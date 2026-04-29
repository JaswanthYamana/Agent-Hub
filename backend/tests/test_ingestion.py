"""
tests/test_ingestion.py – Unit tests for ingestion/normalizer.py
"""
from __future__ import annotations

import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from ingestion.normalizer import normalize_otlp_batch, normalize_sdk_spans
from core.models import SpanKind, SpanStatus


# ── OTLP normalizer ────────────────────────────────────────────────────────

def _otlp_payload(kind: str = "tool", service: str = "test-svc") -> dict:
    """Minimal valid OTLP/JSON span payload."""
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "abc123",
                                "spanId": "span001",
                                "name": "flight_search_api",
                                "startTimeUnixNano": str(int(time.time() * 1e9)),
                                "endTimeUnixNano":   str(int((time.time() + 0.1) * 1e9)),
                                "status": {"code": 1},
                                "attributes": [
                                    {
                                        "key": "openinference.span.kind",
                                        "value": {"stringValue": kind},
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }


class TestNormalizeOtlpBatch:
    def test_returns_list_of_spans(self):
        spans = normalize_otlp_batch(_otlp_payload(), project_id="proj-1")
        assert len(spans) == 1

    def test_service_name_from_resource(self):
        spans = normalize_otlp_batch(_otlp_payload(service="my-agent"))
        assert spans[0].service_name == "my-agent"

    def test_span_name_preserved(self):
        spans = normalize_otlp_batch(_otlp_payload())
        assert spans[0].name == "flight_search_api"

    def test_tool_kind_mapped(self):
        spans = normalize_otlp_batch(_otlp_payload(kind="tool"))
        assert spans[0].kind == SpanKind.TOOL

    def test_llm_kind_mapped(self):
        spans = normalize_otlp_batch(_otlp_payload(kind="llm"))
        assert spans[0].kind == SpanKind.LLM

    def test_empty_payload_returns_empty_list(self):
        spans = normalize_otlp_batch({"resourceSpans": []})
        assert spans == []

    def test_project_id_set(self):
        spans = normalize_otlp_batch(_otlp_payload(), project_id="my-project")
        assert spans[0].project_id == "my-project"


# ── SDK normalizer ─────────────────────────────────────────────────────────

class TestNormalizeSdkSpans:
    def _raw(self, **overrides) -> dict:
        base = {
            "name": "flight_search_api",
            "start_time": time.time(),
            "end_time": time.time() + 0.5,
            "status": "OK",
            "kind": "TOOL",
        }
        base.update(overrides)
        return base

    def test_single_valid_span(self):
        spans = normalize_sdk_spans([self._raw()])
        assert len(spans) == 1
        assert spans[0].name == "flight_search_api"

    def test_status_ok_mapped(self):
        spans = normalize_sdk_spans([self._raw(status="OK")])
        assert spans[0].status == SpanStatus.OK

    def test_status_error_mapped(self):
        spans = normalize_sdk_spans([self._raw(status="ERROR")])
        assert spans[0].status == SpanStatus.ERROR

    def test_missing_name_raises_value_error(self):
        with pytest.raises(ValueError, match="'name'"):
            normalize_sdk_spans([{"start_time": time.time()}])

    def test_missing_start_time_raises_value_error(self):
        with pytest.raises(ValueError, match="'start_time'"):
            normalize_sdk_spans([{"name": "my_tool"}])

    def test_future_start_time_raises_value_error(self):
        future = time.time() + 100_000
        with pytest.raises(ValueError, match="future"):
            normalize_sdk_spans([{"name": "tool", "start_time": future}])

    def test_end_before_start_raises_value_error(self):
        now = time.time()
        with pytest.raises(ValueError, match="'end_time'"):
            normalize_sdk_spans([{"name": "tool", "start_time": now, "end_time": now - 1}])

    def test_fallback_trace_id_applied(self):
        spans = normalize_sdk_spans([self._raw()], trace_id="parent-trace")
        assert spans[0].trace_id == "parent-trace"

    def test_multiple_spans(self):
        spans = normalize_sdk_spans([self._raw(), self._raw(name="pricing_api")])
        assert len(spans) == 2
        names = {s.name for s in spans}
        assert "flight_search_api" in names
        assert "pricing_api" in names

    def test_duration_ms_computed(self):
        now = time.time()
        spans = normalize_sdk_spans([{"name": "t", "start_time": now, "end_time": now + 1.0}])
        assert abs(spans[0].duration_ms - 1000.0) < 1  # ± 1 ms tolerance
