"""
ingestion/normalizer.py – Convert OTLP/JSON spans into platform Span models.

Supports two ingestion paths:
  1. OTLP/HTTP JSON export  (POST /v1/traces)   – standard OpenTelemetry format
  2. SDK direct ingest      (POST /api/ingest)   – simplified dict payload

OpenInference semantic conventions v1.37+ attribute mapping:
  openinference.span.kind  → SpanKind
  input.value              → attributes["task"] / attributes["input"]
  output.value             → attributes["output"]
  tool.name                → attributes["tool"]
  tool.parameters          → attributes["input_params"]
  llm.token_count.*        → token_usage
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from core.models import Span, SpanEvent, SpanKind, SpanStatus

# Mapping from OpenInference / OpenTelemetry attribute names to SpanKind
_KIND_MAP: Dict[str, SpanKind] = {
    "agent":     SpanKind.AGENT,
    "chain":     SpanKind.CHAIN,
    "tool":      SpanKind.TOOL,
    "retriever": SpanKind.RETRIEVER,
    "llm":       SpanKind.LLM,
    "embedding": SpanKind.LLM,
    "reranker":  SpanKind.RETRIEVER,
    "guardrail": SpanKind.INTERNAL,
    "internal":  SpanKind.INTERNAL,
    "rpc":       SpanKind.CLIENT,
    "client":    SpanKind.CLIENT,
}

_STATUS_MAP: Dict[str, SpanStatus] = {
    "0":   SpanStatus.PENDING,
    "1":   SpanStatus.OK,
    "2":   SpanStatus.ERROR,
    "ok":  SpanStatus.OK,
    "error": SpanStatus.ERROR,
    "unset": SpanStatus.PENDING,
}


def normalize_otlp_batch(
    payload: Dict[str, Any],
    project_id: str = "default",
    service_name: str = "external-agent",
) -> List[Span]:
    """
    Parse an OTLP/JSON trace payload into a flat list of Span objects.

    OTLP JSON structure:
    {
      "resourceSpans": [{
        "resource": { "attributes": [...] },
        "scopeSpans": [{
          "spans": [{ <span> }, ...]
        }]
      }]
    }
    """
    spans: List[Span] = []
    for rs in payload.get("resourceSpans", []):
        # Extract service name from resource attributes
        svc = _extract_resource_attr(rs.get("resource", {}), "service.name") or service_name
        for ss in rs.get("scopeSpans", []):
            for raw in ss.get("spans", []):
                span = _normalize_otlp_span(raw, svc, project_id)
                if span:
                    spans.append(span)
    return spans


def normalize_sdk_spans(
    raw_spans: List[Dict[str, Any]],
    trace_id: Optional[str] = None,
    project_id: str = "default",
    service_name: str = "external-agent",
) -> List[Span]:
    """Parse simplified SDK-format spans (non-OTLP).

    ``trace_id`` is used as a fallback when individual span dicts do not carry
    their own ``trace_id`` field.  This is the common case when the platform
    assigns the trace_id at the API layer and injects it into every span.

    Raises ``ValueError`` if validation of any span fails.
    """
    result: List[Span] = []
    for i, raw in enumerate(raw_spans):
        error = _validate_sdk_span_dict(raw, index=i)
        if error:
            raise ValueError(error)
        span = _normalize_sdk_span(raw, service_name, project_id,
                                   fallback_trace_id=trace_id)
        if span:
            result.append(span)
    return result


def _validate_sdk_span_dict(raw: Dict[str, Any], index: int = 0) -> Optional[str]:
    """
    Validate a raw SDK span dict at the system boundary.
    Returns an error string if invalid, or None if valid.
    """
    if not isinstance(raw, dict):
        return f"Span[{index}]: must be a JSON object, got {type(raw).__name__}"

    # Required: name
    name = raw.get("name")
    if not name or not isinstance(name, str):
        return f"Span[{index}]: 'name' is required and must be a non-empty string"
    if len(name) > 256:
        return f"Span[{index}]: 'name' exceeds max length of 256 characters"

    # Required: start_time (epoch seconds, positive)
    start_time = raw.get("start_time")
    if start_time is None:
        return f"Span[{index}]: 'start_time' is required"
    if not isinstance(start_time, (int, float)):
        return f"Span[{index}]: 'start_time' must be a number (Unix epoch seconds)"
    if start_time <= 0:
        return f"Span[{index}]: 'start_time' must be a positive Unix timestamp"
    # Reject timestamps far in the future (more than 24 h ahead)
    if start_time > time.time() + 86400:
        return f"Span[{index}]: 'start_time' is more than 24 hours in the future"

    # Optional but validated: span_id
    span_id = raw.get("span_id")
    if span_id is not None:
        if not isinstance(span_id, str) or len(span_id) > 128:
            return f"Span[{index}]: 'span_id' must be a string of at most 128 characters"

    # Optional but validated: status
    status = raw.get("status")
    if status is not None:
        if not isinstance(status, str) or status.upper() not in SpanStatus.__members__:
            valid = list(SpanStatus.__members__.keys())
            return f"Span[{index}]: 'status' must be one of {valid}"

    # Optional but validated: attributes must be a plain dict
    attrs = raw.get("attributes")
    if attrs is not None and not isinstance(attrs, dict):
        return f"Span[{index}]: 'attributes' must be a JSON object"

    # Optional but validated: end_time
    end_time = raw.get("end_time")
    if end_time is not None:
        if not isinstance(end_time, (int, float)):
            return f"Span[{index}]: 'end_time' must be a number"
        if end_time < start_time:
            return f"Span[{index}]: 'end_time' must not be before 'start_time'"

    return None


# ── Internal helpers ───────────────────────────────────────────────────────

def _normalize_otlp_span(
    raw: Dict[str, Any],
    service_name: str,
    project_id: str,
) -> Optional[Span]:
    try:
        attrs = _otlp_attrs_to_dict(raw.get("attributes", []))
        events_raw = raw.get("events", [])
        events = [
            SpanEvent(
                timestamp=_ns_to_s(e.get("timeUnixNano", 0)),
                name=e.get("name", ""),
                attributes=_otlp_attrs_to_dict(e.get("attributes", [])),
            )
            for e in events_raw
        ]

        # Determine kind
        oi_kind = attrs.get("openinference.span.kind", "").lower()
        otel_kind_int = raw.get("kind", 0)
        kind = _KIND_MAP.get(oi_kind) or _infer_kind_from_name(raw.get("name", ""))

        # Locate span/trace IDs
        span_id  = raw.get("spanId",  str(uuid.uuid4())[:16])
        trace_id = raw.get("traceId", str(uuid.uuid4()))
        parent   = raw.get("parentSpanId") or None

        # Timestamps (nanoseconds → seconds)
        start_ns = int(raw.get("startTimeUnixNano", 0))
        end_ns   = int(raw.get("endTimeUnixNano", 0))
        start_s  = _ns_to_s(start_ns) if start_ns else time.time()
        end_s    = _ns_to_s(end_ns)   if end_ns   else None
        dur      = round((end_ns - start_ns) / 1_000_000, 2) if end_ns and start_ns else None

        # Status
        otel_status = raw.get("status", {})
        status_code = str(otel_status.get("code", "0")).lower()
        status = _STATUS_MAP.get(status_code, SpanStatus.OK)
        if status == SpanStatus.OK and attrs.get("error", False):
            status = SpanStatus.ERROR

        # Token usage
        token_usage: Dict[str, int] = {}
        for k, v in attrs.items():
            if "token" in k and isinstance(v, (int, float)):
                short_key = k.split(".")[-1]
                token_usage[short_key] = int(v)

        return Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent,
            kind=kind,
            name=raw.get("name", "unknown"),
            start_time=start_s,
            end_time=end_s,
            duration_ms=dur,
            status=status,
            attributes=attrs,
            events=events,
            error_message=otel_status.get("message"),
            service_name=service_name,
            project_id=project_id,
            token_usage=token_usage,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to normalize OTLP span: %s", exc)
        return None


def _normalize_sdk_span(
    raw: Dict[str, Any],
    service_name: str,
    project_id: str,
    fallback_trace_id: Optional[str] = None,
) -> Optional[Span]:
    """Normalize the simplified dict format emitted by sdk.py."""
    try:
        kind_str = raw.get("kind", "TOOL").upper()
        kind = SpanKind(kind_str) if kind_str in SpanKind.__members__ else SpanKind.TOOL
        status_str = raw.get("status", "OK").upper()
        status = SpanStatus(status_str) if status_str in SpanStatus.__members__ else SpanStatus.OK
        resolved_trace_id = (
            raw.get("trace_id")
            or fallback_trace_id
            or str(uuid.uuid4())
        )
        _start = raw.get("start_time", time.time())
        _end   = raw.get("end_time")
        _dur   = raw.get("duration_ms")
        if _dur is None and _end is not None:
            _dur = (_end - _start) * 1000
        return Span(
            span_id=raw.get("span_id", str(uuid.uuid4())[:16]),
            trace_id=resolved_trace_id,
            parent_span_id=raw.get("parent_span_id"),
            kind=kind,
            name=raw.get("name", "span"),
            start_time=_start,
            end_time=_end,
            duration_ms=_dur,
            status=status,
            attributes=raw.get("attributes", {}),
            events=[SpanEvent(**e) for e in raw.get("events", [])],
            error_message=raw.get("error_message"),
            contains_injection=bool(raw.get("contains_injection", False)),
            injection_payload=raw.get("injection_payload"),
            service_name=raw.get("service_name", service_name),
            project_id=project_id,
            token_usage=raw.get("token_usage", {}),
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to normalize SDK span: %s", exc)
        return None


def _otlp_attrs_to_dict(attrs: List[Dict]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for a in attrs:
        key = a.get("key", "")
        val = a.get("value", {})
        if "stringValue" in val:
            result[key] = val["stringValue"]
        elif "intValue" in val:
            result[key] = int(val["intValue"])
        elif "doubleValue" in val:
            result[key] = float(val["doubleValue"])
        elif "boolValue" in val:
            result[key] = bool(val["boolValue"])
        elif "arrayValue" in val:
            result[key] = [
                list(v.values())[0] if v else None
                for v in val["arrayValue"].get("values", [])
            ]
        elif "kvlistValue" in val:
            result[key] = _otlp_attrs_to_dict(val["kvlistValue"].get("values", []))
    return result


def _extract_resource_attr(resource: Dict, key: str) -> Optional[str]:
    for a in resource.get("attributes", []):
        if a.get("key") == key:
            return a.get("value", {}).get("stringValue")
    return None


def _ns_to_s(ns: int) -> float:
    return ns / 1_000_000_000


def _infer_kind_from_name(name: str) -> SpanKind:
    name_lower = name.lower()
    if any(k in name_lower for k in ("agent", "plan", "decide", "reason")):
        return SpanKind.AGENT
    if any(k in name_lower for k in ("tool", "api", "call", "invoke", "exec")):
        return SpanKind.TOOL
    if any(k in name_lower for k in ("search", "retriev", "fetch", "rag", "embed")):
        return SpanKind.RETRIEVER
    if any(k in name_lower for k in ("llm", "gpt", "claude", "gemini", "infer", "complet")):
        return SpanKind.LLM
    if any(k in name_lower for k in ("chain", "workflow", "pipeline", "step")):
        return SpanKind.CHAIN
    return SpanKind.INTERNAL
