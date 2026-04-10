import { X, Loader2, AlertCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { WikiGraphNode } from '@/types'
import { useWikiPage } from '@/hooks/useWikiGraph'
import { getNodeColor } from '@/utils/wikiNodeColors'

interface WikiPageDrawerProps {
  node: WikiGraphNode
  onClose: () => void
  onNavigate: (slug: string, category: string) => void
}

export default function WikiPageDrawer({ node, onClose, onNavigate }: WikiPageDrawerProps) {
  const { data, isLoading, isError } = useWikiPage(node.category, node.id)
  const color = getNodeColor(node.type)

  // Render [[pages/entities/slug.md]] links as clickable spans
  const renderContent = (content: string) => {
    const parts = content.split(/(\[\[pages\/[^\]]+\]\])/g)
    return parts.map((part, i) => {
      const match = part.match(/^\[\[pages\/(\w+)\/(\w+)\.md\]\]$/)
      if (match) {
        const [, cat, slug] = match
        return (
          <button
            key={i}
            onClick={() => onNavigate(slug, cat)}
            className="text-violet-400 hover:text-violet-300 underline underline-offset-2 cursor-pointer"
          >
            {slug}
          </button>
        )
      }
      return part
    })
  }

  return (
    <div className="flex flex-col h-full bg-[#111111] border-l border-[#2e2e2e]">
      {/* Header */}
      <div
        className="flex items-start justify-between px-4 py-3 border-b border-[#2e2e2e] flex-shrink-0"
        style={{ borderLeftColor: color, borderLeftWidth: 3 }}
      >
        <div className="flex-1 min-w-0 pr-2">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span
              className="text-[10px] uppercase tracking-wider font-semibold"
              style={{ color }}
            >
              {node.type}
            </span>
            <span className="text-[#444] text-[10px]">·</span>
            <span className="text-[10px] text-[#555]">{node.category}</span>
          </div>
          <h2 className="text-sm font-semibold text-[#f1f1f1] truncate">{node.title}</h2>
          <div className="flex gap-3 mt-1 text-[10px] text-[#555]">
            {node.source_count > 0 && <span>{node.source_count} sources</span>}
            {node.backlink_count > 0 && <span>{node.backlink_count} backlinks</span>}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1 text-[#555] hover:text-[#a0a0a0] hover:bg-[#2a2a2a] rounded transition-colors flex-shrink-0"
        >
          <X size={15} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4">
        {isLoading && (
          <div className="flex items-center gap-2 text-[#555] text-sm">
            <Loader2 size={14} className="animate-spin" />
            Loading...
          </div>
        )}

        {isError && (
          <div className="flex items-center gap-2 text-red-400 text-sm">
            <AlertCircle size={14} />
            Could not load page content.
          </div>
        )}

        {data && (
          <div className="prose prose-invert prose-sm max-w-none text-[#c0c0c0]
            prose-headings:text-[#f1f1f1] prose-headings:font-semibold
            prose-h1:text-base prose-h2:text-sm prose-h3:text-xs
            prose-p:leading-relaxed prose-p:text-[#c0c0c0]
            prose-a:text-violet-400 prose-a:no-underline hover:prose-a:underline
            prose-code:text-violet-300 prose-code:bg-[#1e1e1e] prose-code:px-1 prose-code:rounded
            prose-pre:bg-[#1a1a1a] prose-pre:border prose-pre:border-[#2e2e2e]
            prose-strong:text-[#f1f1f1]
            prose-table:text-xs prose-th:text-[#a0a0a0] prose-td:text-[#c0c0c0]
            prose-hr:border-[#2e2e2e]
          ">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Render [[pages/...]] wiki links as buttons
                p: ({ children }) => (
                  <p>{typeof children === 'string' ? renderContent(children) : children}</p>
                ),
              }}
            >
              {data.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
