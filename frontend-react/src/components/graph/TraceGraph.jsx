/**
 * TraceGraph — React Flow DAG for a single trace's execution graph.
 *
 * Props:
 *   graph      — { nodes, edges, critical_path } from GET /api/traces/:id/graph
 *   onNodeClick — (node) => void
 */
import { useMemo, useCallback, useEffect } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Position,
  MarkerType,
  Handle,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { KindBadge } from '../ui/Badge'
import { fmtDuration } from '../../utils/format'

// ─── Custom node renderer ────────────────────────────────────────────────────
function SpanNode({ data, selected }) {
  const isErr     = (data.status || '').toUpperCase() === 'ERROR'
  const isAnomaly = data.is_anomalous
  const isCritical = data.is_critical_path
  return (
    <div
      className={[
        'rf-node',
        isErr       ? 'rf-node--error'    : '',
        isAnomaly   ? 'rf-node--anomaly'  : '',
        isCritical  ? 'rf-node--critical' : '',
        selected    ? 'rf-node--selected' : '',
      ].filter(Boolean).join(' ')}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#64748b' }} />
      <div className="rf-node-header">
        <KindBadge kind={data.kind} />
        {isAnomaly && <span className="rf-node-alert" title="Anomalous">⚠</span>}
      </div>
      <div className="rf-node-name" title={data.label}>{data.label}</div>
      <div className="rf-node-duration">{fmtDuration(data.duration_ms)}</div>
      <Handle type="source" position={Position.Right} style={{ background: '#64748b' }} />
    </div>
  )
}

const NODE_TYPES = { span: SpanNode }

// ─── BFS layout (left→right tree) ────────────────────────────────────────────
function computeLayout(rawNodes, rawEdges) {
  const NODE_W = 160, NODE_H = 72, H_GAP = 80, V_GAP = 20
  const children = {}
  const parentCount = {}

  rawNodes.forEach((n) => { children[n.span_id] = []; parentCount[n.span_id] = 0 })
  rawEdges.forEach((e) => {
    children[e.source]?.push(e.target)
    if (e.target in parentCount) parentCount[e.target]++
  })

  // Roots = nodes with no parents
  const roots = rawNodes.filter((n) => parentCount[n.span_id] === 0).map((n) => n.span_id)
  const xByNode = {}
  const yByNode = {}
  const levelNodes = []

  // BFS
  let queue = roots.slice()
  let col = 0
  while (queue.length) {
    levelNodes[col] = queue.slice()
    const next = []
    queue.forEach((id) => (children[id] || []).forEach((c) => {
      if (!(c in xByNode)) next.push(c)
    }))
    queue = [...new Set(next)]
    col++
  }

  levelNodes.forEach((ids, depth) => {
    ids.forEach((id, i) => {
      xByNode[id] = depth * (NODE_W + H_GAP)
      yByNode[id] = i * (NODE_H + V_GAP)
    })
  })

  return rawNodes.map((n) => ({
    id: n.span_id,
    type: 'span',
    position: { x: xByNode[n.span_id] ?? 0, y: yByNode[n.span_id] ?? 0 },
    data: {
      label:          n.name ?? n.span_id,
      kind:           n.kind,
      status:         n.status,
      duration_ms:    n.duration_ms,
      is_anomalous:   n.is_anomalous,
      is_critical_path: n.is_critical_path,
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }))
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function TraceGraph({ graph, onNodeClick }) {
  const rfNodes = useMemo(() => {
    if (!graph?.nodes) return []
    return computeLayout(graph.nodes, graph.edges ?? [])
  }, [graph])

  const rfEdges = useMemo(() => {
    if (!graph?.edges) return []
    const cp = new Set(graph.critical_path ?? [])
    return graph.edges.map((e) => {
      const onCP = cp.has(e.source) && cp.has(e.target)
      return {
        id:       `e-${e.source}-${e.target}`,
        source:   e.source,
        target:   e.target,
        type:     'smoothstep',
        animated: onCP,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: onCP ? '#f97316' : '#64748b',
          width: 16,
          height: 16,
        },
        style:    {
          stroke: onCP ? '#f97316' : '#64748b',
          strokeWidth: onCP ? 2.5 : 1.5,
        },
        label: e.label ?? undefined,
      }
    })
  }, [graph])

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges)

  useEffect(() => {
    setNodes(rfNodes)
    setEdges(rfEdges)
  }, [rfNodes, rfEdges, setNodes, setEdges])

  const handleNodeClick = useCallback(
    (_e, node) => onNodeClick?.(node),
    [onNodeClick]
  )

  if (!graph) return (
    <div className="graph-empty">Select a trace to visualise its execution graph.</div>
  )

  return (
    <div className="graph-container">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} color="var(--border)" />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={(n) => (n.data?.is_anomalous ? 'var(--orange)' : 'var(--blue)')}
          maskColor="rgba(0,0,0,0.5)"
          style={{ background: 'var(--bg-card)' }}
        />
      </ReactFlow>

      {/* Legend */}
      <div className="graph-legend">
        <span className="legend-item" style={{ color: 'var(--orange)' }}>━ Critical path</span>
        <span className="legend-item" style={{ color: 'var(--border)' }}>━ Dependency</span>
        <span className="legend-item">⚠ Anomaly</span>
      </div>
    </div>
  )
}
