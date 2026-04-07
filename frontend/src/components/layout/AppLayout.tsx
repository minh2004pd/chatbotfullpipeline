import { useState } from 'react'
import { Menu, X, Mic } from 'lucide-react'
import Sidebar from './Sidebar'
import ChatWindow from '@/components/chat/ChatWindow'
import ToastContainer from '@/components/ui/ToastContainer'
import TranscriptionPanel from '@/components/transcription/TranscriptionPanel'
import { useChatStore } from '@/store/chatStore'

export default function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [transcriptionOpen, setTranscriptionOpen] = useState(false)
  const toasts = useChatStore((s) => s.toasts)
  const removeToast = useChatStore((s) => s.removeToast)

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0f0f0f] text-[#f1f1f1] font-sans">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:relative z-30 lg:z-auto
          h-full flex-shrink-0 flex flex-col
          bg-[#111111] border-r border-[#2e2e2e]
          transition-all duration-300 ease-in-out
          ${sidebarOpen ? 'w-72 translate-x-0' : 'w-0 -translate-x-full lg:w-0 lg:translate-x-0'}
        `}
        style={{ minWidth: sidebarOpen ? '288px' : '0' }}
      >
        {sidebarOpen && (
          <div className="flex flex-col h-full overflow-hidden">
            <div className="flex items-center justify-between px-4 pt-4 pb-2 flex-shrink-0">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-violet-600 flex items-center justify-center flex-shrink-0">
                  <span className="text-white text-xs font-bold">M</span>
                </div>
                <span className="font-semibold text-[#f1f1f1] text-sm tracking-wide">
                  MemRAG
                </span>
              </div>
              <button
                onClick={() => setSidebarOpen(false)}
                className="text-[#666] hover:text-[#f1f1f1] transition-colors p-1 rounded-md hover:bg-[#2a2a2a] lg:flex hidden"
                aria-label="Close sidebar"
              >
                <X size={16} />
              </button>
            </div>
            <Sidebar />
          </div>
        )}
      </aside>

      {/* Main chat area */}
      <main className="flex flex-col flex-1 min-w-0 h-full">
        {/* Top bar */}
        <header className="flex items-center gap-3 px-4 py-3 border-b border-[#2e2e2e] flex-shrink-0 bg-[#0f0f0f]/80 backdrop-blur-sm">
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="p-1.5 rounded-md text-[#666] hover:text-[#f1f1f1] hover:bg-[#2a2a2a] transition-colors"
            aria-label="Toggle sidebar"
          >
            <Menu size={18} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-violet-600 flex items-center justify-center">
              <span className="text-white text-[9px] font-bold">M</span>
            </div>
            <span className="text-sm font-medium text-[#a0a0a0]">MemRAG Chat</span>
          </div>
          <div className="flex-1" />
          <button
            onClick={() => setTranscriptionOpen((v) => !v)}
            className={`p-1.5 rounded-md transition-colors ${
              transcriptionOpen
                ? 'text-violet-400 bg-violet-900/30'
                : 'text-[#666] hover:text-[#f1f1f1] hover:bg-[#2a2a2a]'
            }`}
            title="Toggle transcription panel"
          >
            <Mic size={18} />
          </button>
          <div className="text-xs text-[#666] hidden sm:block">
            Multimodal · RAG · Long-term Memory
          </div>
        </header>

        {/* Chat window */}
        <div className="flex-1 min-h-0">
          <ChatWindow />
        </div>
      </main>

      {/* Transcription panel (right side) */}
      {transcriptionOpen && (
        <aside className="w-80 flex-shrink-0 border-l border-[#2e2e2e] flex flex-col h-full bg-[#0f0f0f]">
          <TranscriptionPanel />
        </aside>
      )}

      {/* Toast notifications */}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </div>
  )
}
