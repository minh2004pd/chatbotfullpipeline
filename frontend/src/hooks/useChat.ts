import { useCallback, useRef } from 'react'
import { streamChat } from '@/api/chat'
import { useChatStore } from '@/store/chatStore'
import type { Citation } from '@/types'

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

  const abortControllerRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(
    async (
      text: string,
      imageBase64?: string,
      imageMimeType?: string,
      imagePreview?: string,
    ) => {
      if (isStreaming || !text.trim()) return

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
      sessionId,
      userId,
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
