import { useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { streamChat } from '@/api/chat'
import { useChatStore } from '@/store/chatStore'
import type { Citation, Session } from '@/types'

// Tránh circular import — định nghĩa inline thay vì import từ useSessions
const sessionKey = (userId: string) => ['sessions', userId]

export function useChat() {
  const {
    messages,
    sessionId,
    userId,
    isStreaming,
    addMessage,
    updateStreamingMessage,
    finalizeStreamingMessage,
    clearMessages,
    resetSession,
    addToast,
    setIsStreaming,
  } = useChatStore()

  const queryClient = useQueryClient()
  const abortControllerRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(
    async (
      text: string,
      imageBase64?: string,
      imageMimeType?: string,
      imagePreview?: string,
    ) => {
      if (isStreaming || !text.trim()) return

      const isFirstMessage = messages.length === 0

      // Add user message
      const userMsgId = crypto.randomUUID()
      addMessage({
        id: userMsgId,
        role: 'user',
        content: text.trim(),
        imagePreview,
        createdAt: new Date(),
      })

      // Add empty assistant message (streaming placeholder)
      const assistantMsgId = crypto.randomUUID()
      addMessage({
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        isStreaming: true,
        citations: [],
        createdAt: new Date(),
      })

      setIsStreaming(true)

      // Optimistic update: hiển thị session mới trong sidebar ngay lập tức
      if (isFirstMessage) {
        const now = new Date().toISOString()
        queryClient.setQueryData<Session[]>(sessionKey(userId), (old) => {
          const list = Array.isArray(old) ? old : []
          if (list.some((s) => s.session_id === sessionId)) return list
          return [
            {
              session_id: sessionId,
              title: text.trim().slice(0, 120),
              created_at: now,
              updated_at: now,
              message_count: 1,
            },
            ...list,
          ]
        })
      }

      // Set up abort controller
      const controller = new AbortController()
      abortControllerRef.current = controller

      const collectedCitations: Citation[] = []

      await streamChat({
        request: {
          message: text.trim(),
          user_id: userId,
          session_id: sessionId,
          image_base64: imageBase64,
          image_mime_type: imageMimeType,
        },
        onChunk: (content) => {
          updateStreamingMessage(assistantMsgId, content)
        },
        onCitations: (citations) => {
          collectedCitations.push(...citations)
        },
        onDone: () => {
          finalizeStreamingMessage(
            assistantMsgId,
            collectedCitations.length > 0 ? collectedCitations : undefined,
          )
          // Sync dữ liệu thật từ server (title chính xác, message_count)
          queryClient.invalidateQueries({ queryKey: sessionKey(userId) })
        },
        onError: (error) => {
          finalizeStreamingMessage(assistantMsgId, undefined)
          addToast({ type: 'error', message: error })
        },
        signal: controller.signal,
      })
    },
    [
      isStreaming,
      messages,
      sessionId,
      userId,
      queryClient,
      addMessage,
      updateStreamingMessage,
      finalizeStreamingMessage,
      addToast,
      setIsStreaming,
    ],
  )

  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsStreaming(false)
    }
  }, [setIsStreaming])

  return {
    messages,
    sessionId,
    userId,
    isStreaming,
    sendMessage,
    stopStreaming,
    clearMessages,
    resetSession,
  }
}
