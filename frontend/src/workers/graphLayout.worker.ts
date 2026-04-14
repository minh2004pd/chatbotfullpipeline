import dagre from '@dagrejs/dagre'
import type { Node, Edge } from '@xyflow/react'

const NODE_WIDTH = 160
const NODE_HEIGHT = 48

/**
 * Web Worker for computing dagre layout positions.
 * This prevents blocking the main thread during graph layout computation.
 */
self.onmessage = (e: MessageEvent<{ nodes: Node[]; edges: Edge[] }>) => {
  const { nodes, edges } = e.data

  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: 100 })

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT }))
  edges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  // Return full node objects with updated positions
  const layoutedNodes = nodes.map((n) => {
    const pos = g.node(n.id)
    return {
      ...n,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })

  self.postMessage({ layoutedNodes })
}

