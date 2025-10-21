import { useEffect, useRef } from 'react'
import { DataSet } from 'vis-data'
import type { Node, Edge } from 'vis-network'
import { Network } from 'vis-network'
import type { GraphData } from '../types/GraphData'

interface NetworkGraphProps {
    data: GraphData
    physics: boolean
    onSelect: (id: string | null) => void
    onDblClick: (id: string) => void
    networkRef: React.RefObject<Network | null>
}

const NetworkGraph = ({ data, physics, onSelect, onDblClick, networkRef }: NetworkGraphProps) => {
    const containerRef = useRef<HTMLDivElement>(null)

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
                edges: { smooth: { enabled: true, type: 'continuous', roundness: 0 } },
            }
        )
        networkRef.current = network
        if (!physics) network.stabilize()
        const handleSelect = (params: any) => {
            if (params?.nodes?.length) {
                onSelect(String(params.nodes[0]))
            } else {
                onSelect(null)
            }
        }
        const handleDblClick = (params: any) => {
            if (params?.nodes?.length) {
                onDblClick(String(params.nodes[0]))
            }
        }
        network.on('selectNode', handleSelect)
        network.on('deselectNode', () => onSelect(null))
        network.on('doubleClick', handleDblClick)
        return () => {
            network.off('selectNode', handleSelect)
            network.off('deselectNode', () => onSelect(null))
            network.off('doubleClick', handleDblClick)
            network.destroy()
            networkRef.current = null
        }
    }, [data])

    // Update physics without recreating the network
    useEffect(() => {
        if (networkRef.current) {
            networkRef.current.setOptions({ physics })
            if (!physics) networkRef.current.stabilize()
        }
    }, [physics, networkRef])

    return (
        <div
            ref={containerRef}
            className="border border-gray-300 rounded bg-white flex-1 h-full"
        />
    )
}

export default NetworkGraph
