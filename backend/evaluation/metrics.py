"""
evaluation/metrics.py – Domain-agnostic reliability metrics engine.

Implements the agent-centric metrics from the research document:
  • Pass^k  (§ "Tau-bench / Pass^k metric")
  • Tool Selection Accuracy     (§ "Tool Selection Accuracy & Parameter Correctness")
  • Parameter Correctness
  • Task Completion Rate
  • Goal Success vs Partial Completion
  • Overall Reliability Score (weighted composite)
  • Attack Success Rate (for red-team runs)

The engine is domain-agnostic: it reads the optimal_path and required_params
from the domain config (core/config.py) keyed by the trace's scenario.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.config import get_domain
from core.models import Span, SpanKind, SpanStatus, Trace

# ── MetricsEngine ──────────────────────────────────────────────────────────


class MetricsEngine:
    def compute(self, trace: Trace) -> Dict[str, Any]:
        """Return a metrics dict suitable for storing in trace.metrics."""
        domain = get_domain(trace.scenario)
        tool_spans = [s for s in trace.spans if s.kind == SpanKind.TOOL]
        opt_path = domain.get("optimal_path", [])
        req_params = domain.get("required_params", {})
        unauth = domain.get("unauthorized_tools", set())

        tsa = self._tool_selection_accuracy(tool_spans, opt_path, unauth)
        pc = self._parameter_correctness(tool_spans, req_params)
        tcr = self._task_completion_rate(tool_spans, opt_path)
        wc = self._workflow_correctness(tool_spans, opt_path)
        goal = trace.success and not trace.partial_completion

        # Anomaly penalty: each critical anomaly costs 15%, high costs 8%
        anomaly_penalty = self._anomaly_penalty(trace.anomalies)

        # Weighted composite — research doc weights updated to include
        # workflow correctness (replaces portion of TSA weight):
        #   0.25·TSA + 0.20·PC + 0.25·TCR + 0.15·WC + 0.15·(1-anomaly_penalty)
        ors = max(
            0.0,
            min(
                1.0,
                tsa * 0.25
                + pc * 0.20
                + tcr * 0.25
                + wc * 0.15
                + (1.0 - anomaly_penalty) * 0.15,
            ),
        )

        hallucination_rate = self._hallucination_rate(tool_spans)
        error_rate = (
            sum(1 for s in tool_spans if s.status == SpanStatus.ERROR) / len(tool_spans)
            if tool_spans
            else 0.0
        )

        return {
            "tool_selection_accuracy": round(tsa, 3),
            "parameter_correctness": round(pc, 3),
            "task_completion_rate": round(tcr, 3),
            "workflow_correctness": round(wc, 3),
            "goal_success": goal,
            "overall_reliability_score": round(ors, 3),
            "anomaly_count": len(trace.anomalies),
            "anomaly_penalty": round(anomaly_penalty, 3),
            "hallucination_rate": round(hallucination_rate, 3),
            "error_rate": round(error_rate, 3),
            "tool_call_count": len(tool_spans),
            "domain": domain.get("name", "Generic"),
        }

    # ── Individual metrics ─────────────────────────────────────────────────

    def _tool_selection_accuracy(
        self,
        tool_spans: List[Span],
        optimal_path: List[str],
        unauthorized_tools: set,
    ) -> float:
        if not tool_spans:
            return 1.0
        correct = 0
        for s in tool_spans:
            tool = s.attributes.get("tool", s.name)
            if tool in optimal_path and tool not in unauthorized_tools:
                correct += 1
            elif tool in unauthorized_tools:
                pass  # zero score for unauthorized
            elif not optimal_path:
                # No domain restriction — count non-errored spans as correct
                if s.status not in (SpanStatus.ERROR, SpanStatus.HALLUCINATED):
                    correct += 1
        return correct / len(tool_spans)

    def _parameter_correctness(
        self,
        tool_spans: List[Span],
        required_params: Dict[str, List[str]],
    ) -> float:
        if not tool_spans:
            return 1.0
        total = 0
        correct = 0
        for s in tool_spans:
            tool = s.attributes.get("tool", s.name)
            params_raw = s.attributes.get("input_params", {})
            # Ensure params is a dictionary; if it's a string or other type, treat as empty
            if isinstance(params_raw, dict):
                params = params_raw
            else:
                params = {}
            req = required_params.get(tool, [])
            if not req:
                # No schema defined → pass if span is OK
                total += 1
                if s.status not in (SpanStatus.ERROR, SpanStatus.HALLUCINATED):
                    correct += 1
            else:
                total += len(req)
                for r in req:
                    if r in params and params[r] not in (None, "", [], {}):
                        correct += 1
        return correct / total if total else 1.0

    def _task_completion_rate(
        self,
        tool_spans: List[Span],
        optimal_path: List[str],
    ) -> float:
        if not optimal_path:
            # Without a path, use span success ratio
            if not tool_spans:
                return 0.0
            ok = sum(1 for s in tool_spans if s.status == SpanStatus.OK)
            return ok / len(tool_spans)
        executed_tools = {
            s.attributes.get("tool", s.name)
            for s in tool_spans
            if s.status == SpanStatus.OK
        }
        completed = sum(1 for t in optimal_path if t in executed_tools)
        return completed / len(optimal_path)

    def _hallucination_rate(self, tool_spans: List[Span]) -> float:
        if not tool_spans:
            return 0.0
        return sum(1 for s in tool_spans if s.status == SpanStatus.HALLUCINATED) / len(
            tool_spans
        )

    def _anomaly_penalty(self, anomalies: List[Dict[str, Any]]) -> float:
        penalty = 0.0
        for a in anomalies:
            sev = a.get("severity", "low")
            if sev == "critical":
                penalty += 0.15
            elif sev == "high":
                penalty += 0.08
            elif sev == "medium":
                penalty += 0.04
            else:
                penalty += 0.01
        return min(penalty, 1.0)

    def _workflow_correctness(
        self, tool_spans: List[Span], optimal_path: List[str]
    ) -> float:
        """
        Measure how closely the actual tool invocation sequence matches the
        optimal path using the Longest Common Subsequence (LCS) ratio.

        LCS length / len(optimal_path) gives a value in [0, 1] where 1.0
        means every step of the optimal path was executed in order.
        """
        if not optimal_path:
            return 1.0  # no domain constraint → cannot penalise
        actual = [
            s.attributes.get("tool", s.name)
            for s in tool_spans
            if s.status == SpanStatus.OK
        ]
        if not actual:
            return 0.0
        lcs_len = _lcs_length(actual, optimal_path)
        return lcs_len / len(optimal_path)


# ── LCS helper ────────────────────────────────────────────────────────────


def _lcs_length(a: List[str], b: List[str]) -> int:
    """Standard dynamic-programming LCS, O(m·n) time and space."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


# ── Pass^k ─────────────────────────────────────────────────────────────────


def compute_pass_k(traces: List[Trace]) -> float:
    """
    Pass^k: fraction of traces that completed successfully.
    Research doc: "measures whether an agent consistently completes tasks
    across k distinct trials."
    """
    if not traces:
        return 0.0
    successes = sum(1 for t in traces if t.success and t.completed)
    return round(successes / len(traces), 3)
