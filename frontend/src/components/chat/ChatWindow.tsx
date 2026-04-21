import { useEffect, useRef } from 'react'
import { Bot, Sparkles, Mic, Network } from 'lucide-react'
import { useChat } from '@/hooks/useChat'
import MessageBubble from './MessageBubble'
import MessageInput from './MessageInput'

interface ChatWindowProps {
  transcriptionOpen?: boolean
  onToggleTranscription?: () => void
}

export default function ChatWindow({ transcriptionOpen, onToggleTranscription }: ChatWindowProps) {
  const { messages, isStreaming, sendMessage, stopStreaming } = useChat()
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages / streaming updates
  useEffect(() => {
    const el = bottomRef.current
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  return (
    <div className="flex flex-col h-full bg-[#0f0f0f]">
      {/* Messages area */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto px-4 py-4 space-y-1 scroll-smooth"
        style={{ scrollbarWidth: 'thin', scrollbarColor: '#2e2e2e #0f0f0f' }}
      >
        {messages.length === 0 ? (
          <WelcomeScreen />
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
          </>
        )}
        <div ref={bottomRef} className="h-1" />
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 border-t border-[#2e2e2e] bg-[#0f0f0f]">
        <MessageInput
          onSend={sendMessage}
          onStop={stopStreaming}
          isStreaming={isStreaming}
          transcriptionOpen={transcriptionOpen}
          onToggleTranscription={onToggleTranscription}
        />
      </div>
    </div>
  )
}

function WelcomeScreen() {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center px-4 animate-[fadeIn_0.4s_ease-in-out]">
      <div className="w-16 h-16 rounded-2xl bg-violet-900/40 border border-violet-700/40 flex items-center justify-center mb-5">
        <Bot size={28} className="text-violet-400" />
      </div>
      <h2 className="text-xl font-semibold text-[#f1f1f1] mb-2">
        Welcome to MemRAG
      </h2>
      <p className="text-[#666] text-sm max-w-md leading-relaxed mb-6">
        An AI research assistant with long-term memory, document understanding,
        and voice transcription. Upload PDFs in the sidebar, record meetings,
        and ask questions — your conversations are remembered across sessions.
      </p>
      <div className="flex flex-wrap justify-center gap-3 w-full max-w-xl">
        {[
          {
            icon: <Sparkles size={14} />,
            title: 'RAG Search',
            desc: 'Ask questions about uploaded PDFs',
          },
          {
            icon: <Sparkles size={14} />,
            title: 'Long Memory',
            desc: 'Remembers your preferences and history',
          },
          {
            icon: <Sparkles size={14} />,
            title: 'Multimodal',
            desc: 'Send images alongside your messages',
          },
          {
            icon: <Mic size={14} />,
            title: 'Voice Transcription',
            desc: 'Record meetings & search transcripts',
          },
          {
            icon: <Network size={14} />,
            title: 'Knowledge Wiki',
            desc: 'Auto-generated wiki from your documents',
          },
        ].map((item) => (
          <div
            key={item.title}
            className="bg-[#1a1a1a] border border-[#2e2e2e] rounded-xl p-3 text-left w-[calc(50%-6px)] sm:w-[calc(33.333%-8px)]"
          >
            <div className="flex items-center gap-1.5 text-violet-400 mb-1.5">
              {item.icon}
              <span className="text-xs font-medium">{item.title}</span>
            </div>
            <p className="text-xs text-[#666] leading-relaxed">{item.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
