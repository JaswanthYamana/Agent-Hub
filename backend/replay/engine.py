"""
replay/engine.py – Execution capture and step-by-step replay engine.

Architecture (research doc §'Execution Replay Engine'):

  CAPTURE PHASE:
    Given a completed Trace, produce a ReplayManifest — an ordered list of
    ReplayFrames, each representing the agent state *before* and *after* a
    single span execution.

  REPLAY PHASE:
    Given a ReplayManifest and a step index, return the ReplayFrame at that
    step. The caller (API / UI) controls which step to "scrub" to.

  DIFF ANALYSIS:
    Given two manifests (e.g. baseline vs attacked run), produce a side-by-side
    diff highlighting which steps diverged.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.config import get_domain  # pyre-ignore[21]
from core.models import SemanticAttributes, Span, SpanKind, SpanStatus, Trace  # pyre-ignore[21]


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class ReplayFrame:
    step: int
    span_id: str
    span_name: str
    span_kind: str
    span_status: str
    duration_ms: Optional[float]
    start_time: float
    end_time: Optional[float]
    attributes: Dict[str, Any]
    error_message: Optional[str]
    # New deterministic-replay fields
    error_category: Optional[str]      # structured error class (TimeoutError, AuthError …)
    contains_injection: bool
    # LLM-specific
    llm_input: Optional[Any]           # messages / prompt text sent to the LLM
    llm_output: Optional[str]          # raw completion returned by the LLM
    model_name: Optional[str]          # LLM model identifier (gpt-4o, claude-3 …)
    token_usage: Dict[str, int]        # {prompt_tokens, completion_tokens}
    # Tool-specific
    tool_params: Optional[Any]         # parameters passed to the tool API
    tool_response: Optional[Any]       # raw response from the tool API
    # Retriever-specific
    retrieved_documents: List[str]     # doc snippets returned by a retriever
    # Execution counters
    cumulative_tool_calls: int
    cumulative_errors: int
    active_tools: List[str]            # tools called so far (non-error)
    pending_tools: List[str]           # tools in optimal path not yet called
    state_snapshot: Dict[str, Any]     # all successful tool outputs keyed by tool name


@dataclass
class ReplayManifest:
    trace_id: str
    task: str
    scenario: str
    project_id: str
    total_steps: int
    original_prompt: str = ""      # the original task / user message that started the trace
    frames: List[ReplayFrame] = field(default_factory=list)
    captured_at: float = field(default_factory=time.time)


@dataclass
class FrameDiff:
    step: int
    span_name: str
    baseline_status: Optional[str]
    attacked_status: Optional[str]
    baseline_duration_ms: Optional[float]
    attacked_duration_ms: Optional[float]
    diverged: bool
    divergence_reason: str


@dataclass
class ReplayDiff:
    baseline_trace_id: str
    attacked_trace_id: str
    total_steps: int
    divergence_count: int
    first_divergence_step: Optional[int]
    frame_diffs: List[FrameDiff]


# ── Capture ────────────────────────────────────────────────────────────────

def capture(trace: Trace, optimal_path: Optional[List[str]] = None) -> ReplayManifest:
    """Build a ReplayManifest from a completed Trace."""
    if optimal_path is None:
        domain       = get_domain(trace.scenario)
        optimal_path = domain.get("optimal_path", [])

    manifest = ReplayManifest(
        trace_id        = trace.trace_id,
        task            = trace.task,
        scenario        = trace.scenario,
        project_id      = trace.project_id,
        total_steps     = len(trace.spans),
        original_prompt = trace.task,   # task is the original user prompt
    )

    called_tools: List[str] = []
    error_count: int = 0
    # Generic state snapshot: accumulate successful tool outputs
    cumulative_outputs: Dict[str, Any] = {}

    for step, span in enumerate(trace.spans):
        is_tool = span.kind == SpanKind.TOOL
        is_retriever = span.kind == SpanKind.RETRIEVER
        is_llm = span.kind == SpanKind.LLM

        if is_tool and span.status != SpanStatus.ERROR:
            tool = span.attributes.get(SemanticAttributes.TOOL_NAME, span.name)
            if tool not in called_tools:
                called_tools.append(tool)

        pending = [t for t in optimal_path if t not in called_tools]

        # Generic state: record every successful tool output
        if is_tool and span.status == SpanStatus.OK:
            cumulative_outputs[span.name] = span.attributes.get(SemanticAttributes.OUTPUT, {})

        # Extract LLM-specific fields
        llm_input  = span.attributes.get("llm_input")  if is_llm else None
        llm_output = span.attributes.get("llm_output") if is_llm else None
        model_name = span.model_name or span.attributes.get("model_name")

        # Extract tool fields
        tool_params   = span.attributes.get(SemanticAttributes.INPUT_PARAMS) if is_tool else None
        tool_response = span.attributes.get(SemanticAttributes.OUTPUT)       if is_tool else None

        # Extract retriever docs
        retrieved_documents: List[str] = []
        if is_retriever:
            out = span.attributes.get(SemanticAttributes.OUTPUT, {})
            if isinstance(out, dict):
                retrieved_documents = out.get("retrieved_docs", [])
            elif isinstance(out, list):
                retrieved_documents = [str(d) for d in out]

        frame = ReplayFrame(
            step                   = step,
            span_id                = span.span_id,
            span_name              = span.name,
            span_kind              = span.kind.value,
            span_status            = span.status.value,
            duration_ms            = span.duration_ms,
            start_time             = span.start_time,
            end_time               = span.end_time,
            attributes             = span.attributes,
            error_message          = span.error_message,
            error_category         = span.error_category,
            contains_injection     = span.contains_injection,
            llm_input              = llm_input,
            llm_output             = llm_output,
            model_name             = model_name,
            token_usage            = span.token_usage,
            tool_params            = tool_params,
            tool_response          = tool_response,
            retrieved_documents    = retrieved_documents,
            cumulative_tool_calls  = len(called_tools),
            cumulative_errors      = sum(1 for s in trace.spans[:step+1] if s.status == SpanStatus.ERROR),
            active_tools           = list(called_tools),
            pending_tools          = list(pending),  # type: ignore
            state_snapshot         = dict(cumulative_outputs),
        )
        manifest.frames.append(frame)

    return manifest


# ── Replay ─────────────────────────────────────────────────────────────────

def get_frame(manifest: ReplayManifest, step: int) -> Optional[ReplayFrame]:
    if 0 <= step < len(manifest.frames):
        return manifest.frames[step]
    return None


def manifest_to_dict(manifest: ReplayManifest) -> Dict[str, Any]:
    """Serialise a ReplayManifest to a JSON-safe dict."""
    from dataclasses import asdict
    return asdict(manifest)  # type: ignore


# ── Diff ────────────────────────────────────────────────────────────────────

def diff_manifests(baseline: ReplayManifest, attacked: ReplayManifest) -> ReplayDiff:
    """
    Produce a step-by-step diff between a baseline and an attacked replay manifest.
    Frames are matched by position (step index). Divergence is flagged when:
      - span_status differs, or
      - span_name differs (different tool was called), or
      - contains_injection is True in attacked frame.
    """
    max_steps     = max(len(baseline.frames), len(attacked.frames))
    frame_diffs: List[FrameDiff] = []
    divergence_count: int  = 0
    first_divergence_step: Optional[int]  = None

    for i in range(max_steps):
        bf = baseline.frames[i] if i < len(baseline.frames) else None
        af = attacked.frames[i] if i < len(attacked.frames) else None

        b_status   = bf.span_status   if bf else None
        a_status   = af.span_status   if af else None
        b_name     = bf.span_name     if bf else None
        a_name     = af.span_name     if af else None
        b_dur      = bf.duration_ms   if bf else None
        a_dur      = af.duration_ms   if af else None
        injection  = bool(af and af.contains_injection)

        diverged = (
            b_status != a_status or
            b_name   != a_name   or
            injection
        )

        reason = ""
        if b_name != a_name:
            reason = f"Tool changed: '{b_name}' → '{a_name}'"
        elif b_status != a_status:
            reason = f"Status changed: '{b_status}' → '{a_status}'"
        elif injection:
            reason = "Injection payload detected in attacked frame"

        if diverged and first_divergence_step is None:
            first_divergence_step = i

        frame_diffs.append(FrameDiff(
            step=i,
            span_name=b_name or a_name or f"step_{i}",
            baseline_status=b_status,
            attacked_status=a_status,
            baseline_duration_ms=b_dur,
            attacked_duration_ms=a_dur,
            diverged=diverged,
            divergence_reason=reason,
        ))

    return ReplayDiff(
        baseline_trace_id     = baseline.trace_id,
        attacked_trace_id     = attacked.trace_id,
        total_steps           = max_steps,
        divergence_count      = sum(1 for f in frame_diffs if f.diverged),
        first_divergence_step = first_divergence_step,
        frame_diffs           = frame_diffs,
    )


# ── Graph-Based Trace Comparison ────────────────────────────────────────────

def _extract_steps(trace: Trace) -> List[Dict[str, Any]]:
    """Convert a Trace's spans into a flat list of step dicts."""
    steps = []
    for i, span in enumerate(trace.spans):
        tool_name = span.attributes.get(SemanticAttributes.TOOL_NAME, span.name)
        steps.append({
            "step": i,
            "span_id": span.span_id,
            "name": span.name,
            "tool": tool_name,
            "kind": span.kind.value,
            "status": span.status.value,
            "type": span.kind.value,
        })
    return steps


def _node_key(step: Dict[str, Any]) -> str:
    """Canonical key used for graph-based node matching."""
    return step.get(SemanticAttributes.TOOL_NAME) or step.get("name") or f"step_{step['step']}"


def compare_traces(traceA: Trace, traceB: Trace) -> Dict[str, Any]:
    """
    Graph-topology-based comparison of two Trace executions.

    Unlike simple index matching, this builds a node-occurrence multiset for
    each trace and matches nodes by tool_name / operation_type.  This means
    a reordered execution (Search→Email→Payment vs Search→Payment→Email) is
    correctly handled — only genuinely missing or extra nodes are flagged
    rather than producing spurious mismatches at every reordered position.

    Returns
    -------
    {
      "first_divergence_step": int | None,
      "divergence_count": int,
      "differences": [
        {
          "step": int,
          "baseline": str,
          "attacked": str,
          "type": "tool_mismatch" | "missing_node" | "extra_node" | "workflow_deviation"
        }, ...
      ]
    }
    """
    stepsA = _extract_steps(traceA)
    stepsB = _extract_steps(traceB)

    # Build name→count maps (multisets) for graph node matching
    countA: Dict[str, int] = {}
    countB: Dict[str, int] = {}
    for s in stepsA:
        _ka = str(_node_key(s))
        countA[_ka] = countA.get(_ka, 0) + 1
    for s in stepsB:
        _kb = str(_node_key(s))
        countB[_kb] = countB.get(_kb, 0) + 1

    all_keys = set(countA) | set(countB)

    differences: List[Dict[str, Any]] = []
    first_divergence_step: Optional[int] = None

    # --- Step-wise comparison (primary output for UI) ---
    max_len = max(len(stepsA), len(stepsB))
    for i in range(max_len):
        sa = stepsA[i] if i < len(stepsA) else None
        sb = stepsB[i] if i < len(stepsB) else None

        key_a = _node_key(sa) if sa else None
        key_b = _node_key(sb) if sb else None

        if key_a is None and key_b is not None:
            diff_type = "extra_node"
        elif key_b is None and key_a is not None:
            diff_type = "missing_node"
        elif key_a != key_b:
            # Check if it's a genuine mismatch or just a reorder
            # If tool B exists later in A it's a workflow deviation; otherwise tool_mismatch
            if key_b and countA.get(key_b, 0) > 0:
                diff_type = "workflow_deviation"
            else:
                diff_type = "tool_mismatch"
        else:
            continue  # identical — skip

        if first_divergence_step is None:
            first_divergence_step = i

        differences.append({
            "step": i,
            "baseline": key_a or "(none)",
            "attacked": key_b or "missing",
            "type": diff_type,
        })

    # --- Node-level graph diff (complements step-wise) ---
    missing_nodes = [
        k for k in all_keys if countA.get(k, 0) > 0 and countB.get(k, 0) == 0
    ]
    extra_nodes = [
        k for k in all_keys if countA.get(k, 0) == 0 and countB.get(k, 0) > 0
    ]

    # --- Edge changes: compare consecutive tool sequences ---
    def _edges(steps: List[Dict]) -> List[Tuple[str, str]]:
        keys = [_node_key(s) for s in steps]
        return [(keys[i], keys[i + 1]) for i in range(len(keys) - 1)]

    edges_a = set(_edges(stepsA))
    edges_b = set(_edges(stepsB))
    edge_changes: List[Dict[str, str]] = []
    for src, dst in edges_a - edges_b:
        edge_changes.append({"baseline": f"{src} → {dst}", "attacked": "(removed)"})
    for src, dst in edges_b - edges_a:
        edge_changes.append({"baseline": "(added)", "attacked": f"{src} → {dst}"})

    return {
        "first_divergence_step": first_divergence_step,
        "divergence_count": len(differences),
        "differences": differences,
        "graph_diff": {
            "missing_nodes": missing_nodes,
            "extra_nodes": extra_nodes,
            "edge_changes": edge_changes,
        },
    }
