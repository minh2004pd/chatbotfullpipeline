import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsApi } from '@/api/documents'
import { useChatStore } from '@/store/chatStore'
import type { UploadProgress } from '@/types'
import { useState, useCallback } from 'react'

export const DOCUMENTS_QUERY_KEY = ['documents']

const POLL_INTERVAL_MS = 2000
const MAX_POLLS = 90  // 3 phút tối đa

export function useDocuments() {
  const queryClient = useQueryClient()
  const { addToast, userId } = useChatStore()
  const [uploadProgresses, setUploadProgresses] = useState<
    Record<string, UploadProgress>
  >({})

  const documentsQuery = useQuery({
    queryKey: [...DOCUMENTS_QUERY_KEY, userId],
    queryFn: () => documentsApi.list(),
    staleTime: 30_000,
  })

  const deleteMutation = useMutation({
    mutationFn: (documentId: string) => documentsApi.delete(documentId),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: DOCUMENTS_QUERY_KEY })
      addToast({ type: 'success', message: data.message || 'Document deleted.' })
    },
    onError: () => {
      addToast({ type: 'error', message: 'Failed to delete document.' })
    },
  })

  const scheduleRemove = useCallback((tempId: string, delayMs = 3000) => {
    setTimeout(() => {
      setUploadProgresses((prev) => {
        const next = { ...prev }
        delete next[tempId]
        return next
      })
    }, delayMs)
  }, [])

  const pollWikiStatus = useCallback(
    (tempId: string, documentId: string) => {
      let polls = 0

      const tick = async () => {
        if (polls++ >= MAX_POLLS) {
          // Timeout — server quá chậm hoặc đã restart, treat as done
          setUploadProgresses((prev) => {
            const entry = prev[tempId]
            if (!entry) return prev
            return { ...prev, [tempId]: { ...entry, status: 'done' } }
          })
          scheduleRemove(tempId)
          void queryClient.invalidateQueries({ queryKey: DOCUMENTS_QUERY_KEY })
          return
        }

        try {
          const { wiki } = await documentsApi.getIndexingStatus(documentId)

          if (wiki === 'done' || wiki === 'disabled') {
            setUploadProgresses((prev) => {
              const entry = prev[tempId]
              if (!entry) return prev
              return { ...prev, [tempId]: { ...entry, status: 'done' } }
            })
            scheduleRemove(tempId)
            void queryClient.invalidateQueries({ queryKey: DOCUMENTS_QUERY_KEY })
          } else if (wiki === 'error') {
            setUploadProgresses((prev) => {
              const entry = prev[tempId]
              if (!entry) return prev
              return { ...prev, [tempId]: { ...entry, status: 'error', error: 'Wiki indexing failed' } }
            })
            scheduleRemove(tempId, 5000)
          } else {
            // "processing" — tiếp tục poll
            setTimeout(() => void tick(), POLL_INTERVAL_MS)
          }
        } catch {
          // Lỗi mạng hoặc server — treat as done để không block UI mãi
          setUploadProgresses((prev) => {
            const entry = prev[tempId]
            if (!entry) return prev
            return { ...prev, [tempId]: { ...entry, status: 'done' } }
          })
          scheduleRemove(tempId)
        }
      }

      // Poll đầu tiên sau 1.5s (để wiki task kịp start)
      setTimeout(() => void tick(), 1500)
    },
    [queryClient, scheduleRemove],
  )

  const uploadFile = useCallback(
    async (file: File): Promise<void> => {
      const tempId = crypto.randomUUID()

      setUploadProgresses((prev) => ({
        ...prev,
        [tempId]: { filename: file.name, progress: 0, status: 'uploading' },
      }))

      try {
        const result = await documentsApi.upload(file, (progress) => {
          setUploadProgresses((prev) => ({
            ...prev,
            [tempId]: { ...prev[tempId], progress },
          }))
        })

        // RAG xong (synchronous) — chuyển sang giai đoạn wiki
        setUploadProgresses((prev) => ({
          ...prev,
          [tempId]: {
            ...prev[tempId],
            progress: 100,
            status: 'rag_done',
            documentId: result.document_id,
            chunkCount: result.chunk_count,
          },
        }))

        addToast({ type: 'success', message: `"${file.name}" uploaded successfully.` })

        // Bắt đầu poll wiki status
        pollWikiStatus(tempId, result.document_id)
      } catch {
        setUploadProgresses((prev) => ({
          ...prev,
          [tempId]: {
            ...prev[tempId],
            status: 'error',
            error: 'Upload failed',
          },
        }))
        addToast({ type: 'error', message: `Failed to upload "${file.name}".` })
        scheduleRemove(tempId, 5000)
      }
    },
    [addToast, pollWikiStatus, scheduleRemove],
  )

  return {
    documents: documentsQuery.data?.documents ?? [],
    total: documentsQuery.data?.total ?? 0,
    isLoading: documentsQuery.isLoading,
    isError: documentsQuery.isError,
    refetch: documentsQuery.refetch,
    uploadFile,
    uploadProgresses,
    deleteDocument: deleteMutation.mutate,
    isDeleting: deleteMutation.isPending,
  }
}
