"""
tests/conftest.py – Shared pytest fixtures for the backend test suite.

Run all tests with:
    pytest backend/tests/ -v
from the repo root with PYTHONPATH=backend set, or:
    cd backend && pytest tests/ -v
"""
from __future__ import annotations

import sys
import time
import uuid
import os

# Ensure the backend package is importable regardless of where pytest is invoked.
_BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND_DIR))

import pytest

from core.models import (
    Span,
    SpanKind,
    SpanStatus,
    Trace,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_span(
    *,
    name: str = "flight_search_api",
    kind: SpanKind = SpanKind.TOOL,
    status: SpanStatus = SpanStatus.OK,
    duration_ms: float = 120.0,
    tool_name: str | None = None,
    input_data: dict | None = None,
    output_data: object = "result",
    error_message: str | None = None,
    trace_id: str = "trace-001",
) -> Span:
    now = time.time()
    attrs = {
        "tool_name": tool_name or (name if kind == SpanKind.TOOL else None),
        "input_data": input_data or {},
        "output_data": output_data,
    }
    return Span(
        span_id=str(uuid.uuid4()),
        trace_id=trace_id,
        kind=kind,
        name=name,
        start_time=now,
        end_time=now + duration_ms / 1000,
        duration_ms=duration_ms,
        status=status,
        attributes=attrs,
        error_message=error_message,
        service_name="test-agent",
        project_id="test",
    )


def _make_trace(
    *,
    trace_id: str = "trace-001",
    scenario: str = "normal",
    spans: list[Span] | None = None,
    success: bool = True,
    partial_completion: bool = False,
    task: str = "Book a flight from NYC to LAX",
    anomalies: list | None = None,
) -> Trace:
    now = time.time()
    span_list = spans or []
    return Trace(
        trace_id=trace_id,
        task=task,
        scenario=scenario,
        start_time=now,
        end_time=now + 2.0,
        duration_ms=2000.0,
        total_steps=len(span_list),
        tool_call_count=sum(1 for s in span_list if s.kind == SpanKind.TOOL),
        error_count=sum(1 for s in span_list if s.status == SpanStatus.ERROR),
        completed=True,
        success=success,
        partial_completion=partial_completion,
        spans=span_list,
        anomalies=anomalies or [],
        metrics={},
        project_id="test",
    )


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def make_span():
    """Factory fixture for creating Span instances."""
    return _make_span


@pytest.fixture()
def make_trace():
    """Factory fixture for creating Trace instances."""
    return _make_trace


@pytest.fixture()
def normal_flight_trace() -> Trace:
    """A complete, successful flight-booking trace with the full optimal path."""
    tid = "trace-flight-001"
    spans = [
        _make_span(name="flight_search_api",    trace_id=tid, input_data={"origin": "NYC", "destination": "LAX"}),
        _make_span(name="seat_selection_api",   trace_id=tid),
        _make_span(name="pricing_api",          trace_id=tid),
        _make_span(name="payment_processing",   trace_id=tid),
        _make_span(name="booking_confirmation", trace_id=tid),
        _make_span(name="notification_service", trace_id=tid),
    ]
    return _make_trace(trace_id=tid, scenario="flight_booking", spans=spans, success=True)


@pytest.fixture()
def error_flight_trace() -> Trace:
    """A trace with a repeated tool error (triggers reasoning-loop anomaly)."""
    tid = "trace-error-001"
    spans = [
        _make_span(name="flight_search_api", trace_id=tid),
        _make_span(name="payment_processing", trace_id=tid, status=SpanStatus.ERROR, error_message="card declined"),
        _make_span(name="payment_processing", trace_id=tid, status=SpanStatus.ERROR, error_message="card declined"),
        _make_span(name="payment_processing", trace_id=tid, status=SpanStatus.ERROR, error_message="card declined"),
    ]
    return _make_trace(trace_id=tid, scenario="tool_error", spans=spans, success=False)
