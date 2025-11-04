import type { Node, Edge } from 'vis-network'

export type GraphData = {
  nodes: Node[]
  edges: Edge[]
  details: Record<string, { cx?: any; cx_file?: string }>
}