import React, { useState } from 'react'
import { LogIn, UserPlus, Loader2, AlertCircle, Mail, Lock, User } from 'lucide-react'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'

type AuthMode = 'login' | 'register'

export default function LoginPage() {
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const setUser = useAuthStore((s) => s.setUser)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      if (mode === 'register') {
        if (password !== confirmPassword) {
          setError('Mật khẩu xác nhận không khớp.')
          setLoading(false)
          return
        }
        const res = await authApi.register({
          email,
          password,
          display_name: displayName,
        })
        setUser({
          id: res.user_id,
          email: res.email,
          display_name: res.display_name,
          avatar_url: res.avatar_url,
        })
      } else {
        const res = await authApi.login({ email, password })
        setUser({
          id: res.user_id,
          email: res.email,
          display_name: res.display_name,
          avatar_url: res.avatar_url,
        })
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Đã xảy ra lỗi'
      // Extract detail from axios error
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || msg)
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = async () => {
    setError('')
    setLoading(true)
    try {
      const url = await authApi.getGoogleAuthUrl()
      window.location.href = url
    } catch {
      setError('Google OAuth chưa được cấu hình.')
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0f0f0f] p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="w-9 h-9 rounded-lg bg-violet-600 flex items-center justify-center">
            <span className="text-white text-sm font-bold">M</span>
          </div>
          <span className="text-lg font-semibold text-[#f1f1f1] tracking-wide">MemRAG</span>
        </div>

        {/* Card */}
        <div className="bg-[#111111] border border-[#2e2e2e] rounded-xl p-6">
          {/* Tab toggle */}
          <div className="flex bg-[#1a1a1a] rounded-lg p-0.5 mb-6">
            <button
              onClick={() => { setMode('login'); setError(''); setConfirmPassword('') }}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-colors ${
                mode === 'login'
                  ? 'bg-[#2a2a2a] text-[#f1f1f1]'
                  : 'text-[#555] hover:text-[#a0a0a0]'
              }`}
            >
              <LogIn size={13} />
              Đăng nhập
            </button>
            <button
              onClick={() => { setMode('register'); setError(''); setConfirmPassword('') }}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-colors ${
                mode === 'register'
                  ? 'bg-[#2a2a2a] text-[#f1f1f1]'
                  : 'text-[#555] hover:text-[#a0a0a0]'
              }`}
            >
              <UserPlus size={13} />
              Đăng ký
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 p-2.5 mb-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
              <AlertCircle size={13} className="flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-3">
            {mode === 'register' && (
              <div className="relative">
                <User size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#444]" />
                <input
                  type="text"
                  placeholder="Tên hiển thị"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full bg-[#0f0f0f] border border-[#2e2e2e] rounded-lg pl-9 pr-3 py-2.5 text-sm text-[#f1f1f1] placeholder-[#444] outline-none focus:border-violet-500 transition-colors"
                />
              </div>
            )}
            <div className="relative">
              <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#444]" />
              <input
                type="email"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-[#0f0f0f] border border-[#2e2e2e] rounded-lg pl-9 pr-3 py-2.5 text-sm text-[#f1f1f1] placeholder-[#444] outline-none focus:border-violet-500 transition-colors"
              />
            </div>
            <div className="relative">
              <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#444]" />
              <input
                type="password"
                placeholder="Mật khẩu"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="w-full bg-[#0f0f0f] border border-[#2e2e2e] rounded-lg pl-9 pr-3 py-2.5 text-sm text-[#f1f1f1] placeholder-[#444] outline-none focus:border-violet-500 transition-colors"
              />
            </div>
            {mode === 'register' && (
              <div className="relative">
                <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#444]" />
                <input
                  type="password"
                  placeholder="Xác nhận mật khẩu"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  minLength={6}
                  className={`w-full bg-[#0f0f0f] border rounded-lg pl-9 pr-3 py-2.5 text-sm text-[#f1f1f1] placeholder-[#444] outline-none transition-colors ${
                    confirmPassword && confirmPassword !== password
                      ? 'border-red-500/60 focus:border-red-500'
                      : 'border-[#2e2e2e] focus:border-violet-500'
                  }`}
                />
                {confirmPassword && confirmPassword !== password && (
                  <p className="text-[10px] text-red-400 mt-1 ml-1">Mật khẩu không khớp</p>
                )}
              </div>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-white transition-colors"
            >
              {loading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : mode === 'login' ? (
                <>
                  <LogIn size={14} />
                  Đăng nhập
                </>
              ) : (
                <>
                  <UserPlus size={14} />
                  Đăng ký
                </>
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-[#2e2e2e]" />
            <span className="text-[10px] text-[#444] uppercase">hoặc</span>
            <div className="flex-1 h-px bg-[#2e2e2e]" />
          </div>

          {/* Google */}
          <button
            onClick={handleGoogleLogin}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-[#1a1a1a] hover:bg-[#222] border border-[#2e2e2e] disabled:opacity-50 rounded-lg text-sm font-medium text-[#f1f1f1] transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
            Tiếp tục với Google
          </button>
        </div>

        <p className="text-center text-[10px] text-[#444] mt-6">
          AI Research Assistant chuyên sâu
        </p>
      </div>
    </div>
  )
}
