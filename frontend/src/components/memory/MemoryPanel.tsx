import { useState } from 'react'
import {
  Brain,
  Trash2,
  RefreshCw,
  Loader2,
  AlertCircle,
  AlertTriangle,
  X,
} from 'lucide-react'
import { useMemory } from '@/hooks/useMemory'

export default function MemoryPanel() {
  const {
    memories,
    total,
    isLoading,
    isError,
    refetch,
    deleteMemory,
    isDeleting,
    deleteAll,
    isDeletingAll,
  } = useMemory()

  const [confirmClearAll, setConfirmClearAll] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleDelete = (memoryId: string) => {
    setDeletingId(memoryId)
    deleteMemory(memoryId, {
      onSettled: () => setDeletingId(null),
    })
  }

  const handleDeleteAll = () => {
    deleteAll(undefined, {
      onSettled: () => setConfirmClearAll(false),
    })
  }

  return (
    <div className="space-y-2">
      {/* Header actions */}
      <div className="flex items-center justify-between px-0.5">
        <span className="text-[10px] text-[#555] font-medium">
          {total > 0 ? `${total} memor${total !== 1 ? 'ies' : 'y'}` : 'No memories yet'}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => void refetch()}
            disabled={isLoading}
            className="p-1 text-[#444] hover:text-[#a0a0a0] transition-colors rounded disabled:opacity-30"
            title="Refresh memories"
          >
            <RefreshCw size={11} className={isLoading ? 'animate-spin' : ''} />
          </button>
          {memories.length > 0 && (
            <button
              onClick={() => setConfirmClearAll(true)}
              disabled={isDeletingAll}
              className="p-1 text-[#444] hover:text-red-400 transition-colors rounded disabled:opacity-30"
              title="Clear all memories"
            >
              {isDeletingAll ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <Trash2 size={11} />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Confirm clear all */}
      {confirmClearAll && (
        <div className="bg-red-900/15 border border-red-900/40 rounded-lg p-2.5 animate-[fadeIn_0.15s_ease-in-out]">
          <div className="flex items-start gap-2 mb-2">
            <AlertTriangle size={12} className="text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-[11px] text-red-300 leading-tight">
              Delete all {total} memories? This cannot be undone.
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleDeleteAll}
              disabled={isDeletingAll}
              className="flex-1 text-[10px] font-medium text-red-400 bg-red-900/30 hover:bg-red-900/50 border border-red-900/40 rounded-md py-1 transition-colors disabled:opacity-50"
            >
              {isDeletingAll ? 'Deleting…' : 'Delete all'}
            </button>
            <button
              onClick={() => setConfirmClearAll(false)}
              className="p-1 text-[#666] hover:text-[#a0a0a0] transition-colors rounded"
            >
              <X size={12} />
            </button>
          </div>
        </div>
      )}

      {/* States */}
      {isLoading && (
        <div className="flex items-center justify-center py-4">
          <Loader2 size={16} className="text-[#555] animate-spin" />
        </div>
      )}

      {isError && (
        <div className="flex items-center gap-1.5 text-[11px] text-red-400/80 bg-red-900/10 border border-red-900/30 rounded-lg px-2.5 py-2">
          <AlertCircle size={12} />
          <span>Failed to load memories</span>
        </div>
      )}

      {!isLoading && !isError && memories.length === 0 && (
        <div className="flex flex-col items-center gap-1.5 py-4">
          <Brain size={20} className="text-[#333]" />
          <p className="text-[11px] text-[#444] text-center">
            Memories appear after conversations
          </p>
        </div>
      )}

      {/* Memory list */}
      {memories.length > 0 && (
        <div className="space-y-1.5 max-h-[280px] overflow-y-auto pr-0.5"
          style={{ scrollbarWidth: 'thin', scrollbarColor: '#2e2e2e transparent' }}
        >
          {memories.map((memory) => (
            <div
              key={memory.id}
              className="flex items-start gap-2 px-2.5 py-2 bg-[#111] border border-[#1e1e1e] rounded-lg group hover:border-[#2a2a2a] transition-colors"
            >
              <div className="w-1.5 h-1.5 rounded-full bg-violet-600/60 flex-shrink-0 mt-1.5" />
              <div className="flex-1 min-w-0">
                <p className="text-[11px] text-[#b0b0b0] leading-relaxed break-words">
                  {memory.memory}
                </p>
                {memory.created_at && (
                  <span className="text-[9px] text-[#444] mt-0.5 block">
                    {formatDate(memory.created_at)}
                  </span>
                )}
              </div>
              <button
                onClick={() => handleDelete(memory.id)}
                disabled={isDeleting && deletingId === memory.id}
                className="p-0.5 text-[#333] hover:text-red-400 opacity-0 group-hover:opacity-100 disabled:opacity-50 transition-all rounded flex-shrink-0"
                title="Delete memory"
              >
                {isDeleting && deletingId === memory.id ? (
                  <Loader2 size={10} className="animate-spin" />
                ) : (
                  <Trash2 size={10} />
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function formatDate(dateStr: string): string {
  try {
    return new Intl.DateTimeFormat('en', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(new Date(dateStr))
  } catch {
    return ''
  }
}
