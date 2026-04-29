/**
 * Graph view — React Flow execution DAG for any trace.
 */
import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ExecutionGraph from "../components/graph/ExecutionGraph";
import SpanDetailSidebar from "../components/trace/SpanDetailSidebar";
import { Spinner } from "../components/ui/Spinner";
import { EmptyState } from "../components/ui/EmptyState";
import useStore from "../store/useStore";
import { useAsync } from "../hooks/useAsync";
import api from "../services/api";
import { short } from "../utils/format";

export default function Graph() {
    const { traceId: urlId } = useParams();
    const navigate = useNavigate();
    const toast = useStore((s) => s.toast);

    const [traceId, setTraceId] = useState(urlId ?? "");
    const [inputId, setInputId] = useState(urlId ?? "");
    const [selectedNode, setSelected] = useState(null);

    const { data: traceList, execute: loadList } = useAsync(
        useCallback(() => api.listTraces(), []),
    );

    const {
        data: graph,
        loading,
        error,
        execute: loadGraph,
    } = useAsync(useCallback((id) => api.getGraph(id), []));

    useEffect(() => {
        loadList();
    }, [loadList]);
    useEffect(() => {
        if (error) toast(`Graph load failed: ${error}`, "error");
    }, [error, toast]);
    useEffect(() => {
        if (urlId) {
            setTraceId(urlId);
            setInputId(urlId);
            loadGraph(urlId);
        }
    }, [urlId]); // eslint-disable-line

    const handleLoad = () => {
        if (!inputId.trim()) {
            toast("Enter a trace ID.", "warn");
            return;
        }
        setTraceId(inputId.trim());
        navigate(`/graph/${inputId.trim()}`, { replace: true });
        loadGraph(inputId.trim());
    };

    // Map a React Flow node click → full span data
    const handleNodeClick = (rfNode) => {
        if (!graph) return;
        const spanData = graph.nodes?.find((n) => n.span_id === rfNode.id);
        setSelected(
            spanData
                ? {
                      span_id: spanData.span_id,
                      trace_id: traceId,
                      name: spanData.name,
                      kind: spanData.kind,
                      status: spanData.status,
                      duration_ms: spanData.duration_ms,
                      is_anomalous: spanData.is_anomalous,
                  }
                : null,
        );
    };

    return (
        <div
            className="view"
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
        >
            <div className="view-header">
                <h1 className="view-title">Execution Graph</h1>
                {traceId && (
                    <div className="view-header-actions">
                        <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => navigate(`/traces/${traceId}`)}
                        >
                            Inspect Spans
                        </button>
                        <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => navigate(`/replay/${traceId}`)}
                        >
                            Replay
                        </button>
                    </div>
                )}
            </div>

            {/* Trace selector */}
            <div className="panel" style={{ padding: "12px 16px" }}>
                <div className="trace-selector">
                    <input
                        className="form-input"
                        placeholder="Trace ID…"
                        value={inputId}
                        onChange={(e) => setInputId(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleLoad()}
                        list="trace-id-list"
                        style={{ flex: 1 }}
                    />
                    <datalist id="trace-id-list">
                        {(traceList ?? []).map((t) => (
                            <option key={t.trace_id} value={t.trace_id} />
                        ))}
                    </datalist>
                    <button
                        className="btn btn-primary btn-sm"
                        onClick={handleLoad}
                        disabled={loading}
                    >
                        {loading ? <Spinner size="sm" /> : "Load"}
                    </button>
                </div>
            </div>

            {/* Graph area */}
            <div style={{ flex: 1, position: "relative", minHeight: 400 }}>
                {loading && (
                    <div className="graph-loading">
                        <Spinner /> Loading graph…
                    </div>
                )}

                {!loading && !graph && (
                    <EmptyState
                        icon="⬡"
                        title="No graph loaded"
                        description="Enter a trace ID above and click Load."
                    />
                )}

                {graph && (
                    <ExecutionGraph
                        graph={graph}
                        onNodeClick={handleNodeClick}
                        traceId={traceId}
                    />
                )}
            </div>

            {selectedNode && (
                <SpanDetailSidebar
                    span={selectedNode}
                    onClose={() => setSelected(null)}
                />
            )}
        </div>
    );
}
