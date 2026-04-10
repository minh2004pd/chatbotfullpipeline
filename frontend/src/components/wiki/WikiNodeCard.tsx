import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { WikiGraphNode } from '@/types'
import { getNodeColor } from '@/utils/wikiNodeColors'

export const WikiNodeCard = memo(({ data, selected }: NodeProps) => {
  const node = data as unknown as WikiGraphNode
  const color = getNodeColor(node.type)

  return (
    <div
      className={`
        px-3 py-2 rounded-lg border text-xs cursor-pointer select-none
        transition-all duration-150 min-w-[120px] max-w-[160px]
        ${selected
          ? 'border-white/60 shadow-lg shadow-black/40'
          : 'border-white/10 hover:border-white/30'
        }
      `}
      style={{ background: `${color}22`, borderColor: selected ? color : undefined }}
    >
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !border-0" style={{ background: color }} />

      {/* Type badge */}
      <div className="flex items-center gap-1.5 mb-1">
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ background: color }}
        />
        <span className="text-[10px] uppercase tracking-wider font-medium truncate" style={{ color }}>
          {node.type}
        </span>
      </div>

      {/* Title */}
      <div className="text-[#f1f1f1] font-medium leading-tight text-[11px] line-clamp-2">
        {node.title}
      </div>

      {/* Stats */}
      {(node.source_count > 0 || node.backlink_count > 0) && (
        <div className="flex gap-2 mt-1.5 text-[#666]" style={{ fontSize: '9px' }}>
          {node.source_count > 0 && <span>{node.source_count} src</span>}
          {node.backlink_count > 0 && <span>{node.backlink_count} links</span>}
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !border-0" style={{ background: color }} />
    </div>
  )
})

WikiNodeCard.displayName = 'WikiNodeCard'
