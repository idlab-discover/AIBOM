import { ArrowPathIcon, PlayIcon, PauseIcon, InformationCircleIcon, ArrowRightIcon } from '@heroicons/react/24/outline'

interface DetailsPanelProps {
    selectedId: string | null
    selected: { cx?: any; cx_file?: string } | null
    selectedNode: any
    showCxLink: boolean
    onRefresh: () => void
    physics: boolean
    onTogglePhysics: () => void
}

const DetailsPanel = ({
    selectedId,
    selected,
    selectedNode,
    showCxLink,
    onRefresh,
    physics,
    onTogglePhysics,
}: DetailsPanelProps) => {


    return (
        <div className="border border-gray-300 bg-white shadow rounded flex flex-col h-full">
            <div className="flex items-center justify-between px-4 py-2 border-b border-gray-300">
                <span className="font-semibold text-lg">Details</span>
                <div className="relative group flex items-center">
                    <InformationCircleIcon className="w-6 h-6 text-gray-500 transition-colors group-hover:text-blue-500" />
                    <div className="absolute right-0 top-full mt-2 z-10 hidden group-hover:block bg-white border border-gray-300 rounded shadow-lg px-3 py-2 text-xs text-gray-700 w-64">
                        Select a node to display its CycloneDX content.<br />Model or Dataset nodes can be fully viewed by double clicking.
                    </div>
                </div>
            </div>
            <div className="flex flex-col flex-1 min-h-0 px-4 py-2">
                <div className="flex flex-wrap items-center gap-2 mt-2">

                    <button
                        className="px-2 py-1 text-xs rounded border border-gray-400 text-gray-700 hover:bg-gray-100 flex items-center gap-1 cursor-pointer"
                        onClick={onRefresh}
                    >
                        <ArrowPathIcon className="w-4 h-4" />
                        Refresh graph
                    </button>
                    <button
                        className="px-2 py-1 text-xs rounded border border-cyan-400 text-cyan-700 hover:bg-cyan-50 flex items-center gap-1 cursor-pointer"
                        onClick={onTogglePhysics}
                    >
                        {physics ? <PauseIcon className="w-4 h-4" /> : <PlayIcon className="w-4 h-4" />}
                        {physics ? 'Disable' : 'Enable'} physics
                    </button>
                    {showCxLink && selected?.cx_file ? (
                        <button
                            onClick={() => window.open(`/output/${selected.cx_file}`, '_blank')}
                            className="px-2 py-1 text-xs rounded border border-blue-500 text-blue-700 hover:bg-blue-50 flex items-center gap-1 cursor-pointer"
                        >
                            Full AIBOM of "{selectedId}"
                            <ArrowRightIcon className="w-4 h-4" />
                        </button>
                    ) : null}
                </div>
                <div className="mt-3 font-semibold text-sm">CycloneDX</div>
                <div className="flex-1 min-h-0 overflow-auto flex flex-col">
                    <pre className="bg-gray-100 rounded p-3 text-xs flex-1 overflow-auto">
                        {selectedId && selected?.cx ? JSON.stringify(selected.cx, null, 2) : 'Select a node...'}
                    </pre>
                </div>
            </div>
        </div>
    )
}

export default DetailsPanel
