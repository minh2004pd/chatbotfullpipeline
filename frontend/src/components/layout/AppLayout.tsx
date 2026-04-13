import { useState } from 'react'
import { Menu, X, Mic, Network } from 'lucide-react'
import Sidebar from './Sidebar'
import ChatWindow from '@/components/chat/ChatWindow'
import ToastContainer from '@/components/ui/ToastContainer'
import TranscriptionPanel from '@/components/transcription/TranscriptionPanel'
import WikiGraphPanel from '@/components/wiki/WikiGraphPanel'
import { useChatStore } from '@/store/chatStore'

type MainView = 'chat' | 'wiki'

export default function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [transcriptionOpen, setTranscriptionOpen] = useState(false)
  const [mainView, setMainView] = useState<MainView>('chat')
  const toasts = useChatStore((s) => s.toasts)
  const removeToast = useChatStore((s) => s.removeToast)
  const wikiAccessCount = useChatStore((s) => s.wikiAccessCount)

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

          {/* View toggle */}
          <div className="flex items-center gap-0.5 bg-[#1a1a1a] border border-[#2e2e2e] rounded-md p-0.5">
            <button
              onClick={() => setMainView('chat')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                mainView === 'chat'
                  ? 'bg-[#2a2a2a] text-[#f1f1f1]'
                  : 'text-[#555] hover:text-[#a0a0a0]'
              }`}
            >
              Chat
            </button>
            <button
              onClick={() => setMainView('wiki')}
              className={`relative flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                mainView === 'wiki'
                  ? 'bg-[#2a2a2a] text-[#f1f1f1]'
                  : 'text-[#555] hover:text-[#a0a0a0]'
              }`}
            >
              <Network size={12} />
              Knowledge
              {wikiAccessCount > 0 && mainView === 'chat' && (
                <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 text-[9px] font-bold leading-none">
                  {wikiAccessCount}
                </span>
              )}
            </button>
          </div>

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
        </header>

        {/* Main view */}
        <div className="flex-1 min-h-0">
          {mainView === 'chat' ? <ChatWindow /> : <WikiGraphPanel />}
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
