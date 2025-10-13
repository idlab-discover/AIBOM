import { useCallback, useEffect, useRef, useState } from 'react'
import { DataSet } from 'vis-data'
import type { Node, Edge } from 'vis-network'
import { Network } from 'vis-network'
import 'vis-network/styles/vis-network.css'
import './vis.css'

type GraphData = {
  nodes: Node[]
  edges: Edge[]
  details: Record<string, { cx?: any; cx_file?: string }>
}


const VisNetwork = () => {
  const containerRef = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [physics, setPhysics] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/cx-graph', { cache: 'no-store' })
      const json = (await res.json()) as GraphData
      setData(json)
    } catch (e) {
      console.error('Failed to load graph', e)
    }
  }, [])

  useEffect(() => {
    // initial load
    void load()
  }, [load])

  // Store network instance for dynamic option changes
  const networkRef = useRef<Network | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data) return
    const nodes = new DataSet<Node>(data.nodes)
    const edges = new DataSet<Edge>(data.edges)
    const network = new Network(
      containerRef.current,
      { nodes, edges },
      {
        interaction: { hover: true, dragNodes: true },
        physics,
        layout: { improvedLayout: true, hierarchical: false },
        nodes: { font: { color: '#111', size: 16, face: 'Arial' } },
        edges: { smooth: { enabled: true, type: 'dynamic', roundness: 0.5 } },
      }
    )
    networkRef.current = network
    if (!physics) network.stabilize()
    const onSelect = (params: any) => {
      if (params?.nodes?.length) {
        setSelectedId(String(params.nodes[0]))
      } else {
        setSelectedId(null)
      }
    }
    const onDbl = (params: any) => {
      if (params?.nodes?.length) {
        const id = String(params.nodes[0])
        const d = data.details?.[id]
        const node = data.nodes.find((n: any) => n.id === id)
        if (d?.cx_file && node && node.shape === 'dot' && (node as any).color && ((node as any).color === '#1976d2' || (node as any).color === '#2e7d32')) {
          window.open(`/output/${d.cx_file}`, '_blank')
        }
      }
    }
    network.on('selectNode', onSelect)
    network.on('deselectNode', () => setSelectedId(null))
    network.on('doubleClick', onDbl)
    return () => {
      network.off('selectNode', onSelect)
      network.off('deselectNode', () => setSelectedId(null))
      network.off('doubleClick', onDbl)
      network.destroy()
      networkRef.current = null
    }
  }, [data])


  const selected = selectedId && data ? data.details?.[selectedId] : null
  const selectedNode = selectedId && data ? (data.nodes as any[]).find(n => n.id === selectedId) : null
  const showCxLink = Boolean(selectedId && selected?.cx_file && selectedNode && selectedNode.shape === 'dot' && (selectedNode.color === '#1976d2' || selectedNode.color === '#2e7d32'))

  return (
    <div className="container">
      <div className="graph" ref={containerRef} />
      <div className="panel">
        <h3>Details</h3>
        <div className="links">Click a model or dataset to open full BOM(s).</div>
        <h4>CycloneDX</h4>
        <pre className="pre">
          {selectedId && selected?.cx ? JSON.stringify(selected.cx, null, 2) : 'Select a node...'}
        </pre>
        <div className="links">
          {showCxLink && selected?.cx_file ? (
            <a href={`/output/${selected.cx_file}`} target="_blank" rel="noreferrer">
              Open CycloneDX
            </a>
          ) : null}
          <button className="refresh" onClick={() => void load()} style={{ marginLeft: 8 }}>Refresh graph</button>
          <button
            className="refresh"
            onClick={() => {
              setPhysics(p => {
                const next = !p
                if (networkRef.current) {
                  networkRef.current.setOptions({ physics: next })
                  if (!next) networkRef.current.stabilize()
                }
                return next
              })
            }}
            style={{ marginLeft: 8 }}
          >
            {physics ? 'Disable' : 'Enable'} physics
          </button>
        </div>
      </div>
    </div>
  )
}

export default VisNetwork
