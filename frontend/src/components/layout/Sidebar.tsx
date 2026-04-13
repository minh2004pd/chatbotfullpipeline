import { useState } from 'react'
import {
  User,
  FileText,
  Brain,
  ChevronDown,
  ChevronRight,
  LogOut,
  MessageSquare,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useChatStore } from '@/store/chatStore'
import DocumentPanel from '@/components/documents/DocumentPanel'
import MemoryPanel from '@/components/memory/MemoryPanel'
import SessionList from '@/components/chat/SessionList'

type Section = 'sessions' | 'documents' | 'memory'

export default function Sidebar() {
  const { user, logout } = useAuthStore()
  const { resetSession } = useChatStore()
  const [openSections, setOpenSections] = useState<Set<Section>>(
    new Set(['sessions', 'documents']),
  )

  const toggleSection = (section: Section) => {
    setOpenSections((prev) => {
      const next = new Set(prev)
      if (next.has(section)) next.delete(section)
      else next.add(section)
      return next
    })
  }

  const handleLogout = async () => {
    await logout()
    resetSession()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Phần trên: User + Documents + Memory — cố định, không bị đẩy */}
      <div className="flex-shrink-0">
        {/* User section */}
        <div className="px-3 py-3 border-b border-[#2e2e2e]">
          <div className="flex items-center gap-2.5">
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.display_name}
                className="w-7 h-7 rounded-full flex-shrink-0 object-cover"
              />
            ) : (
              <div className="w-7 h-7 rounded-full bg-violet-900/60 border border-violet-700/50 flex items-center justify-center flex-shrink-0">
                <User size={13} className="text-violet-400" />
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="text-sm text-[#f1f1f1] font-medium truncate">
                {user?.display_name || 'User'}
              </div>
              <div className="text-[10px] text-[#555] truncate">
                {user?.email || ''}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="p-1 text-[#444] hover:text-red-400 hover:bg-red-400/10 rounded transition-colors flex-shrink-0"
              title="Đăng xuất"
            >
              <LogOut size={13} />
            </button>
          </div>
        </div>

        {/* Documents section */}
        <div className="border-b border-[#2e2e2e]">
          <button
            onClick={() => toggleSection('documents')}
            className="flex items-center gap-2 w-full px-3 py-2.5 text-left hover:bg-[#1e1e1e] transition-colors group"
          >
            <FileText size={14} className="text-violet-400 flex-shrink-0" />
            <span className="text-xs font-medium text-[#a0a0a0] uppercase tracking-wider flex-1">
              Documents
            </span>
            {openSections.has('documents') ? (
              <ChevronDown size={12} className="text-[#555] group-hover:text-[#a0a0a0] transition-colors" />
            ) : (
              <ChevronRight size={12} className="text-[#555] group-hover:text-[#a0a0a0] transition-colors" />
            )}
          </button>
          {openSections.has('documents') && (
            <div className="px-2 pb-2">
              <DocumentPanel />
            </div>
          )}
        </div>

        {/* Memory section */}
        <div className="border-b border-[#2e2e2e]">
          <button
            onClick={() => toggleSection('memory')}
            className="flex items-center gap-2 w-full px-3 py-2.5 text-left hover:bg-[#1e1e1e] transition-colors group"
          >
            <Brain size={14} className="text-violet-400 flex-shrink-0" />
            <span className="text-xs font-medium text-[#a0a0a0] uppercase tracking-wider flex-1">
              Memories
            </span>
            {openSections.has('memory') ? (
              <ChevronDown size={12} className="text-[#555] group-hover:text-[#a0a0a0] transition-colors" />
            ) : (
              <ChevronRight size={12} className="text-[#555] group-hover:text-[#a0a0a0] transition-colors" />
            )}
          </button>
          {openSections.has('memory') && (
            <div className="px-2 pb-2">
              <MemoryPanel />
            </div>
          )}
        </div>
      </div>

      {/* History — chiếm phần còn lại, scroll độc lập */}
      <div className="flex flex-col flex-1 min-h-0 border-t border-[#2e2e2e]">
        <button
          onClick={() => toggleSection('sessions')}
          className="flex items-center gap-2 w-full px-3 py-2.5 text-left hover:bg-[#1e1e1e] transition-colors group flex-shrink-0"
        >
          <MessageSquare size={14} className="text-violet-400 flex-shrink-0" />
          <span className="text-xs font-medium text-[#a0a0a0] uppercase tracking-wider flex-1">
            History
          </span>
          {openSections.has('sessions') ? (
            <ChevronDown size={12} className="text-[#555] group-hover:text-[#a0a0a0] transition-colors" />
          ) : (
            <ChevronRight size={12} className="text-[#555] group-hover:text-[#a0a0a0] transition-colors" />
          )}
        </button>
        {openSections.has('sessions') && (
          <div className="flex-1 overflow-y-auto scrollbar-thin pb-4">
            <SessionList />
          </div>
        )}
      </div>
    </div>
  )
}
