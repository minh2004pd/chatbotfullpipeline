import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AuthUser } from '@/types'
import { authApi } from '@/api/auth'
import { useChatStore } from '@/store/chatStore'

interface AuthStore {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean

  setUser: (user: AuthUser | null) => void
  logout: () => Promise<void>
  checkAuth: () => Promise<boolean>
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true,

      setUser: (user: AuthUser | null) => {
        set({
          user,
          isAuthenticated: !!user,
          isLoading: false,
        })

        // Sync authenticated user_id to chatStore for memory/document isolation
        if (user) {
          useChatStore.getState().setUserId(user.id)
        } else {
          useChatStore.getState().setUserId('default_user')
        }
      },

      logout: async () => {
        try {
          await authApi.logout()
        } catch {
          // ignore — cookies will be cleared regardless
        }
        set({ user: null, isAuthenticated: false })

        // Reset userId in chatStore on logout
        useChatStore.getState().setUserId('default_user')
      },

      checkAuth: async () => {
        set({ isLoading: true })
        try {
          const user = await authApi.getMe()
          set({ user, isAuthenticated: true, isLoading: false })

          // Sync user_id to chatStore for memory/document isolation
          if (user) {
            useChatStore.getState().setUserId(user.id)
          }
          return true
        } catch {
          set({ user: null, isAuthenticated: false, isLoading: false })
          return false
        }
      },
    }),
    {
      name: 'memrag-auth-store',
      version: 1,
      partialize: (state) => ({
        // Only persist user data; isAuthenticated is derived from checkAuth()
        // so we don't persist stale state across sessions
        user: state.user,
      }),
    },
  ),
)
