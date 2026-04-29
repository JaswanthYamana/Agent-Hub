"""
explain/divergence.py — AI-powered divergence explanation engine.

Given the diff output from compare_traces(), generates a human-readable
explanation of WHY the two traces diverged, WHAT the impact is, and
HOW to fix it.

Strategy
--------
* If OPENAI_API_KEY is set in the environment, calls the OpenAI chat
  completions API with a structured prompt.
* Otherwise (or on any API error) falls back to a deterministic
  rule-based explanation built from the diff data.  The fallback is
  always demo-able and never requires network access.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Rule-based fallback explanation ───────────────────────────────────────────

def _rule_based_explanation(diff: Dict[str, Any], task_description: str = "") -> Dict[str, str]:
    """
    Deterministic, always-available explanation built from the diff data.
    Used when no LLM key is configured or the LLM call fails.
    """
    differences: List[Dict[str, Any]] = diff.get("differences", [])
    graph_diff   = diff.get("graph_diff", {})
    missing      = graph_diff.get("missing_nodes", [])
    extra        = graph_diff.get("extra_nodes", [])
    edge_changes = graph_diff.get("edge_changes", [])
    divergence_count = diff.get("divergence_count", 0)
    first_step   = diff.get("first_divergence_step")

    if divergence_count == 0:
        return {
            "summary":       "No divergence detected — both executions followed the same workflow.",
            "root_cause":    "Traces are identical in structure.",
            "impact":        "None.",
            "suggested_fix": "No action required.",
        }

    # Build readable summary
    type_counts: Dict[str, int] = {}
    for d in differences:
        type_counts[d["type"]] = type_counts.get(d["type"], 0) + 1

    parts = []
    if type_counts.get("tool_mismatch"):
        n = type_counts["tool_mismatch"]
        examples = [d for d in differences if d["type"] == "tool_mismatch"][:2]  # type: ignore
        ex_str = "; ".join(f"{e['baseline']} → {e['attacked']}" for e in examples)
        parts.append(f"{n} tool mismatch(es) ({ex_str})")
    if type_counts.get("missing_node"):
        parts.append(f"{type_counts['missing_node']} step(s) missing in attacked trace")
    if type_counts.get("extra_node"):
        parts.append(f"{type_counts['extra_node']} extra step(s) in attacked trace")
    if type_counts.get("workflow_deviation"):
        parts.append(f"{type_counts['workflow_deviation']} workflow deviation(s) detected")

    first_diff = differences[0] if differences else {}
    first_tool_a = first_diff.get("baseline", "unknown")
    first_tool_b = first_diff.get("attacked",  "unknown")

    step_label = f"step {first_step + 1}" if first_step is not None else "an early step"

    summary = (
        f"Execution diverged at {step_label}. "
        + (f"Detected: {'; '.join(parts)}." if parts else "Differences found.")
    )

    # Root cause heuristics
    if missing:
        root_cause = (
            f"The attacked trace skipped: {', '.join(missing[:3])}. "
            "This could indicate an injected instruction that redirected the agent away from "
            "required tools, or a tool failure that caused premature termination."
        )
    elif extra:
        root_cause = (
            f"The attacked trace added unexpected steps: {', '.join(extra[:3])}. "
            "This may indicate an injected tool call or a confused reasoning chain."
        )
    elif type_counts.get("tool_mismatch"):
        root_cause = (
            f"At {step_label}, the agent chose '{first_tool_b}' instead of '{first_tool_a}'. "
            "This typically results from prompt injection, a modified tool description, or "
            "ambiguous system instructions that changed tool-selection priority."
        )
    elif type_counts.get("workflow_deviation"):
        root_cause = (
            "The execution order changed between traces. This may be caused by "
            "non-deterministic LLM output, modified context, or parallel tool invocation "
            "resolving in a different order."
        )
    else:
        root_cause = (
            "The exact root cause cannot be determined from trace data alone. "
            "Review the LLM reasoning chains at the divergence point for more detail."
        )

    # Impact
    if missing:
        impact = (
            f"The following critical steps were not executed: {', '.join(missing[:3])}. "
            "This may have left the task partially or incorrectly completed."
        )
    elif extra:
        impact = (
            "Additional unexpected tool calls were made which may have unintended effects "
            "on external systems or data."
        )
    else:
        impact = (
            f"{divergence_count} step(s) differed from the baseline, "
            "which may affect task correctness and reliability."
        )

    # Fix
    if missing:
        fix = (
            "Audit tool schema definitions and system prompt to ensure required tools are "
            "not ambiguously described. Add pre-condition checks that enforce mandatory steps "
            "before proceeding. Consider adding a workflow validator."
        )
    elif extra:
        fix = (
            "Review system prompt for injection vulnerabilities. Add tool allow-listing "
            "that restricts which tools can be called for a given task type."
        )
    else:
        fix = (
            "Strengthen the agent's system prompt with explicit step ordering. "
            "Add output validation to detect early termination or step skipping. "
            "Use the graph diff to identify which tool descriptions need hardening."
        )

    if edge_changes:
        fix += f" Also review edge changes: {len(edge_changes)} execution path change(s) detected."

    return {
        "summary":       summary,
        "root_cause":    root_cause,
        "impact":        impact,
        "suggested_fix": fix,
    }


# ── LLM-powered explanation ────────────────────────────────────────────────────

def _llm_explanation(diff: Dict[str, Any], task_description: str = "") -> Optional[Dict[str, str]]:
    """
    Call OpenAI chat completions to generate an AI explanation.
    Returns None if the API key is not configured or the call fails.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None

    try:
        import httpx  # type: ignore

        prompt = f"""You are an AI agent debugging expert.

A user ran an AI agent on this task:
"{task_description or 'AI agent task'}"

Two executions were compared and the following differences were detected:
{json.dumps(diff, indent=2)}

Please explain in clear, concise terms:
1. summary: What happened (1-2 sentences)
2. root_cause: Why it happened (1-2 sentences)  
3. impact: What the effect was on the task outcome (1 sentence)
4. suggested_fix: How to prevent this (1-2 sentences)

Respond with ONLY valid JSON with these exact 4 keys."""

        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model":       "gpt-4o-mini",
                "messages":    [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens":  400,
            },
            timeout=15.0,
        )
        if response.status_code != 200:
            logger.warning("OpenAI API returned %d", response.status_code)
            return None

        content = response.json()["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        parsed = json.loads(content)
        required = {"summary", "root_cause", "impact", "suggested_fix"}
        if required.issubset(parsed):
            return {k: str(parsed[k]) for k in required}
    except Exception as exc:
        logger.warning("LLM explanation failed: %s", exc)
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_divergence_explanation(
    diff: Dict[str, Any],
    task_description: str = "",
) -> Dict[str, str]:
    """
    Generate a human-readable explanation of trace divergence.

    Tries the LLM first (if OPENAI_API_KEY is set), falls back to the
    rule-based engine which is always available.

    Parameters
    ----------
    diff : dict
        Output of ``compare_traces()`` — contains ``differences``,
        ``graph_diff``, ``first_divergence_step``, ``divergence_count``.
    task_description : str
        The original user task / query that the agent was solving.

    Returns
    -------
    {
      "summary":       str,
      "root_cause":    str,
      "impact":        str,
      "suggested_fix": str
    }
    """
    llm_result = _llm_explanation(diff, task_description)
    if llm_result:
        return llm_result
    return _rule_based_explanation(diff, task_description)
