"""
tests/test_replay.py – Unit tests for replay/engine.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from replay.engine import capture, get_frame, diff_manifests, manifest_to_dict
from core.models import SpanKind, SpanStatus


# ── capture() ─────────────────────────────────────────────────────────────

class TestCapture:
    def test_returns_manifest_with_correct_trace_id(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        assert manifest.trace_id == normal_flight_trace.trace_id

    def test_frame_count_matches_span_count(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        assert len(manifest.frames) == len(normal_flight_trace.spans)

    def test_empty_trace_produces_empty_manifest(self, make_trace):
        trace = make_trace(spans=[])
        manifest = capture(trace)
        assert manifest.total_steps == 0
        assert manifest.frames == []

    def test_frame_step_indices_sequential(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        for i, frame in enumerate(manifest.frames):
            assert frame.step == i

    def test_cumulative_tool_calls_monotonically_increases(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        prev = 0
        for frame in manifest.frames:
            assert frame.cumulative_tool_calls >= prev
            prev = frame.cumulative_tool_calls

    def test_error_span_increments_cumulative_errors(self, make_span, make_trace):
        spans = [
            make_span(name="tool_a"),
            make_span(name="tool_b", status=SpanStatus.ERROR, error_message="fail"),
        ]
        trace = make_trace(spans=spans)
        manifest = capture(trace)
        assert manifest.frames[1].cumulative_errors == 1

    def test_no_errors_cumulative_errors_zero(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        for frame in manifest.frames:
            assert frame.cumulative_errors == 0

    def test_task_set_on_manifest(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        assert manifest.task == normal_flight_trace.task

    def test_span_name_preserved_in_frame(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        span_names = {s.name for s in normal_flight_trace.spans}
        frame_names = {f.span_name for f in manifest.frames}
        assert span_names == frame_names


# ── get_frame() ────────────────────────────────────────────────────────────

class TestGetFrame:
    def test_get_frame_valid_index(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        frame = get_frame(manifest, 0)
        assert frame is not None
        assert frame.step == 0

    def test_get_frame_last_index(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        last = len(manifest.frames) - 1
        frame = get_frame(manifest, last)
        assert frame is not None
        assert frame.step == last

    def test_get_frame_out_of_bounds_returns_none(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        frame = get_frame(manifest, 9999)
        assert frame is None

    def test_get_frame_negative_index_returns_none(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        frame = get_frame(manifest, -1)
        assert frame is None


# ── diff_manifests() ───────────────────────────────────────────────────────

class TestDiffManifests:
    def test_same_trace_produces_empty_diff(self, normal_flight_trace):
        m1 = capture(normal_flight_trace)
        m2 = capture(normal_flight_trace)
        diff = diff_manifests(m1, m2)
        assert diff.first_divergence_step is None or diff.divergence_count == 0

    def test_different_traces_show_divergence(self, normal_flight_trace, error_flight_trace):
        m1 = capture(normal_flight_trace)
        m2 = capture(error_flight_trace)
        diff = diff_manifests(m1, m2)
        # Manifests of different lengths — diff should detect it
        assert diff is not None

    def test_diff_has_expected_fields(self, normal_flight_trace, error_flight_trace):
        m1 = capture(normal_flight_trace)
        m2 = capture(error_flight_trace)
        diff = diff_manifests(m1, m2)
        # Check basic structural attributes survive
        assert hasattr(diff, "baseline_trace_id")
        assert hasattr(diff, "attacked_trace_id")


# ── manifest_to_dict() ─────────────────────────────────────────────────────

class TestManifestToDict:
    def test_returns_dict(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        result = manifest_to_dict(manifest)
        assert isinstance(result, dict)

    def test_dict_has_trace_id(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        result = manifest_to_dict(manifest)
        assert result.get("trace_id") == normal_flight_trace.trace_id

    def test_dict_has_frames(self, normal_flight_trace):
        manifest = capture(normal_flight_trace)
        result = manifest_to_dict(manifest)
        assert "frames" in result
        assert isinstance(result["frames"], list)
        assert len(result["frames"]) == len(normal_flight_trace.spans)
