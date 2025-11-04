
import { useCallback, useEffect, useRef, useState } from 'react'
import 'vis-network/styles/vis-network.css'
// Removed Bootstrap import
import NetworkGraph from './NetworkGraph'
import DetailsPanel from './DetailsPanel'
import type { GraphData } from '../types/GraphData'

const HomePage = () => {
  const [data, setData] = useState<GraphData | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [physics, setPhysics] = useState(false)
  const networkRef = useRef<any>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/cx-graph', { cache: 'no-store' })
      const json = (await res.json()) as GraphData
      setData(json)
      setSelectedId(null)
    } catch (e) {
      console.error('Failed to load graph', e)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const handleSelect = (id: string | null) => {
    setSelectedId(id)
  }

  const handleDblClick = (id: string) => {
    if (!data) return
    const d = data.details?.[id]
    const node = data.nodes.find((n: any) => n.id === id)
    if (d?.cx_file && node && node.shape === 'dot' && (node as any).color && ((node as any).color === '#1976d2' || (node as any).color === '#2e7d32')) {
      window.open(`/output/${d.cx_file}`, '_blank')
    }
  }

  const selected = selectedId && data ? data.details?.[selectedId] : null
  const selectedNode = selectedId && data ? (data.nodes as any[]).find(n => n.id === selectedId) : null
  const showCxLink = Boolean(selectedId && selected?.cx_file && selectedNode && selectedNode.shape === 'dot' && (selectedNode.color === '#1976d2' || selectedNode.color === '#2e7d32'))

  const handleTogglePhysics = () => {
    setPhysics(p => {
      const next = !p
      if (networkRef.current) {
        networkRef.current.setOptions({ physics: next })
        if (!next) networkRef.current.stabilize()
      }
      return next
    })
  }


  return (
    <div className="w-full h-screen py-4 px-2">
      <div className="flex flex-col lg:flex-row h-full gap-4">
        {/* On mobile: stack vertically, each takes 50% height. On desktop: side by side. */}
        <div className="flex-1 flex flex-col min-h-0 h-1/2 lg:h-full">
          {data && (
            <div className="flex-1 h-full">
              <NetworkGraph
                data={data}
                physics={physics}
                onSelect={handleSelect}
                onDblClick={handleDblClick}
                networkRef={networkRef}
              />
            </div>
          )}
        </div>
        <div className="w-full lg:w-1/3 flex flex-col min-h-[200px] h-1/2 lg:h-full">
          <div className="flex-1 overflow-y-auto min-h-0">
            <DetailsPanel
              selectedId={selectedId}
              selected={selected}
              selectedNode={selectedNode}
              showCxLink={showCxLink}
              onRefresh={load}
              physics={physics}
              onTogglePhysics={handleTogglePhysics}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

export default HomePage
