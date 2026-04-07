import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ChatStore, Message, Citation, Toast } from '@/types'
import { setUserIdInStorage } from '@/api/client'

const generateId = () => crypto.randomUUID()

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      messages: [],
      sessionId: generateId(),
      userId: localStorage.getItem('memrag_user_id') ?? 'default_user',
      isStreaming: false,
      toasts: [],

      addMessage: (message: Message) => {
        set((state) => ({ messages: [...state.messages, message] }))
      },

      updateStreamingMessage: (id: string, content: string) => {
        set((state) => ({
          messages: state.messages.map((msg) =>
            msg.id === id
              ? { ...msg, content: msg.content + content }
              : msg,
          ),
        }))
      },

      finalizeStreamingMessage: (id: string, citations?: Citation[]) => {
        set((state) => ({
          messages: state.messages.map((msg) =>
            msg.id === id
              ? { ...msg, isStreaming: false, citations: citations ?? msg.citations }
              : msg,
          ),
          isStreaming: false,
        }))
      },

      clearMessages: () => {
        set({ messages: [] })
      },

      setUserId: (userId: string) => {
        setUserIdInStorage(userId)
        set({ userId })
      },

      resetSession: () => {
        set({ sessionId: generateId(), messages: [] })
      },

      loadSession: (sessionId: string, messages: Message[]) => {
        set({ sessionId, messages, isStreaming: false })
      },

      addToast: (toast: Omit<Toast, 'id'>) => {
        const id = generateId()
        set((state) => ({
          toasts: [...state.toasts, { ...toast, id }],
        }))
        // Auto-remove after 4 seconds
        setTimeout(() => {
          get().removeToast(id)
        }, 4000)
      },

      removeToast: (id: string) => {
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        }))
      },

      setIsStreaming: (value: boolean) => {
        set({ isStreaming: value })
      },
    }),
    {
      name: 'memrag-chat-store',
      version: 2, // bump khi schema thay đổi → Zustand tự clear localStorage cũ
      // Chỉ persist userId/sessionId; messages được lấy từ DynamoDB khi cần
      partialize: (state) => ({
        userId: state.userId,
        sessionId: state.sessionId,
      }),
      migrate: (persistedState) => persistedState,
    },
  ),
)
