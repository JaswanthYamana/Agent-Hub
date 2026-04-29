"""
tests/test_anomaly_detection.py – Unit tests for anomaly/detector.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from anomaly.detector import AnomalyDetector
from core.models import AnomalyType, SpanKind, SpanStatus


# ┌─ Fixtures are imported from conftest.py ─────────────────────────────────

_detector = AnomalyDetector()


# ── Reasoning-loop detection ───────────────────────────────────────────────

class TestReasoningLoopDetection:
    def test_no_anomaly_on_clean_trace(self, normal_flight_trace):
        anomalies = _detector.detect(normal_flight_trace, baselines={})
        types = [a["type"] for a in anomalies]
        assert AnomalyType.REASONING_LOOP.value not in types

    def test_three_failures_triggers_loop(self, error_flight_trace):
        anomalies = _detector.detect(error_flight_trace, baselines={})
        types = [a["type"] for a in anomalies]
        assert AnomalyType.REASONING_LOOP.value in types

    def test_anomaly_evidence_contains_fail_count(self, error_flight_trace):
        anomalies = _detector.detect(error_flight_trace, baselines={})
        loop_anomalies = [a for a in anomalies if a["type"] == AnomalyType.REASONING_LOOP.value]
        assert loop_anomalies
        assert loop_anomalies[0]["evidence"]["fail_count"] >= 3

    def test_two_failures_does_not_trigger(self, make_span, make_trace):
        """Just below the threshold — should NOT flag a reasoning loop."""
        spans = [
            make_span(name="payment_processing", status=SpanStatus.ERROR),
            make_span(name="payment_processing", status=SpanStatus.ERROR),
        ]
        trace = make_trace(scenario="tool_error", spans=spans, success=False)
        anomalies = _detector.detect(trace, baselines={})
        types = [a["type"] for a in anomalies]
        assert AnomalyType.REASONING_LOOP.value not in types


# ── Excessive steps detection ──────────────────────────────────────────────

class TestExcessiveStepsDetection:
    def test_many_tool_calls_triggers_excessive_steps(self, make_span, make_trace):
        spans = [make_span(name=f"tool_{i}") for i in range(20)]
        trace = make_trace(scenario="normal", spans=spans)
        anomalies = _detector.detect(trace, baselines={})
        types = [a["type"] for a in anomalies]
        assert AnomalyType.EXCESSIVE_STEPS.value in types

    def test_few_tool_calls_no_anomaly(self, normal_flight_trace):
        anomalies = _detector.detect(normal_flight_trace, baselines={})
        types = [a["type"] for a in anomalies]
        assert AnomalyType.EXCESSIVE_STEPS.value not in types


# ── Abnormal latency detection ─────────────────────────────────────────────

class TestAbnormalLatency:
    def test_high_latency_span_triggers_anomaly(self, make_span, make_trace):
        spans = [make_span(name="slow_tool", duration_ms=15_000)]
        trace = make_trace(scenario="normal", spans=spans)
        anomalies = _detector.detect(trace, baselines={})
        types = [a["type"] for a in anomalies]
        assert AnomalyType.ABNORMAL_LATENCY.value in types

    def test_normal_latency_no_anomaly(self, make_span, make_trace):
        spans = [make_span(name="fast_tool", duration_ms=200)]
        trace = make_trace(scenario="normal", spans=spans)
        anomalies = _detector.detect(trace, baselines={})
        types = [a["type"] for a in anomalies]
        assert AnomalyType.ABNORMAL_LATENCY.value not in types


# ── Return schema ──────────────────────────────────────────────────────────

class TestAnomalySchema:
    def test_anomaly_record_has_required_fields(self, error_flight_trace):
        anomalies = _detector.detect(error_flight_trace, baselines={})
        for a in anomalies:
            assert "id" in a
            assert "trace_id" in a
            assert "type" in a
            assert "severity" in a
            assert "description" in a
            assert "evidence" in a
            assert "created_at" in a

    def test_severity_is_valid_string(self, error_flight_trace):
        anomalies = _detector.detect(error_flight_trace, baselines={})
        valid_severities = {"low", "medium", "high", "critical"}
        for a in anomalies:
            assert a["severity"] in valid_severities
