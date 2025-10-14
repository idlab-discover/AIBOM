import { useCallback, useEffect, useRef, useState } from 'react'
import { DataSet } from 'vis-data'
import type { Node, Edge } from 'vis-network'
import { Network } from 'vis-network'
import 'vis-network/styles/vis-network.css'
import 'bootstrap/dist/css/bootstrap.min.css'
import { Tooltip } from 'bootstrap'

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
  // Removed panelOpen state and all collapse logic

  // Bootstrap tooltip for info icons
  const infoIconRef = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    if (infoIconRef.current) {
      new Tooltip(infoIconRef.current, { title: 'Click a model or dataset to open full BOM(s).' })
    }
  }, [])

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
    <div className="container-fluid py-4" style={{ height: '100vh', minHeight: 0 }}>
      <div className="row h-100 flex-nowrap">
        <div className="col-lg-8 col-md-7 d-flex flex-column">
          <div
            ref={containerRef}
            className="border rounded shadow-sm bg-white flex-grow-1"
            style={{ height: '100%', minHeight: 0 }}
          />
        </div>
        <div className="col-lg-4 col-md-5 d-flex flex-column" style={{ height: '100%' }}>
          <div className="card shadow-sm h-100" style={{ width: '100%', minWidth: 0, minHeight: 0, maxHeight: '100%' }}>
            <div className="card-header d-flex align-items-center justify-content-between">
              <span>Details</span>
              <span
                ref={infoIconRef}
                className="ms-2 text-secondary"
                tabIndex={0}
                data-bs-toggle="tooltip"
                data-bs-placement="left"
                style={{ cursor: 'pointer' }}
                aria-label="Info"
              >
                <i className="bi bi-info-circle" />
              </span>
            </div>
            <div className="card-body d-flex flex-column" style={{ minHeight: 0, height: '100%' }}>
              <div className="d-flex align-items-center mt-3 flex-wrap gap-2">
                {showCxLink && selected?.cx_file ? (
                  <a
                    href={`/output/${selected.cx_file}`}
                    target="_blank"
                    rel="noreferrer"
                    className="btn btn-outline-primary btn-sm"
                  >
                    Open CycloneDX
                  </a>
                ) : null}
                <button
                  className="btn btn-outline-secondary btn-sm"
                  onClick={() => void load()}
                >
                  <i className="bi bi-arrow-clockwise me-1" />Refresh graph
                </button>
                <button
                  className="btn btn-outline-info btn-sm"
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
                >
                  <i className={physics ? 'bi bi-pause-circle me-1' : 'bi bi-play-circle me-1'} />
                  {physics ? 'Disable' : 'Enable'} physics
                </button>
              </div>
              <h6 className="mt-3">CycloneDX</h6>
              <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
                <pre className="bg-light rounded p-2" style={{ fontSize: 13, minHeight: 120, flex: 1, overflow: 'auto' }}>
                  {selectedId && selected?.cx ? JSON.stringify(selected.cx, null, 2) : 'Select a node...'}
                </pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default VisNetwork
