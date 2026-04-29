"""
tests/test_metrics.py – Unit tests for evaluation/metrics.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from evaluation.metrics import MetricsEngine
from core.models import SpanKind, SpanStatus


_engine = MetricsEngine()


# ── Basic computation ──────────────────────────────────────────────────────

class TestMetricsEngineKeys:
    def test_all_keys_present_on_normal_trace(self, normal_flight_trace):
        result = _engine.compute(normal_flight_trace)
        required_keys = {
            "tool_selection_accuracy",
            "parameter_correctness",
            "task_completion_rate",
            "workflow_correctness",
            "goal_success",
            "overall_reliability_score",
            "anomaly_count",
            "anomaly_penalty",
            "hallucination_rate",
            "error_rate",
            "tool_call_count",
            "domain",
        }
        assert required_keys.issubset(result.keys())

    def test_scores_between_0_and_1(self, normal_flight_trace):
        result = _engine.compute(normal_flight_trace)
        for key in ("tool_selection_accuracy", "parameter_correctness",
                    "task_completion_rate", "workflow_correctness",
                    "overall_reliability_score"):
            assert 0.0 <= result[key] <= 1.0, f"{key} out of range: {result[key]}"

    def test_overall_reliability_is_float(self, normal_flight_trace):
        result = _engine.compute(normal_flight_trace)
        assert isinstance(result["overall_reliability_score"], float)


# ── Error trace degrades metrics ──────────────────────────────────────────

class TestErrorTraceMetrics:
    def test_error_rate_nonzero_on_error_trace(self, error_flight_trace):
        result = _engine.compute(error_flight_trace)
        assert result["error_rate"] > 0.0

    def test_overall_score_lower_on_error_trace(self, normal_flight_trace, error_flight_trace):
        good = _engine.compute(normal_flight_trace)["overall_reliability_score"]
        bad  = _engine.compute(error_flight_trace)["overall_reliability_score"]
        assert bad <= good

    def test_goal_success_false_on_failed_trace(self, error_flight_trace):
        result = _engine.compute(error_flight_trace)
        assert result["goal_success"] is False


# ── Tool call count ────────────────────────────────────────────────────────

class TestToolCallCount:
    def test_tool_call_count_matches_tool_spans(self, make_span, make_trace):
        spans = [
            make_span(name="flight_search_api", kind=SpanKind.TOOL),
            make_span(name="pricing_api",       kind=SpanKind.TOOL),
            make_span(name="llm_chat",          kind=SpanKind.LLM),
        ]
        trace = make_trace(spans=spans)
        result = _engine.compute(trace)
        assert result["tool_call_count"] == 2  # only TOOL spans counted

    def test_empty_trace_returns_zero_tool_calls(self, make_trace):
        trace = make_trace(spans=[])
        result = _engine.compute(trace)
        assert result["tool_call_count"] == 0


# ── Anomaly penalty ────────────────────────────────────────────────────────

class TestAnomalyPenalty:
    def test_no_anomaly_penalty_on_clean_trace(self, normal_flight_trace):
        normal_flight_trace.anomalies = []
        result = _engine.compute(normal_flight_trace)
        assert result["anomaly_penalty"] == 0.0

    def test_anomalies_increase_penalty(self, normal_flight_trace):
        normal_flight_trace.anomalies = [
            {"type": "REASONING_LOOP", "severity": "high"},
        ]
        result = _engine.compute(normal_flight_trace)
        assert result["anomaly_penalty"] > 0.0


# ── pass_k function ────────────────────────────────────────────────────────

class TestComputePassK:
    def test_pass_k_all_success(self, normal_flight_trace):
        from evaluation.metrics import compute_pass_k
        traces = [normal_flight_trace] * 5
        score = compute_pass_k(traces)
        assert score == 1.0

    def test_pass_k_none_success(self, error_flight_trace):
        from evaluation.metrics import compute_pass_k
        score = compute_pass_k([error_flight_trace] * 5)
        assert score == 0.0

    def test_pass_k_empty_returns_zero(self):
        from evaluation.metrics import compute_pass_k
        assert compute_pass_k([]) == 0.0

    def test_pass_k_partial(self, normal_flight_trace, error_flight_trace):
        from evaluation.metrics import compute_pass_k
        traces = [normal_flight_trace] * 3 + [error_flight_trace] * 2
        score = compute_pass_k(traces)
        assert 0.0 < score < 1.0
