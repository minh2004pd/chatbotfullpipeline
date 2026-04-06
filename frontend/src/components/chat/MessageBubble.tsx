import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { User, Bot, ChevronDown, ChevronUp, FileText, Copy, Check } from 'lucide-react'
import type { Message, Citation } from '@/types'

interface Props {
  message: Message
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div
      className={`flex gap-3 py-3 animate-[slideUp_0.2s_ease-out] ${
        isUser ? 'flex-row-reverse' : 'flex-row'
      }`}
    >
      {/* Avatar */}
      <div
        className={`
          w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5
          ${isUser
            ? 'bg-violet-700/60 border border-violet-600/50'
            : 'bg-[#1e1e1e] border border-[#2e2e2e]'
          }
        `}
      >
        {isUser ? (
          <User size={13} className="text-violet-300" />
        ) : (
          <Bot size={13} className="text-violet-400" />
        )}
      </div>

      {/* Content */}
      <div className={`flex flex-col gap-2 max-w-[80%] min-w-0 ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Image preview (user messages with images) */}
        {message.imagePreview && (
          <div className="rounded-xl overflow-hidden border border-[#2e2e2e] max-w-[200px]">
            <img
              src={message.imagePreview}
              alt="Attached image"
              className="w-full h-auto object-cover"
            />
          </div>
        )}

        {/* Message bubble */}
        <div
          className={`
            rounded-2xl px-4 py-3 text-sm leading-relaxed
            ${isUser
              ? 'bg-[#1e1035] border border-violet-800/50 text-[#e8e0ff] rounded-tr-sm'
              : 'bg-[#1a1a1a] border border-[#2e2e2e] text-[#f1f1f1] rounded-tl-sm'
            }
          `}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <AssistantContent content={message.content} isStreaming={message.isStreaming} />
          )}
        </div>

        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <CitationsList citations={message.citations} />
        )}

        {/* Timestamp */}
        <span className="text-[10px] text-[#444] px-1">
          {formatTime(message.createdAt)}
        </span>
      </div>
    </div>
  )
}

function AssistantContent({
  content,
  isStreaming,
}: {
  content: string
  isStreaming?: boolean
}) {
  return (
    <div className="prose prose-invert prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className ?? '')
            const isBlock = !!match
            const codeString = String(children).replace(/\n$/, '')

            if (isBlock) {
              return (
                <CodeBlock language={match[1]} code={codeString} />
              )
            }
            return (
              <code
                className="bg-[#0f0f0f] text-violet-300 rounded px-1.5 py-0.5 text-[0.85em] font-mono border border-[#2e2e2e]"
                {...props}
              >
                {children}
              </code>
            )
          },
          pre({ children }) {
            return <>{children}</>
          },
          p({ children }) {
            return <p className="mb-2 last:mb-0">{children}</p>
          },
          ul({ children }) {
            return <ul className="list-disc list-inside mb-2 space-y-0.5 pl-1">{children}</ul>
          },
          ol({ children }) {
            return <ol className="list-decimal list-inside mb-2 space-y-0.5 pl-1">{children}</ol>
          },
          li({ children }) {
            return <li className="text-[#e0e0e0]">{children}</li>
          },
          blockquote({ children }) {
            return (
              <blockquote className="border-l-2 border-violet-600/50 pl-3 text-[#a0a0a0] italic my-2">
                {children}
              </blockquote>
            )
          },
          h1({ children }) {
            return <h1 className="text-lg font-bold text-[#f1f1f1] mb-2 mt-3 first:mt-0">{children}</h1>
          },
          h2({ children }) {
            return <h2 className="text-base font-semibold text-[#f1f1f1] mb-1.5 mt-3 first:mt-0">{children}</h2>
          },
          h3({ children }) {
            return <h3 className="text-sm font-semibold text-[#f1f1f1] mb-1 mt-2 first:mt-0">{children}</h3>
          },
          a({ href, children }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-violet-400 hover:text-violet-300 underline underline-offset-2"
              >
                {children}
              </a>
            )
          },
          table({ children }) {
            return (
              <div className="overflow-x-auto my-2">
                <table className="text-xs border-collapse w-full">{children}</table>
              </div>
            )
          },
          th({ children }) {
            return (
              <th className="border border-[#2e2e2e] bg-[#111] px-3 py-1.5 text-left font-medium text-[#a0a0a0]">
                {children}
              </th>
            )
          },
          td({ children }) {
            return (
              <td className="border border-[#2e2e2e] px-3 py-1.5 text-[#e0e0e0]">
                {children}
              </td>
            )
          },
          hr() {
            return <hr className="border-[#2e2e2e] my-3" />
          },
        }}
      >
        {content}
      </ReactMarkdown>
      {isStreaming && (
        <span
          className="inline-block w-0.5 h-4 bg-violet-400 ml-0.5 align-text-bottom animate-[blink_1s_step-end_infinite]"
          aria-hidden="true"
        />
      )}
    </div>
  )
}

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
    } catch {
      // Fallback cho browser block clipboard API
      const el = document.createElement('textarea')
      el.value = code
      el.style.position = 'fixed'
      el.style.opacity = '0'
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-[#2e2e2e] group">
      {/* Code header */}
      <div className="flex items-center justify-between bg-[#111] px-3 py-1.5 border-b border-[#2e2e2e]">
        <span className="text-[10px] text-[#666] font-mono uppercase tracking-wider">
          {language}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[#555] hover:text-[#a0a0a0] transition-colors text-[10px]"
        >
          {copied ? (
            <>
              <Check size={11} className="text-green-400" />
              <span className="text-green-400">Copied</span>
            </>
          ) : (
            <>
              <Copy size={11} />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        style={oneDark}
        language={language}
        PreTag="div"
        customStyle={{
          margin: 0,
          borderRadius: 0,
          background: '#0a0a0a',
          fontSize: '0.78rem',
          padding: '0.85rem 1rem',
        }}
        codeTagProps={{
          style: { fontFamily: "'JetBrains Mono', 'Fira Code', monospace" },
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}

function CitationsList({ citations }: { citations: Citation[] }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="w-full max-w-full">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-[10px] text-[#555] hover:text-[#a0a0a0] transition-colors px-1 py-0.5 rounded hover:bg-[#1e1e1e]"
      >
        <FileText size={10} />
        <span>
          {citations.length} source{citations.length !== 1 ? 's' : ''}
        </span>
        {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
      </button>

      {expanded && (
        <div className="mt-1.5 space-y-1.5 animate-[fadeIn_0.15s_ease-in-out]">
          {citations.map((citation, i) => (
            <CitationCard key={`${citation.document_id}-${i}`} citation={citation} index={i + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  const [open, setOpen] = useState(false)
  const scorePercent = Math.round((citation.score ?? 0) * 100)

  return (
    <div className="bg-[#111] border border-[#2a2a2a] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[#1a1a1a] transition-colors"
      >
        <span className="text-[10px] text-violet-500 font-mono font-bold flex-shrink-0">
          [{index}]
        </span>
        <span className="text-[11px] text-[#a0a0a0] truncate flex-1 font-medium">
          {citation.document_name}
        </span>
        <span className="text-[10px] text-[#555] flex-shrink-0">
          {scorePercent}%
        </span>
        {open ? (
          <ChevronUp size={10} className="text-[#555] flex-shrink-0" />
        ) : (
          <ChevronDown size={10} className="text-[#555] flex-shrink-0" />
        )}
      </button>
      {open && (
        <div className="px-3 pb-2.5 border-t border-[#1e1e1e]">
          <p className="text-[11px] text-[#888] leading-relaxed mt-2 line-clamp-6">
            {citation.chunk_text}
          </p>
        </div>
      )}
    </div>
  )
}

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('en', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date))
}
