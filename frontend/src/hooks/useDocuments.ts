import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { documentsApi } from '@/api/documents'
import { useChatStore } from '@/store/chatStore'
import type { UploadProgress } from '@/types'
import { useState, useCallback } from 'react'

export const DOCUMENTS_QUERY_KEY = ['documents']

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

  const uploadFile = useCallback(
    async (file: File): Promise<void> => {
      const tempId = crypto.randomUUID()

      setUploadProgresses((prev) => ({
        ...prev,
        [tempId]: { filename: file.name, progress: 0, status: 'uploading' },
      }))

      try {
        await documentsApi.upload(file, (progress) => {
          setUploadProgresses((prev) => ({
            ...prev,
            [tempId]: { ...prev[tempId], progress },
          }))
        })

        setUploadProgresses((prev) => ({
          ...prev,
          [tempId]: { ...prev[tempId], progress: 100, status: 'done' },
        }))

        void queryClient.invalidateQueries({ queryKey: DOCUMENTS_QUERY_KEY })
        addToast({ type: 'success', message: `"${file.name}" uploaded successfully.` })

        // Remove progress entry after a delay
        setTimeout(() => {
          setUploadProgresses((prev) => {
            const next = { ...prev }
            delete next[tempId]
            return next
          })
        }, 2000)
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
      }
    },
    [queryClient, addToast],
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
