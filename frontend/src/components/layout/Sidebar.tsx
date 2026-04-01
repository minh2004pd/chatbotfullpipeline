import { useState } from 'react'
import {
  User,
  FileText,
  Brain,
  ChevronDown,
  ChevronRight,
  Edit3,
  Check,
  X,
  RotateCcw,
} from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import DocumentPanel from '@/components/documents/DocumentPanel'
import MemoryPanel from '@/components/memory/MemoryPanel'

type Section = 'documents' | 'memory'

export default function Sidebar() {
  const { userId, setUserId, resetSession } = useChatStore()
  const [openSections, setOpenSections] = useState<Set<Section>>(
    new Set(['documents']),
  )
  const [editingUser, setEditingUser] = useState(false)
  const [userIdInput, setUserIdInput] = useState(userId)

  const toggleSection = (section: Section) => {
    setOpenSections((prev) => {
      const next = new Set(prev)
      if (next.has(section)) next.delete(section)
      else next.add(section)
      return next
    })
  }

  const handleSaveUserId = () => {
    const trimmed = userIdInput.trim()
    if (trimmed) {
      setUserId(trimmed)
      resetSession()
    }
    setEditingUser(false)
  }

  const handleCancelEdit = () => {
    setUserIdInput(userId)
    setEditingUser(false)
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto pb-4 scrollbar-thin">
      {/* User ID section */}
      <div className="px-3 py-3 border-b border-[#2e2e2e]">
        <div className="flex items-center gap-2 mb-1.5">
          <div className="w-7 h-7 rounded-full bg-violet-900/60 border border-violet-700/50 flex items-center justify-center flex-shrink-0">
            <User size={13} className="text-violet-400" />
          </div>
          <span className="text-xs text-[#666] font-medium uppercase tracking-wider">
            User
          </span>
        </div>

        {editingUser ? (
          <div className="flex items-center gap-1.5 mt-2">
            <input
              value={userIdInput}
              onChange={(e) => setUserIdInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveUserId()
                if (e.key === 'Escape') handleCancelEdit()
              }}
              autoFocus
              className="flex-1 bg-[#1a1a1a] border border-violet-700/60 rounded-md px-2.5 py-1.5 text-xs text-[#f1f1f1] outline-none focus:border-violet-500 transition-colors"
              placeholder="user_id"
            />
            <button
              onClick={handleSaveUserId}
              className="p-1.5 text-violet-400 hover:text-violet-300 hover:bg-violet-900/30 rounded transition-colors"
            >
              <Check size={13} />
            </button>
            <button
              onClick={handleCancelEdit}
              className="p-1.5 text-[#666] hover:text-[#a0a0a0] hover:bg-[#2a2a2a] rounded transition-colors"
            >
              <X size={13} />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 group">
            <span className="text-sm text-[#f1f1f1] font-medium truncate flex-1 pl-0.5">
              {userId}
            </span>
            <button
              onClick={() => {
                setUserIdInput(userId)
                setEditingUser(true)
              }}
              className="p-1 text-[#444] hover:text-[#a0a0a0] opacity-0 group-hover:opacity-100 transition-all rounded"
              title="Edit user ID"
            >
              <Edit3 size={12} />
            </button>
          </div>
        )}

        <button
          onClick={resetSession}
          className="mt-2 flex items-center gap-1.5 text-xs text-[#555] hover:text-[#a0a0a0] transition-colors w-full py-1 px-1 rounded hover:bg-[#1e1e1e]"
          title="Start a new session"
        >
          <RotateCcw size={11} />
          <span>New session</span>
        </button>
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
      <div>
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
  )
}
