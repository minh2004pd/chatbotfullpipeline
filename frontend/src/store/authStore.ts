import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AuthUser } from '@/types'
import { authApi } from '@/api/auth'

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
      },

      logout: async () => {
        try {
          await authApi.logout()
        } catch {
          // ignore — cookies will be cleared regardless
        }
        set({ user: null, isAuthenticated: false })
      },

      checkAuth: async () => {
        set({ isLoading: true })
        try {
          const user = await authApi.getMe()
          set({ user, isAuthenticated: true, isLoading: false })
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
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
)
