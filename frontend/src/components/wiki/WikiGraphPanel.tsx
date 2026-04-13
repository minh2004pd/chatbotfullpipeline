import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { RefreshCw, Loader2, AlertCircle, ChevronDown, X, FileText } from 'lucide-react'

import type { WikiGraphNode } from '@/types'
import { useWikiGraph } from '@/hooks/useWikiGraph'
import { useChatStore } from '@/store/chatStore'
import { useDocuments } from '@/hooks/useDocuments'
import { applyDagreLayout } from '@/utils/wikiGraphLayout'
import { getNodeColor } from '@/utils/wikiNodeColors'
import { WikiNodeCard } from './WikiNodeCard'
import WikiPageDrawer from './WikiPageDrawer'

const nodeTypes = { wikiNode: WikiNodeCard }

function toWikiNode(node: Node): WikiGraphNode {
  return node.data as unknown as WikiGraphNode
}

export default function WikiGraphPanel() {
  const userId = useChatStore((s) => s.userId)
  const activeWikiNodes = useChatStore((s) => s.activeWikiNodes)
  const [showSummaries, setShowSummaries] = useState(false)
  const [showStubs, setShowStubs] = useState(false)
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [selectedNode, setSelectedNode] = useState<WikiGraphNode | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const { documents } = useDocuments()

  const { data, isLoading, isError, refetch, isFetching } = useWikiGraph({
    userId,
    showStubs,
    showSummaries,
    sourceIds: selectedSourceIds,
  })

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Element)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Rebuild graph khi data hoặc activeWikiNodes thay đổi
  useEffect(() => {
    if (!data) return

    const rfNodes: Node[] = data.nodes.map((n) => ({
      id: n.key,   // unique key = "{category}/{slug}"
      type: 'wikiNode',
      position: { x: 0, y: 0 },
      data: { ...n, isActive: activeWikiNodes.includes(n.key) } as unknown as Record<string, unknown>,
      selected: selectedNode?.key === n.key,
    }))

    const rfEdges: Edge[] = data.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      style: { stroke: '#3a3a3a', strokeWidth: 1.5 },
      animated: false,
    }))

    setNodes(applyDagreLayout(rfNodes, rfEdges))
    setEdges(rfEdges)
  }, [data, activeWikiNodes]) // eslint-disable-line react-hooks/exhaustive-deps

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    const wikiNode = toWikiNode(node)
    setSelectedNode((prev) => (prev?.key === wikiNode.key ? null : wikiNode))
  }, [])

  const onPaneClick = useCallback(() => setSelectedNode(null), [])

  const handleNavigate = useCallback(
    (slug: string, category: string) => {
      const target = data?.nodes.find((n) => n.id === slug && n.category === category)
      if (target) setSelectedNode(target)
    },
    [data],
  )

  const miniMapNodeColor = useCallback((node: Node) => getNodeColor(toWikiNode(node).type), [])

  const legend = useMemo(() => {
    if (!data) return []
    const seen = new Set<string>()
    return data.nodes.map((n) => n.type).filter((t) => {
      if (seen.has(t)) return false
      seen.add(t)
      return true
    })
  }, [data])

  const toggleSource = (id: string) => {
    setSelectedSourceIds((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id],
    )
  }

  const sourceLabel = useMemo(() => {
    if (selectedSourceIds.length === 0) return 'All sources'
    if (selectedSourceIds.length === 1) {
      const doc = documents.find((d) => d.document_id === selectedSourceIds[0])
      return doc?.filename ?? '1 source'
    }
    return `${selectedSourceIds.length} sources`
  }, [selectedSourceIds, documents])

  return (
    <div className="flex h-full w-full bg-[#0f0f0f]">
      {/* Graph canvas */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#2e2e2e] flex-shrink-0 bg-[#111111]">
          <span className="text-xs font-semibold text-[#a0a0a0] uppercase tracking-wider flex-shrink-0">
            Knowledge Graph
          </span>
          {data && (
            <span className="text-[10px] text-[#555] flex-shrink-0">
              {data.nodes.length} nodes · {data.edges.length} edges
            </span>
          )}

          <div className="flex-1" />

          {/* Source filter dropdown */}
          <div className="relative flex-shrink-0" ref={dropdownRef}>
            <button
              onClick={() => setDropdownOpen((v) => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded border text-[11px] transition-colors ${
                selectedSourceIds.length > 0
                  ? 'border-violet-600/60 text-violet-300 bg-violet-900/20'
                  : 'border-[#2e2e2e] text-[#666] hover:text-[#a0a0a0] hover:border-[#444]'
              }`}
            >
              <FileText size={11} />
              <span className="max-w-[120px] truncate">{sourceLabel}</span>
              <ChevronDown size={10} className={dropdownOpen ? 'rotate-180' : ''} />
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 top-full mt-1 w-56 bg-[#1a1a1a] border border-[#2e2e2e] rounded-lg shadow-xl z-50 overflow-hidden">
                {/* All sources option */}
                <button
                  onClick={() => { setSelectedSourceIds([]); setDropdownOpen(false) }}
                  className={`w-full flex items-center gap-2 px-3 py-2 text-[11px] text-left transition-colors hover:bg-[#252525] ${
                    selectedSourceIds.length === 0 ? 'text-violet-300' : 'text-[#a0a0a0]'
                  }`}
                >
                  <div className={`w-3 h-3 rounded border flex-shrink-0 flex items-center justify-center ${
                    selectedSourceIds.length === 0 ? 'bg-violet-600 border-violet-600' : 'border-[#444]'
                  }`}>
                    {selectedSourceIds.length === 0 && <span className="text-white text-[8px]">✓</span>}
                  </div>
                  All sources
                </button>

                {documents.length > 0 && <div className="border-t border-[#2e2e2e]" />}

                {/* Per-document options */}
                {documents.map((doc) => {
                  const checked = selectedSourceIds.includes(doc.document_id)
                  return (
                    <button
                      key={doc.document_id}
                      onClick={() => toggleSource(doc.document_id)}
                      className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-left hover:bg-[#252525] transition-colors"
                    >
                      <div className={`w-3 h-3 rounded border flex-shrink-0 flex items-center justify-center ${
                        checked ? 'bg-violet-600 border-violet-600' : 'border-[#444]'
                      }`}>
                        {checked && <span className="text-white text-[8px]">✓</span>}
                      </div>
                      <span className={`truncate ${checked ? 'text-violet-300' : 'text-[#a0a0a0]'}`}>
                        {doc.filename}
                      </span>
                    </button>
                  )
                })}

                {documents.length === 0 && (
                  <div className="px-3 py-2 text-[10px] text-[#444]">No documents uploaded</div>
                )}
              </div>
            )}
          </div>

          {/* Clear source filter */}
          {selectedSourceIds.length > 0 && (
            <button
              onClick={() => setSelectedSourceIds([])}
              className="p-1 rounded text-[#555] hover:text-[#a0a0a0] hover:bg-[#2a2a2a] transition-colors"
              title="Clear filter"
            >
              <X size={12} />
            </button>
          )}

          {/* Other filters */}
          <label className="flex items-center gap-1.5 text-[11px] text-[#666] cursor-pointer select-none hover:text-[#a0a0a0] transition-colors flex-shrink-0">
            <input
              type="checkbox"
              checked={showSummaries}
              onChange={(e) => setShowSummaries(e.target.checked)}
              className="w-3 h-3 rounded accent-violet-500"
            />
            Summaries
          </label>
          <label className="flex items-center gap-1.5 text-[11px] text-[#666] cursor-pointer select-none hover:text-[#a0a0a0] transition-colors flex-shrink-0">
            <input
              type="checkbox"
              checked={showStubs}
              onChange={(e) => setShowStubs(e.target.checked)}
              className="w-3 h-3 rounded accent-violet-500"
            />
            Stubs
          </label>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-1.5 rounded text-[#555] hover:text-[#a0a0a0] hover:bg-[#2a2a2a] transition-colors disabled:opacity-50 flex-shrink-0"
            title="Refresh graph"
          >
            <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* States */}
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
            <div className="flex items-center gap-2 text-[#555] text-sm">
              <Loader2 size={16} className="animate-spin" />
              Building knowledge graph...
            </div>
          </div>
        )}

        {isError && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="flex flex-col items-center gap-2 text-red-400 text-sm">
              <AlertCircle size={20} />
              <span>Failed to load graph</span>
              <button onClick={() => refetch()} className="text-xs text-[#666] hover:text-[#a0a0a0] underline mt-1">
                Try again
              </button>
            </div>
          </div>
        )}

        {!isLoading && !isError && data?.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
            <div className="text-center text-[#444]">
              <div className="text-4xl mb-3">🕸️</div>
              <div className="text-sm">
                {selectedSourceIds.length > 0 ? 'No knowledge found for selected sources' : 'No knowledge yet'}
              </div>
              <div className="text-xs mt-1">
                {selectedSourceIds.length > 0
                  ? 'Try selecting different sources or clear the filter'
                  : 'Upload documents or record meetings to build the graph'}
              </div>
            </div>
          </div>
        )}

        {/* React Flow */}
        <div className="flex-1 min-h-0">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.2}
            maxZoom={2}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#2a2a2a" gap={24} variant={BackgroundVariant.Dots} />
            <Controls className="!bg-[#1a1a1a] !border-[#2e2e2e] !rounded-lg" showInteractive={false} />
            <MiniMap
              nodeColor={miniMapNodeColor}
              className="!bg-[#111111] !border-[#2e2e2e] !rounded-lg"
              maskColor="rgba(0,0,0,0.6)"
            />
          </ReactFlow>
        </div>

        {/* Legend */}
        {legend.length > 0 && (
          <div className="absolute bottom-16 left-3 flex flex-wrap gap-1.5 max-w-xs pointer-events-none">
            {legend.map((type) => (
              <span
                key={type}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] bg-[#111111]/80 border border-[#2e2e2e]"
                style={{ color: getNodeColor(type) }}
              >
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: getNodeColor(type) }} />
                {type}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Page drawer */}
      {selectedNode && (
        <div className="w-80 flex-shrink-0">
          <WikiPageDrawer
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onNavigate={handleNavigate}
          />
        </div>
      )}
    </div>
  )
}
