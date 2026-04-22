import { useCallback, useEffect, useRef } from 'react'
import type { Node, Edge } from '@xyflow/react'

interface LayoutResult {
  layoutedNodes: Node[]
}

/**
 * Hook to apply dagre layout using a Web Worker.
 * Falls back to sync computation if workers are not supported.
 */
export function useGraphLayout() {
  const workerRef = useRef<Worker | null>(null)
  // Use ref instead of state to avoid triggering re-renders and re-creating applyLayout
  const isLayoutReady = useRef(true)
  const pendingCallback = useRef<((nodes: Node[]) => void) | null>(null)

  useEffect(() => {
    // Initialize worker
    try {
      workerRef.current = new Worker(
        new URL('../workers/graphLayout.worker.ts', import.meta.url),
        { type: 'module' }
      )

      workerRef.current.onmessage = (e: MessageEvent<LayoutResult>) => {
        if (pendingCallback.current) {
          pendingCallback.current(e.data.layoutedNodes)
          pendingCallback.current = null
        }
        isLayoutReady.current = true
      }

      workerRef.current.onerror = (err) => {
        console.error('Graph layout worker error:', err)
        isLayoutReady.current = true
      }
    } catch {
      console.warn('Web Workers not supported, using sync layout')
    }

    return () => {
      workerRef.current?.terminate()
    }
  }, [])

  // Stable reference — never changes because no state deps
  const applyLayout = useCallback(
    (nodes: Node[], edges: Edge[], callback: (layoutedNodes: Node[]) => void) => {
      if (workerRef.current && isLayoutReady.current) {
        isLayoutReady.current = false
        pendingCallback.current = callback
        workerRef.current.postMessage({ nodes, edges })
      } else {
        // Fallback to sync
        import('@/utils/wikiGraphLayout').then(({ applyDagreLayout }) => {
          const layoutedNodes = applyDagreLayout(nodes, edges)
          callback(layoutedNodes)
        })
      }
    },
    []
  )

  return { applyLayout }
}
