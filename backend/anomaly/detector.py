"""
anomaly/detector.py – Multi-layer anomaly detection engine.

Two detection strategies (as described in the research document §'Anomaly Detection'):

  LAYER 1 – Pattern-based detectors (11 patterns):
    Each detector inspects the span list for a known failure signature.

  LAYER 2 – Statistical baseline comparison:
    Compare span.duration_ms against per-span-name baselines stored in the DB.
    Anomaly when |z| > ANOMALY_Z_SCORE_THRESHOLD.

Both layers return AnomalyRecord dicts that share the same schema so the
API and UI can treat them identically.
"""
from __future__ import annotations

import math
import time
import uuid
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from core.config import (
    Z_SCORE_THRESHOLD as ANOMALY_Z_SCORE_THRESHOLD,
    MAX_STEP_DURATION_MS,
    MAX_TOOL_CALLS,
    REASONING_LOOP_THRESHOLD,
    get_domain,
)
from core.models import SemanticAttributes, AnomalyType, Span, SpanKind, SpanStatus, Trace

# Scenarios where off-path tool usage is intentional — suppress false positives
_ADVERSARIAL_SCENARIOS: frozenset[str] = frozenset({
    "prompt_injection", "idpi", "schema_poisoning", "schema_poison",
    "memory_poison", "tool_fuzzing", "tool_error", "goal_hijacking", "jailbreak",
})

# ── Helpers ────────────────────────────────────────────────────────────────

def _record(
    *,
    trace_id: str,
    anomaly_type: AnomalyType,
    severity: str,
    description: str,
    evidence: Dict[str, Any],
    span_id: Optional[str] = None,
    span_name: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id":          str(uuid.uuid4()),
        "trace_id":    trace_id,
        "span_id":     span_id or "",
        "span_name":   span_name or "",
        "type":        anomaly_type.value,
        "severity":    severity,
        "description": description,
        "evidence":    evidence,
        "created_at":  time.time(),
    }


# ── Pattern detectors ──────────────────────────────────────────────────────

def _detect_reasoning_loops(trace: Trace) -> List[Dict]:
    """Same tool called with ERROR status ≥ REASONING_LOOP_THRESHOLD times."""
    results: List[Dict] = []
    fail_counts: Counter = Counter()
    for s in trace.spans:
        if s.kind == SpanKind.TOOL and s.status == SpanStatus.ERROR:
            fail_counts[s.name] += 1
    for tool, count in fail_counts.items():
        if count >= REASONING_LOOP_THRESHOLD:
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.REASONING_LOOP,
                severity="high",
                description=(
                    f"Tool '{tool}' failed {count} times (total across trace). "
                    "Agent is likely stuck in a retry loop without backoff."
                ),
                evidence={SemanticAttributes.TOOL_NAME: tool, "fail_count": count},
            ))
    return results


def _detect_wrong_tool_selection(trace: Trace) -> List[Dict]:
    """Tool calls that are not on the optimal path and not generic.

    Skipped for adversarial scenarios where off-path tool usage is intentional
    (e.g. an injected payload forcing a web_search call).  The prompt_injection
    and schema_poisoning detectors handle those cases instead.
    """
    if trace.scenario in _ADVERSARIAL_SCENARIOS:
        return []
    domain   = get_domain(trace.scenario)
    opt_path = set(domain.get("optimal_path", []))
    results: List[Dict] = []
    if not opt_path:
        return results
    for s in trace.spans:
        if s.kind != SpanKind.TOOL:
            continue
        tool = s.attributes.get(SemanticAttributes.TOOL_NAME, s.name)
        if tool and tool not in opt_path:
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.WRONG_TOOL_SELECTION,
                severity="medium",
                description=f"Tool '{tool}' is not in domain optimal path.",
                evidence={SemanticAttributes.TOOL_NAME: tool, "optimal_path": list(opt_path)},
                span_id=s.span_id, span_name=s.name,
            ))
    return results


def _detect_wrong_parameters(trace: Trace) -> List[Dict]:
    """Tool calls missing required parameters as defined in domain config."""
    domain     = get_domain(trace.scenario)
    req_params = domain.get("required_params", {})
    results: List[Dict] = []
    for s in trace.spans:
        if s.kind != SpanKind.TOOL:
            continue
        tool   = s.attributes.get(SemanticAttributes.TOOL_NAME, s.name)
        params = s.attributes.get(SemanticAttributes.INPUT_PARAMS, {}) or {}
        req    = req_params.get(tool, [])
        missing = [r for r in req if r not in params or params[r] in (None, "", [], {})]
        if missing:
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.WRONG_PARAMETERS,
                severity="medium",
                description=f"Tool '{tool}' called with missing required parameters.",
                evidence={SemanticAttributes.TOOL_NAME: tool, "missing_params": missing},
                span_id=s.span_id, span_name=s.name,
            ))
    return results


def _detect_skipped_steps(trace: Trace) -> List[Dict]:
    """Optimal path steps that were never called.

    Only meaningful for scenarios where a specific tool path is expected.
    Adversarial scenarios (injection, poisoning) naturally skip steps, so we
    suppress false positives there.
    """
    if trace.scenario in _ADVERSARIAL_SCENARIOS:
        return []
    domain    = get_domain(trace.scenario)
    opt_path  = domain.get("optimal_path", [])
    results: List[Dict] = []
    if not opt_path or not trace.completed:
        return results
    called = {
        s.attributes.get(SemanticAttributes.TOOL_NAME, s.name)
        for s in trace.spans
        if s.kind == SpanKind.TOOL and s.status != SpanStatus.ERROR
    }
    skipped = [t for t in opt_path if t not in called]
    if skipped:
        results.append(_record(
            trace_id=trace.trace_id,
            anomaly_type=AnomalyType.SKIPPED_STEP,
            severity="high",
            description=f"Agent skipped {len(skipped)} required step(s): {skipped}",
            evidence={"skipped_tools": skipped, "called_tools": list(called)},
        ))
    return results


def _detect_hallucinated_outputs(trace: Trace) -> List[Dict]:
    results: List[Dict] = []
    for s in trace.spans:
        if s.status == SpanStatus.HALLUCINATED:
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.HALLUCINATED_OUTPUT,
                severity="critical",
                description=(
                    f"Span '{s.name}' is marked HALLUCINATED. The agent claimed "
                    "completion of an action that was never executed."
                ),
                evidence={SemanticAttributes.OUTPUT: s.attributes.get(SemanticAttributes.OUTPUT, "")},
                span_id=s.span_id, span_name=s.name,
            ))
    return results


def _detect_prompt_injection(trace: Trace) -> List[Dict]:
    results: List[Dict] = []
    for s in trace.spans:
        if s.contains_injection:
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.PROMPT_INJECTION,
                severity="critical",
                description=(
                    f"Prompt injection payload detected in span '{s.name}'. "
                    "Indirect Prompt Injection (IDPI) attack signature present."
                ),
                evidence={
                    "payload": s.injection_payload or "",
                    "attack_type": s.attributes.get("attack_type", "idpi"),
                },
                span_id=s.span_id, span_name=s.name,
            ))
    return results


def _detect_unauthorized_tools(trace: Trace) -> List[Dict]:
    domain   = get_domain(trace.scenario)
    unauth   = domain.get("unauthorized_tools", set())
    allowed  = domain.get("allowed_tools", set())
    results = []
    for s in trace.spans:
        if s.kind != SpanKind.TOOL:
            continue
        tool = s.attributes.get(SemanticAttributes.TOOL_NAME, s.name)
        is_unauthorized = (allowed and tool not in allowed) or (tool in unauth)
        if is_unauthorized:
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.UNAUTHORIZED_TOOL,
                severity="high",
                description=(
                    f"Agent invoked unauthorised tool '{tool}'. "
                    "Tool is outside the agent's defined permission boundary."
                ),
                evidence={
                    "tool": tool,
                    "unauthorized_list": list(unauth),
                    "allowed_tools": list(allowed),
                },
                span_id=s.span_id, span_name=s.name,
            ))
    return results


def _detect_excessive_steps(trace: Trace) -> List[Dict]:
    tool_calls = sum(1 for s in trace.spans if s.kind == SpanKind.TOOL)
    if tool_calls > MAX_TOOL_CALLS:
        return [_record(
            trace_id=trace.trace_id,
            anomaly_type=AnomalyType.EXCESSIVE_STEPS,
            severity="medium",
            description=(
                f"Agent made {tool_calls} tool calls (threshold: {MAX_TOOL_CALLS}). "
                "Indicates inefficient execution or runaway orchestration."
            ),
            evidence={"tool_call_count": tool_calls, "threshold": MAX_TOOL_CALLS},
        )]
    return []


def _detect_partial_completion(trace: Trace) -> List[Dict]:
    if trace.completed and trace.partial_completion and not trace.success:
        return [_record(
            trace_id=trace.trace_id,
            anomaly_type=AnomalyType.PARTIAL_COMPLETION,
            severity="medium",
            description=(
                "Agent terminated with partial completion. "
                "Task was not fully achieved despite some progress."
            ),
            evidence={"scenario": trace.scenario, "final_summary": trace.final_summary},
        )]
    return []


def _detect_schema_poisoning(trace: Trace) -> List[Dict]:
    results: List[Dict] = []
    for s in trace.spans:
        payload = (s.injection_payload or "").lower() + str(s.attributes).lower()
        exfil   = ["exfiltrate", "attacker.com", "evil.com", "c2.", ".onion", "webhook.site"]
        if any(m in payload for m in exfil):
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.SCHEMA_POISONING,
                severity="critical",
                description=(
                    f"Tool '{s.name}' carries an exfiltration payload. "
                    "Tool description has been poisoned with hidden instructions."
                ),
                evidence={"span_name": s.name, "payload_fragment": payload[:200]},
                span_id=s.span_id, span_name=s.name,
            ))
    return results


def _detect_abnormal_latency(trace: Trace) -> List[Dict]:
    results: List[Dict] = []
    for s in trace.spans:
        dur = s.duration_ms
        if dur is not None and dur > MAX_STEP_DURATION_MS:
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.ABNORMAL_LATENCY,
                severity="low",
                description=(
                    f"Span '{s.name}' took {dur:.0f} ms "
                    f"(threshold: {MAX_STEP_DURATION_MS} ms)."
                ),
                evidence={"duration_ms": dur, "threshold_ms": MAX_STEP_DURATION_MS},
                span_id=s.span_id, span_name=s.name,
            ))
    return results


def _detect_workflow_path_deviation(trace: Trace) -> List[Dict]:
    """
    Comparison of the *actual* tool execution sequence against the domain
    optimal path using sequence edit distance.

    A high edit distance ratio (> 0.5) relative to the optimal path length
    indicates that the agent followed a substantially different workflow.
    This catches unexpected branching, extra steps, and reorderings that
    rule-based detectors (wrong_tool_selection / skipped_step) may miss when
    the overall path is partially correct.

    Suppressed for adversarial scenarios where deviation is intentional.
    """
    if trace.scenario in _ADVERSARIAL_SCENARIOS:
        return []
    domain    = get_domain(trace.scenario)
    opt_path  = domain.get("optimal_path", [])
    if not opt_path or not trace.completed:
        return []

    actual_sequence: List[str] = [
        s.attributes.get(SemanticAttributes.TOOL_NAME, s.name)
        for s in trace.spans
        if s.kind == SpanKind.TOOL
    ]

    # Levenshtein edit distance (insertions + deletions only, no substitutions)
    m, n = len(opt_path), len(actual_sequence)
    if m == 0:
        return []

    # Simple DP — O(m*n)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        new_dp = [i] + [0] * n
        for j in range(1, n + 1):
            if opt_path[i - 1] == actual_sequence[j - 1]:
                new_dp[j] = dp[j - 1]
            else:
                new_dp[j] = 1 + min(dp[j], new_dp[j - 1], dp[j - 1])
        dp = new_dp

    edit_distance = dp[n]
    ratio         = edit_distance / m   # normalised by optimal path length

    if ratio > 0.5:
        return [_record(
            trace_id=trace.trace_id,
            anomaly_type=AnomalyType.WORKFLOW_DEVIATION,
            severity="medium",
            description=(
                f"Agent workflow diverged significantly from the expected path "
                f"(edit distance {edit_distance}/{m} steps, ratio {ratio:.2f}). "
                "Actual tool sequence does not match the optimal execution pattern."
            ),
            evidence={
                "optimal_path":    opt_path,
                "actual_sequence": actual_sequence,
                "edit_distance":   edit_distance,
                "deviation_ratio": round(ratio, 2),
            },
        )]
    return []


def _detect_goal_hijacking(trace: Trace) -> List[Dict]:
    """
    Detects when the agent transitions to executing attacker-defined goals
    rather than the original task.

    Indicators:
    1. An injection payload is present AND the agent subsequently calls a
       tool outside the domain's authorised set (evidence of hijack success).
    2. The agent's final_summary contains keywords matching known exfiltration /
       redirection goals even when no injection flag is set.
    """
    results: List[Dict] = []
    EXFIL_KEYWORDS = [
        "exfiltrat", "attacker", "evil.com", "c2.", ".onion", "webhook.site",
        "ignore previous", "ignore all", "new objective", "cancel existing",
        "re-book for", "send to attacker",
    ]

    # Check 1: injection present + off-domain tool used after injection
    injection_spans = [s for s in trace.spans if s.contains_injection]
    if injection_spans:
        domain   = get_domain(trace.scenario)
        unauth   = domain.get("unauthorized_tools", set())
        allowed  = domain.get("allowed_tools", set())
        # Find any tool span that comes after the injection and is unauthorised
        inj_step = min(
            trace.spans.index(s) for s in injection_spans
            if s in trace.spans
        )
        post_injection_tools = [
            s for s in trace.spans[inj_step + 1:]
            if s.kind == SpanKind.TOOL
        ]
        hijacked = [
            s for s in post_injection_tools
            if (
                (allowed and s.attributes.get(SemanticAttributes.TOOL_NAME, s.name) not in allowed)
                or (s.attributes.get(SemanticAttributes.TOOL_NAME, s.name) in unauth)
            )
        ]
        if hijacked:
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.GOAL_HIJACKING,
                severity="critical",
                description=(
                    f"Goal hijacking confirmed: agent executed unauthorised tool(s) "
                    f"{[s.name for s in hijacked]} following an injection payload. "
                    "The agent was redirected to the attacker's objective."
                ),
                evidence={
                    "injection_payload": injection_spans[0].injection_payload,
                    "hijacked_tools": [s.name for s in hijacked],
                },
            ))

    # Check 2: exfiltration keywords in final summary
    summary_lower = trace.final_summary.lower()
    hits = [kw for kw in EXFIL_KEYWORDS if kw in summary_lower]
    if hits:
        results.append(_record(
            trace_id=trace.trace_id,
            anomaly_type=AnomalyType.GOAL_HIJACKING,
            severity="high",
            description=(
                "Agent final summary contains exfiltration/redirection keywords, "
                f"suggesting goal hijacking: {hits}"
            ),
            evidence={"keywords_found": hits, "summary": trace.final_summary[:300]},
        ))

    return results


# ── Statistical baseline comparison ───────────────────────────────────────

def _detect_statistical_outliers(
    trace: Trace, baselines: Dict[str, Any]
) -> List[Dict]:
    """Compare span durations against historical per-span-name baselines."""
    results: List[Dict] = []
    if not baselines:
        return results
    for s in trace.spans:
        if s.duration_ms is None:
            continue
        bl = baselines.get(s.name)
        if bl is None:
            continue
        mean: float = bl.get("mean", 0)
        std:  float = bl.get("std", 0)
        if std < 1:            # < 1 ms std → not enough variance to judge
            continue
        z = abs(s.duration_ms - mean) / std
        if z > ANOMALY_Z_SCORE_THRESHOLD:
            direction = "slower" if s.duration_ms > mean else "faster"
            results.append(_record(
                trace_id=trace.trace_id,
                anomaly_type=AnomalyType.STATISTICAL_OUTLIER,
                severity="low" if z < 4 else "medium",
                description=(
                    f"Span '{s.name}' is a statistical outlier: {s.duration_ms:.1f} ms "
                    f"vs baseline mean {mean:.1f} ms (z={z:.2f}, {direction} than usual)."
                ),
                evidence={
                    "duration_ms": s.duration_ms,
                    "baseline_mean": mean,
                    "baseline_std": std,
                    "z_score": round(z, 2),
                    "p95": bl.get("p95"),
                },
                span_id=s.span_id, span_name=s.name,
            ))
    return results


# ── Public API ─────────────────────────────────────────────────────────────

class AnomalyDetector:
    """
    Run all detection layers and return a unified list of anomaly records.

    Usage:
        detector = AnomalyDetector()
        anomalies = detector.detect(trace, baselines={"flight_search_api": {...}})
    """

    _PATTERN_DETECTORS = [
        _detect_reasoning_loops,
        _detect_wrong_tool_selection,
        _detect_wrong_parameters,
        _detect_skipped_steps,
        _detect_hallucinated_outputs,
        _detect_prompt_injection,
        _detect_unauthorized_tools,
        _detect_excessive_steps,
        _detect_partial_completion,
        _detect_schema_poisoning,
        _detect_abnormal_latency,
        _detect_workflow_path_deviation,   # sequence edit-distance check
        _detect_goal_hijacking,            # post-injection unauthorised tool / exfil keyword
    ]

    def detect(
        self,
        trace: Trace,
        baselines: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        found: List[Dict] = []
        for fn in self._PATTERN_DETECTORS:
            try:
                found.extend(fn(trace))
            except Exception:
                pass
        if baselines:
            found.extend(_detect_statistical_outliers(trace, baselines))
        # Remove duplicates keyed on (type, span_id)
        seen: set = set()
        unique: List[Dict] = []
        for r in found:
            key = (r["type"], r["span_id"])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique
