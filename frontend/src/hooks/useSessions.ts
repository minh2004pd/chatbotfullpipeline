import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { deleteSession, getSessionMessages, getSessions } from '@/api/sessions'
import { useChatStore } from '@/store/chatStore'
import type { Message } from '@/types'

export const sessionsQueryKey = (userId: string) => ['sessions', userId]

export function useSessions() {
  const queryClient = useQueryClient()
  const userId = useChatStore((s) => s.userId)
  const sessionId = useChatStore((s) => s.sessionId)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const loadSession = useChatStore((s) => s.loadSession)
  const resetSession = useChatStore((s) => s.resetSession)
  const addToast = useChatStore((s) => s.addToast)

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: sessionsQueryKey(userId),
    queryFn: getSessions,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
  })

  const deleteMutation = useMutation({
    mutationFn: (sid: string) => deleteSession(sid),
    onSuccess: (_data, sid) => {
      queryClient.invalidateQueries({ queryKey: sessionsQueryKey(userId) })
      // Nếu xóa session đang active → tạo session mới
      if (sid === sessionId) {
        resetSession()
      }
    },
    onError: () => {
      addToast({ type: 'error', message: 'Xóa session thất bại' })
    },
  })

  const loadSessionById = async (sid: string) => {
    if (isStreaming) {
      addToast({ type: 'warning', message: 'Vui lòng đợi AI trả lời xong trước khi chuyển session' })
      return
    }
    try {
      const result = await getSessionMessages(sid)
      const messages: Message[] = result.messages.map((m, i) => ({
        id: `hist-${sid}-${i}`,
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content,
        createdAt: new Date(m.timestamp),
      }))
      loadSession(sid, messages)
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 404) {
        queryClient.invalidateQueries({ queryKey: sessionsQueryKey(userId) })
      } else {
        addToast({ type: 'error', message: 'Không thể tải lịch sử session' })
      }
    }
  }

  return {
    sessions,
    isLoading,
    currentSessionId: sessionId,
    deleteSession: (sid: string) => deleteMutation.mutate(sid),
    loadSessionById,
    isDeletingSession: deleteMutation.isPending,
  }
}
