import React, { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import LoginPage from './LoginPage'

interface AuthGuardProps {
  children: React.ReactNode
}

export default function AuthGuard({ children }: AuthGuardProps) {
  const { isAuthenticated, isLoading, checkAuth, setUser } = useAuthStore()
  const [checked, setChecked] = useState(false)

  useEffect(() => {
    checkAuth().then(() => setChecked(true))
  }, [checkAuth])

  // Listen for logout events from 401 interceptor
  useEffect(() => {
    const handleLogout = () => {
      setUser(null)
    }
    window.addEventListener('auth:logout', handleLogout)
    return () => window.removeEventListener('auth:logout', handleLogout)
  }, [setUser])

  // Handle Google OAuth callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    if (code && !checked) {
      // Import async to avoid circular deps
      import('@/api/auth').then(async ({ authApi }) => {
        try {
          const res = await authApi.googleCallback(code)
          useAuthStore.getState().setUser({
            id: res.user_id,
            email: res.email,
            display_name: res.display_name,
            avatar_url: res.avatar_url,
          })
          // Clean URL
          window.history.replaceState({}, '', window.location.pathname)
        } catch {
          // Stay on login page, error will show
        }
        setChecked(true)
      })
      return
    }
  }, [checked])

  if (isLoading || !checked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0f0f0f]">
        <div className="flex items-center gap-2 text-[#555] text-sm">
          <Loader2 size={16} className="animate-spin" />
          Đang kiểm tra đăng nhập...
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <LoginPage />
  }

  return <>{children}</>
}
