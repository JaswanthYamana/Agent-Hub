/**
 * ExecutionGraph — Enhanced DAG visualization with advanced features
 *
 * Features:
 * - Interactive execution trajectory visualization
 * - Node statistics and detailed span information
 * - Critical path highlighting
 * - Performance metrics overlay
 * - Export capabilities
 *
 * Props:
 *   graph      — { nodes, edges, critical_path } from GET /api/traces/:id/graph
 *   onNodeClick — (node) => void
 *   traceId    — string (for reference)
 */
import { useMemo, useCallback, useEffect, useState } from 'react'
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
import { fmtDuration, short } from '../../utils/format'
import './ExecutionGraph.css'

// ─── Enhanced Custom Node Renderer ────────────────────────────────────────────
function EnhancedSpanNode({ data, selected }) {
  const isErr = (data.status || '').toUpperCase() === 'ERROR'
  const isAnomaly = data.is_anomalous
  const isCritical = data.is_critical_path
  const isPending = (data.status || '').toUpperCase() === 'PENDING'

  return (
    <div
      className={[
        'eg-node',
        isErr ? 'eg-node--error' : '',
        isAnomaly ? 'eg-node--anomaly' : '',
        isCritical ? 'eg-node--critical' : '',
        isPending ? 'eg-node--pending' : '',
        selected ? 'eg-node--selected' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      title={data.label}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: '#64748b' }}
      />
      <div className="eg-node-header">
        <KindBadge kind={data.kind} />
        {isAnomaly && (
          <span className="eg-node-alert" title="Anomalous">
            ⚠
          </span>
        )}
        {isErr && (
          <span className="eg-node-error" title="Error">
            ✕
          </span>
        )}
      </div>
      <div className="eg-node-name">{data.label}</div>
      <div className="eg-node-meta">
        <span className="eg-node-duration" title="Duration">
          {fmtDuration(data.duration_ms)}
        </span>
        {data.token_count && (
          <span className="eg-node-tokens" title="Tokens">
            {data.token_count}T
          </span>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: '#64748b' }}
      />
    </div>
  )
}

const NODE_TYPES = { span: EnhancedSpanNode }

// ─── Advanced Layout Algorithm (DAG with level assignment) ────────────────────
function computeLayout(rawNodes, rawEdges) {
  const NODE_W = 180
  const NODE_H = 90
  const H_GAP = 100
  const V_GAP = 25

  const children = {}
  const parents = {}
  const parentCount = {}
  const levels = {}

  rawNodes.forEach((n) => {
    children[n.span_id] = []
    parents[n.span_id] = []
    parentCount[n.span_id] = 0
    levels[n.span_id] = 0
  })

  rawEdges.forEach((e) => {
    children[e.source]?.push(e.target)
    parents[e.target]?.push(e.source)
    if (e.target in parentCount) parentCount[e.target]++
  })

  // Topological sort to assign levels
  const visited = new Set()
  const queue = rawNodes
    .filter((n) => parentCount[n.span_id] === 0)
    .map((n) => n.span_id)

  while (queue.length > 0) {
    const nodeId = queue.shift()
    visited.add(nodeId)

    const childrenIds = children[nodeId] || []
    childrenIds.forEach((childId) => {
      levels[childId] = Math.max(levels[childId] || 0, (levels[nodeId] || 0) + 1)
      const unvisitedParents = (parents[childId] || []).filter((p) => !visited.has(p))
      if (unvisitedParents.length === 0) {
        queue.push(childId)
      }
    })
  }

  // Group nodes by level
  const nodesByLevel = {}
  rawNodes.forEach((n) => {
    const lvl = levels[n.span_id] || 0
    if (!nodesByLevel[lvl]) nodesByLevel[lvl] = []
    nodesByLevel[lvl].push(n.span_id)
  })

  const xByNode = {}
  const yByNode = {}

  Object.entries(nodesByLevel).forEach(([level, nodeIds]) => {
    const lvl = parseInt(level, 10)
    nodeIds.forEach((id, i) => {
      xByNode[id] = lvl * (NODE_W + H_GAP)
      yByNode[id] = i * (NODE_H + V_GAP)
    })
  })

  return rawNodes.map((n) => ({
    id: n.span_id,
    type: 'span',
    position: { x: xByNode[n.span_id] ?? 0, y: yByNode[n.span_id] ?? 0 },
    data: {
      label: n.name ?? n.span_id,
      kind: n.kind,
      status: n.status,
      duration_ms: n.duration_ms,
      token_count: n.token_count,
      is_anomalous: n.is_anomalous,
      is_critical_path: n.is_critical_path,
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }))
}

// ─── Statistics Computation ────────────────────────────────────────────────────
function computeStats(nodes, edges) {
  if (!nodes || nodes.length === 0) {
    return {
      totalNodes: 0,
      totalDuration: 0,
      criticalPathLength: 0,
      errorCount: 0,
      anomalyCount: 0,
    }
  }

  const totalDuration = nodes.reduce((sum, n) => sum + (n.duration_ms || 0), 0)
  const errorCount = nodes.filter((n) => (n.status || '').toUpperCase() === 'ERROR').length
  const anomalyCount = nodes.filter((n) => n.is_anomalous).length

  return {
    totalNodes: nodes.length,
    totalDuration,
    criticalPathLength: edges?.length || 0,
    errorCount,
    anomalyCount,
  }
}

// ─── Main Component ───────────────────────────────────────────────────────────
export default function ExecutionGraph({ graph, onNodeClick, traceId }) {
  const [showStats, setShowStats] = useState(true)
  const [showLegend, setShowLegend] = useState(true)

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
        id: `e-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
        animated: onCP,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: onCP ? '#f97316' : '#64748b',
          width: 16,
          height: 16,
        },
        style: {
          stroke: onCP ? '#f97316' : '#64748b',
          strokeWidth: onCP ? 2.5 : 1.5,
        },
        label: e.label ?? undefined,
      }
    })
  }, [graph])

  const stats = useMemo(
    () => computeStats(graph?.nodes, graph?.edges),
    [graph?.nodes, graph?.edges]
  )

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

  const handleExport = useCallback(() => {
    if (!graph) return
    const dataStr = JSON.stringify(
      {
        trace_id: traceId,
        export_date: new Date().toISOString(),
        stats,
        graph,
      },
      null,
      2
    )
    const dataBlob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `trace-${traceId}-graph-${Date.now()}.json`
    link.click()
    URL.revokeObjectURL(url)
  }, [graph, traceId, stats])

  if (!graph) {
    return (
      <div className="eg-empty">
        <p>Select a trace to visualize its execution graph.</p>
      </div>
    )
  }

  return (
    <div className="eg-container">
      {/* Header Controls */}
      <div className="eg-controls">
        <div className="eg-controls-left">
          <button
            className="eg-control-btn"
            title={showStats ? 'Hide statistics' : 'Show statistics'}
            onClick={() => setShowStats(!showStats)}
          >
            {showStats ? '📊' : '◯'}
          </button>
          <button
            className="eg-control-btn"
            title={showLegend ? 'Hide legend' : 'Show legend'}
            onClick={() => setShowLegend(!showLegend)}
          >
            {showLegend ? '🔤' : '◯'}
          </button>
        </div>
        <div className="eg-controls-right">
          <button
            className="eg-control-btn"
            title="Export graph data"
            onClick={handleExport}
          >
            💾
          </button>
        </div>
      </div>

      {/* Main Graph Canvas */}
      <div className="eg-graph-wrapper">
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
          maxZoom={3}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} color="var(--border, #e0e0e0)" />
          <Controls showInteractive={false} />
          <MiniMap
            nodeColor={(n) => {
              if (n.data?.is_anomalous) return '#ff9800'
              if ((n.data?.status || '').toUpperCase() === 'ERROR')
                return '#f44336'
              return '#2196f3'
            }}
            maskColor="rgba(0, 0, 0, 0.3)"
            style={{ background: 'var(--bg-card, #fff)' }}
          />
        </ReactFlow>
      </div>

      {/* Statistics Panel */}
      {showStats && (
        <div className="eg-stats-panel">
          <div className="eg-stats-header">Graph Statistics</div>
          <div className="eg-stats-grid">
            <div className="eg-stat-item">
              <span className="eg-stat-label">Nodes</span>
              <span className="eg-stat-value">{stats.totalNodes}</span>
            </div>
            <div className="eg-stat-item">
              <span className="eg-stat-label">Total Duration</span>
              <span className="eg-stat-value">{fmtDuration(stats.totalDuration)}</span>
            </div>
            <div className="eg-stat-item">
              <span className="eg-stat-label">Errors</span>
              <span className={`eg-stat-value ${stats.errorCount > 0 ? 'eg-error' : ''}`}>
                {stats.errorCount}
              </span>
            </div>
            <div className="eg-stat-item">
              <span className="eg-stat-label">Anomalies</span>
              <span className={`eg-stat-value ${stats.anomalyCount > 0 ? 'eg-warning' : ''}`}>
                {stats.anomalyCount}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Legend */}
      {showLegend && (
        <div className="eg-legend">
          <div className="eg-legend-title">Legend</div>
          <div className="eg-legend-items">
            <span className="eg-legend-item">
              <span className="eg-legend-line" style={{ color: '#f97316' }}>
                ━━
              </span>{' '}
              Critical path
            </span>
            <span className="eg-legend-item">
              <span className="eg-legend-line">━━</span> Dependency
            </span>
            <span className="eg-legend-item">
              <span className="eg-legend-marker eg-legend-error">✕</span> Error
            </span>
            <span className="eg-legend-item">
              <span className="eg-legend-marker eg-legend-anomaly">⚠</span> Anomaly
            </span>
          </div>
        </div>
      )}
    </div>
  )
}