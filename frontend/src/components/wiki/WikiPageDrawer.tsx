import { X, Loader2, AlertCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import '@/styles/katex-dark.css'
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

  // Preprocess markdown: strip frontmatter, source citations, convert [[wiki links]]
  const processContent = (raw: string): string => {
    // Strip YAML frontmatter between --- markers
    let content = raw.replace(/^---\n[\s\S]*?\n---\n?/, '')
    // Remove source citation UUIDs like [813c6abc-ccf4-...]
    content = content.replace(/\s*\[[0-9a-f]{8}-[0-9a-f-]{27}\]/g, '')
    // Convert [[pages/category/slug.md]] → markdown link [slug](wiki:category/slug)
    content = content.replace(
      /\[\[pages\/([^/\]]+)\/([^\]]+?)\.md\]\]/g,
      (_, cat, slug) => `[${slug.replace(/-/g, ' ')}](wiki:${cat}/${encodeURIComponent(slug)})`
    )
    return content
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
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={{
                a: ({ href, children }) => {
                  if (href?.startsWith('wiki:')) {
                    const rest = href.slice(5)
                    const slashIdx = rest.indexOf('/')
                    const cat = rest.slice(0, slashIdx)
                    const slug = decodeURIComponent(rest.slice(slashIdx + 1))
                    return (
                      <button
                        onClick={() => onNavigate(slug, cat)}
                        className="text-violet-400 hover:text-violet-300 underline underline-offset-2 cursor-pointer font-medium"
                      >
                        {children}
                      </button>
                    )
                  }
                  return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                },
              }}
            >
              {processContent(data.content)}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
