"""
graph/builder.py – Build an execution graph (DAG) from a list of Span objects.

Constructs:
  - Nodes: one per span, with depth and timing metadata
  - Edges: parent_span_id → span_id directed edges
  - Cycle detection: DFS-based for reasoning loop identification
  - Critical path: longest duration path through the DAG

The ExecutionGraph model can be serialised to JSON and consumed directly
by the vis.js frontend visualisation.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from core.models import (
    ExecutionGraph,
    GraphEdge,
    GraphNode,
    Span,
    SpanKind,
    SpanStatus,
)


class GraphBuilder:
    """Build an ExecutionGraph from an ordered list of spans."""

    def build(self, trace_id: str, spans: List[Span]) -> ExecutionGraph:
        if not spans:
            return ExecutionGraph(trace_id=trace_id)

        # Index spans by id
        by_id: Dict[str, Span] = {s.span_id: s for s in spans}

        # Build child → parent and parent → children maps
        children: Dict[str, List[str]] = defaultdict(list)
        for s in spans:
            if s.parent_span_id and s.parent_span_id in by_id:
                children[s.parent_span_id].append(s.span_id)

        # Find root span(s): spans with no parent (or parent not in trace)
        roots = [s.span_id for s in spans
                 if not s.parent_span_id or s.parent_span_id not in by_id]

        # Assign depth via BFS from roots
        depth: Dict[str, int] = {}
        queue = [(r, 0) for r in roots]
        while queue:
            nid, d = queue.pop(0)
            depth[nid] = d
            for child in children.get(nid, []):
                if child not in depth:
                    queue.append((child, d + 1))
        # Assign depth 0 to any disconnected span
        for s in spans:
            if s.span_id not in depth:
                depth[s.span_id] = 0

        # Build nodes
        nodes = [
            GraphNode(
                span_id=s.span_id,
                name=s.name,
                kind=s.kind,
                status=s.status,
                start_time=s.start_time,
                end_time=s.end_time,
                duration_ms=s.duration_ms,
                depth=depth.get(s.span_id, 0),
                attributes=s.attributes,
            )
            for s in spans
        ]

        # Build edges
        edges = [
            GraphEdge(source=s.parent_span_id, target=s.span_id)
            for s in spans
            if s.parent_span_id and s.parent_span_id in by_id
        ]

        # Cycle detection (DFS)
        cycles, cycle_spans = self._detect_cycles(spans, children)

        # Critical path (longest-duration path from root)
        critical_path = self._critical_path(spans, by_id, children, roots)

        # Stats
        kind_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        for s in spans:
            kind_counts[str(s.kind.value)] = kind_counts.get(str(s.kind.value), 0) + 1
            status_counts[str(s.status.value)] = status_counts.get(str(s.status.value), 0) + 1

        durations = [s.duration_ms for s in spans if s.duration_ms is not None]
        stats: Dict[str, Any] = {
            "span_count":    len(spans),
            "max_depth":     max(depth.values(), default=0),
            "kind_counts":   dict(kind_counts),
            "status_counts": dict(status_counts),
            "total_duration_ms": sum(durations) if durations else None,
            "avg_span_duration_ms": round(float(sum(durations)) / len(durations), 2) if durations else None,  # type: ignore
        }

        return ExecutionGraph(
            trace_id=trace_id,
            nodes=nodes,
            edges=edges,
            has_cycles=bool(cycles),
            cycle_spans=cycle_spans,
            critical_path=critical_path,
            max_depth=stats["max_depth"],
            stats=stats,
        )

    # ── Cycle detection ────────────────────────────────────────────────────

    def _detect_cycles(
        self,
        spans: List[Span],
        children: Dict[str, List[str]],
    ) -> Tuple[bool, List[str]]:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycle_nodes: Set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for child in children.get(node, []):
                if child not in visited:
                    if dfs(child):
                        cycle_nodes.add(child)
                        return True
                elif child in rec_stack:
                    cycle_nodes.add(node)
                    cycle_nodes.add(child)
                    return True
            rec_stack.discard(node)
            return False

        for s in spans:
            if s.span_id not in visited:
                dfs(s.span_id)

        return bool(cycle_nodes), list(cycle_nodes)

    # ── Critical path ──────────────────────────────────────────────────────

    def _critical_path(
        self,
        spans: List[Span],
        by_id: Dict[str, Span],
        children: Dict[str, List[str]],
        roots: List[str],
    ) -> List[str]:
        """Return span_ids on the critical (longest-duration) path."""
        memo: Dict[str, Tuple[float, List[str]]] = {}

        def longest(node_id: str) -> Tuple[float, List[str]]:
            if node_id in memo:
                return memo[node_id]
            span = by_id.get(node_id)
            dur = (span.duration_ms or 0.0) if span else 0.0
            kids = children.get(node_id, [])
            if not kids:
                result = (dur, [node_id])
            else:
                best_dur, best_path = max(
                    (longest(c) for c in kids), key=lambda x: x[0]
                )
                result = (dur + best_dur, [node_id] + best_path)
            memo[node_id] = result
            return result

        if not roots:
            return []
        _, path = max((longest(r) for r in roots), key=lambda x: x[0])
        return path

    # ── Graph Diff ─────────────────────────────────────────────────────────

    def diff_graphs(
        self,
        graphA: "ExecutionGraph",
        graphB: "ExecutionGraph",
    ) -> Dict[str, Any]:
        """
        Compute the structural difference between two ExecutionGraphs.

        Node matching uses span name (tool/operation label) as the canonical
        key so that graphs with different span_ids but the same tool sequence
        are handled correctly.

        Returns
        -------
        {
          "missing_nodes": [str, ...],     # in A but not in B
          "extra_nodes":   [str, ...],     # in B but not in A
          "tool_mismatch": [               # same step index, different name
              {"step": int, "baseline": str, "attacked": str}, ...
          ],
          "edge_changes": [               # edges present in A but not B or vice-versa
              {"baseline": "A → B", "attacked": "(removed)"}, ...
          ]
        }
        """
        # Build name-sets and ordered name-lists
        names_a: List[str] = [n.name for n in graphA.nodes]
        names_b: List[str] = [n.name for n in graphB.nodes]
        set_a = set(names_a)
        set_b = set(names_b)

        missing_nodes = sorted(set_a - set_b)
        extra_nodes   = sorted(set_b - set_a)

        # Step-level tool mismatch (by position)
        tool_mismatch: List[Dict[str, Any]] = []
        for i in range(min(len(names_a), len(names_b))):
            if names_a[i] != names_b[i]:
                tool_mismatch.append({
                    "step":     i,
                    "baseline": names_a[i],
                    "attacked": names_b[i],
                })

        # Edge comparison using "source_name → target_name" string keys
        def _named_edges(graph: "ExecutionGraph") -> Set[Tuple[str, str]]:
            id_to_name: Dict[str, str] = {n.span_id: n.name for n in graph.nodes}
            return {
                (str(id_to_name.get(e.source, e.source)), str(id_to_name.get(e.target, e.target)))
                for e in graph.edges
                if e.source in id_to_name and e.target in id_to_name
            }

        edges_a = _named_edges(graphA)
        edges_b = _named_edges(graphB)
        edge_changes: List[Dict[str, str]] = []
        for src, dst in sorted(edges_a - edges_b):
            edge_changes.append({"baseline": f"{src} → {dst}", "attacked": "(removed)"})
        for src, dst in sorted(edges_b - edges_a):
            edge_changes.append({"baseline": "(added)", "attacked": f"{src} → {dst}"})

        return {
            "missing_nodes": missing_nodes,
            "extra_nodes":   extra_nodes,
            "tool_mismatch": tool_mismatch,
            "edge_changes":  edge_changes,
        }
