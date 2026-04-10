/** Màu sắc cho từng loại entity/concept trong wiki graph. */
export const NODE_TYPE_COLORS: Record<string, string> = {
  model:      '#3b82f6', // blue
  method:     '#22c55e', // green
  concept:    '#a855f7', // purple
  framework:  '#f97316', // orange
  dataset:    '#eab308', // yellow
  benchmark:  '#06b6d4', // cyan
  researcher: '#ec4899', // pink
  lab:        '#ef4444', // red
  tool:       '#14b8a6', // teal
  topic:      '#6366f1', // indigo
  summary:    '#6b7280', // gray
}

export const DEFAULT_NODE_COLOR = '#6b7280'

export function getNodeColor(type: string): string {
  return NODE_TYPE_COLORS[type] ?? DEFAULT_NODE_COLOR
}
