import { useState, useRef, type MouseEvent } from 'react'
import { MessageSquare, Trash2, Plus, Loader2 } from 'lucide-react'
import { useSessions } from '@/hooks/useSessions'
import { useChatStore } from '@/store/chatStore'

function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  if (diffDays === 0) return 'Hôm nay'
  if (diffDays === 1) return 'Hôm qua'
  if (diffDays < 7) return `${diffDays} ngày trước`
  return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })
}

export default function SessionList() {
  const { sessions, isLoading, currentSessionId, deleteSession, loadSessionById } = useSessions()
  const resetSession = useChatStore((s) => s.resetSession)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const loadingRef = useRef(false)

  const handleLoad = async (sessionId: string) => {
    if (sessionId === currentSessionId || loadingRef.current) return
    loadingRef.current = true
    setLoadingId(sessionId)
    await loadSessionById(sessionId)
    loadingRef.current = false
    setLoadingId(null)
  }

  const handleDelete = async (e: MouseEvent<HTMLButtonElement>, sessionId: string) => {
    e.stopPropagation()
    setDeletingId(sessionId)
    deleteSession(sessionId)
    // deletingId cleared after mutation resolves (via re-render)
    setTimeout(() => setDeletingId(null), 500)
  }

  return (
    <div className="flex flex-col">
      {/* Header + New session button */}
      <div className="flex items-center justify-between px-3 py-1.5">
        <span className="text-[10px] font-semibold text-[#555] uppercase tracking-widest">
          Chats
        </span>
        <button
          onClick={resetSession}
          title="Tạo session mới"
          className="flex items-center gap-1 text-[10px] text-[#555] hover:text-violet-400 transition-colors px-1.5 py-0.5 rounded hover:bg-violet-900/20"
        >
          <Plus size={10} />
          <span>Mới</span>
        </button>
      </div>

      {/* Session list */}
      <div className="flex flex-col gap-0.5 px-1.5">
        {isLoading ? (
          // Skeleton loading
          Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-9 rounded-md bg-[#1a1a1a] animate-pulse"
              style={{ opacity: 1 - i * 0.25 }}
            />
          ))
        ) : sessions.length === 0 ? (
          <div className="px-2 py-4 text-center">
            <MessageSquare size={20} className="text-[#333] mx-auto mb-1.5" />
            <p className="text-[11px] text-[#444]">Chưa có cuộc trò chuyện</p>
          </div>
        ) : (
          sessions.map((session) => {
            const isActive = session.session_id === currentSessionId
            const isLoading = loadingId === session.session_id
            const isDeleting = deletingId === session.session_id

            return (
              <div
                key={session.session_id}
                role="button"
                tabIndex={0}
                onClick={() => handleLoad(session.session_id)}
                onKeyDown={(e) => e.key === 'Enter' && handleLoad(session.session_id)}
                aria-disabled={isLoading || isDeleting}
                className={`
                  group relative w-full text-left rounded-md px-2.5 py-2 transition-all duration-150 cursor-pointer
                  ${isActive
                    ? 'bg-violet-900/25 border-l-2 border-violet-500 pl-[9px]'
                    : 'hover:bg-[#1e1e1e] border-l-2 border-transparent pl-[9px]'
                  }
                  ${isLoading || isDeleting ? 'opacity-50 pointer-events-none' : ''}
                `}
              >
                <div className="flex items-center gap-1.5 pr-5">
                  {isLoading ? (
                    <Loader2 size={10} className="text-violet-400 flex-shrink-0 animate-spin" />
                  ) : (
                    <MessageSquare
                      size={10}
                      className={`flex-shrink-0 ${isActive ? 'text-violet-400' : 'text-[#444] group-hover:text-[#666]'}`}
                    />
                  )}
                  <span
                    className={`
                      text-xs truncate leading-tight flex-1
                      ${isActive ? 'text-[#e8e8e8] font-medium' : 'text-[#888] group-hover:text-[#b0b0b0]'}
                    `}
                    title={session.title}
                  >
                    {session.title}
                  </span>
                </div>

                <div className="flex items-center gap-1.5 mt-0.5 pl-[18px]">
                  <span className="text-[10px] text-[#444] group-hover:text-[#555]">
                    {formatRelativeDate(session.updated_at)}
                  </span>
                  <span className="text-[10px] text-[#333] group-hover:text-[#444]">
                    · {session.message_count} tin
                  </span>
                </div>

                {/* Delete button — appears on hover */}
                <button
                  onClick={(e) => handleDelete(e, session.session_id)}
                  title="Xóa session"
                  className={`
                    absolute right-1.5 top-1/2 -translate-y-1/2
                    p-1 rounded transition-all duration-150
                    opacity-0 group-hover:opacity-100
                    ${isActive
                      ? 'text-violet-400/60 hover:text-red-400 hover:bg-red-900/20'
                      : 'text-[#444] hover:text-red-400 hover:bg-red-900/20'
                    }
                  `}
                >
                  {isDeleting ? (
                    <Loader2 size={11} className="animate-spin" />
                  ) : (
                    <Trash2 size={11} />
                  )}
                </button>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
