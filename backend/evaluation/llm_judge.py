"""
evaluation/llm_judge.py – Real LLM-based judge engine.

Uses OpenAI (gpt-4o) or Anthropic (claude-3-5-sonnet) to evaluate a complete
agent trace on five quality dimensions and returns a structured LLMJudgeResult.

Flow:
  1. Check judge_results cache    (repository.get_judge_result)
  2. Summarise trace into text    (summarize_trace)
  3. Call LLM provider            (_call_openai / _call_anthropic)
  4. Parse JSON response           (_parse_response)
  5. Persist to cache             (repository.save_judge_result)
  6. Return LLMJudgeResult

Falls back to a rule-based heuristic when:
  - No LLM API key is configured  (get_llm_provider() == "none")
  - The LLM call throws any exception (timeout, rate-limit, parse failure)
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Dict, Optional

from core.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    get_llm_provider,
)
from core.models import SemanticAttributes, LLMJudgeResult, SpanKind, SpanStatus, Trace
from storage import repository

logger = logging.getLogger(__name__)

# ── Prompt template ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert AI system reliability evaluator. \
You will be given a summary of an AI agent's execution trace and must rate its quality.

Return ONLY a valid JSON object — no markdown, no prose, no code fences — with exactly these keys:
{
  "tool_selection":         "PASS" | "WARN" | "FAIL",
  "parameter_correctness":  "PASS" | "WARN" | "FAIL",
  "reasoning_faithfulness": "PASS" | "WARN" | "FAIL",
  "workflow_order":         "PASS" | "WARN" | "FAIL",
  "task_completion":        "PASS" | "WARN" | "FAIL",
  "explanation":            "<concise explanation under 200 words>",
  "confidence_score":       <float 0.0–1.0>
}

Rubric definitions:
- tool_selection:         Did the agent choose appropriate tools for the task?
- parameter_correctness:  Were tool arguments accurate and well-formed?
- reasoning_faithfulness: Did the agent reason faithfully from context without hallucinating?
- workflow_order:         Did the tool calls follow a logical, efficient sequence?
- task_completion:        Was the overall task successfully completed?

Verdict guidance:
  PASS – meets expectations with no notable issues
  WARN – minor issues, partially correct, or suboptimal
  FAIL – clearly incorrect, missing required steps, or harmful
"""

_USER_TEMPLATE = """\
Task: {task}
Scenario: {scenario}

Execution steps ({n_steps} tool calls):
{steps}

Final output: {final_output}

Anomalies detected: {anomalies}
"""


# ── Trace summariser ──────────────────────────────────────────────────────

def summarize_trace(trace: Trace) -> Dict[str, Any]:
    """Condense a Trace into a compact dict suitable for LLM prompting."""
    steps = []
    for span in trace.spans:
        if span.kind != SpanKind.TOOL:
            continue
        tool_name  = span.attributes.get(SemanticAttributes.TOOL_NAME, span.name)
        params     = span.attributes.get(SemanticAttributes.INPUT_PARAMS, {}) or {}
        output_val = span.attributes.get(SemanticAttributes.OUTPUT) or span.attributes.get("result", "")
        is_error   = span.status == SpanStatus.ERROR
        steps.append({
            SemanticAttributes.TOOL_NAME:       tool_name,
            "parameters":    params,
            SemanticAttributes.OUTPUT:          _truncate(output_val, 300),
            "status":        span.status.value,
            "error":      span.error_message if is_error else None,
        })

    anomaly_types = list({a.get("type", "UNKNOWN") for a in (trace.anomalies or [])})

    # Use the last span's output as "final output", if any spans exist
    last_output = None
    if trace.spans:
        last = trace.spans[-1]
        last_output = last.attributes.get(SemanticAttributes.OUTPUT) or last.attributes.get("result")
    final_output = _truncate(last_output, 400)

    return {
        "task":         trace.task,
        "scenario":     trace.scenario,
        "steps":        steps,
        "final_output": final_output,
        "anomalies":    anomaly_types,
        "n_steps":      len(steps),
    }


def _truncate(value: Any, max_chars: int) -> str:
    """Convert any value to string, truncating if too long."""
    if value is None:
        return "none"
    text = json.dumps(value) if not isinstance(value, str) else value
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


# ── LLM Judge Engine ──────────────────────────────────────────────────────

class LLMJudgeEngine:
    """Evaluate a full agent trace using a real LLM and return structured verdicts."""

    async def evaluate(self, trace: Trace) -> LLMJudgeResult:
        # 1. Cache check
        cached = await repository.get_judge_result(trace.trace_id)
        if cached:
            logger.debug("LLM judge cache hit for trace %s", trace.trace_id)
            return _dict_to_result(cached, trace.trace_id)

        provider = get_llm_provider()
        if provider == "none":
            logger.warning("No LLM provider configured; using rule-based fallback for trace %s", trace.trace_id)
            result = self._rule_based_fallback(trace)
        else:
            summary = summarize_trace(trace)
            prompt  = _build_user_prompt(summary)
            try:
                if provider == "ollama":
                    # Import here to avoid circular dependencies if any, or general namespace cleanliness
                    from evaluation.ollama_client import ollama_chat
                    from core.config import OLLAMA_MODEL
                    raw = await ollama_chat(prompt)
                    used_model = OLLAMA_MODEL
                elif provider == "openai":
                    raw = await self._call_openai(prompt)
                    used_model = OPENAI_MODEL
                else:
                    raw = await self._call_anthropic(prompt)
                    used_model = ANTHROPIC_MODEL
                    
                parsed = self._parse_response(raw)
                result = LLMJudgeResult(
                    trace_id=trace.trace_id,
                    tool_selection=parsed.get("tool_selection", "WARN"),
                    parameter_correctness=parsed.get("parameter_correctness", "WARN"),
                    reasoning_faithfulness=parsed.get("reasoning_faithfulness", "WARN"),
                    workflow_order=parsed.get("workflow_order", "WARN"),
                    task_completion=parsed.get("task_completion", "WARN"),
                    explanation=parsed.get("explanation", "No explanation provided."),
                    confidence_score=parsed.get("confidence_score"),
                    source="llm",
                    judge_backend="llm",
                    model=used_model,
                )
            except Exception:
                logger.exception(
                    "LLM judge call failed for trace %s; falling back to rule-based",
                    trace.trace_id,
                )
                result = self._rule_based_fallback(trace)

        # 5. Persist to cache
        try:
            await repository.save_judge_result(result.model_dump(mode="json"))
        except Exception:
            logger.warning("Failed to cache judge result for trace %s", trace.trace_id)

        return result

    async def evaluate_span(self, span: Span, trace: Trace) -> Dict[str, Any]:
        """Evaluate a specific TOOL span for Tool Selection Accuracy."""
        from core.models import SpanKind
        
        if span.kind != SpanKind.TOOL:
            return {"error": "Only TOOL spans can be evaluated"}
        
        context = f"Goal: {trace.task}\n"
        context += f"Scenario: {trace.scenario}\n"
        context += f"Span Name: {span.name}\n"
        context += f"Input Params: {span.attributes.get(SemanticAttributes.INPUT_PARAMS, {})}\n"
        context += f"Output: {span.attributes.get(SemanticAttributes.OUTPUT, '')}\n"
        
        prompt = f"""Evaluate the tool selection accuracy for the following agent action.
        {context}
        
        Return a strict JSON response with:
        - "score" (number between 0 and 100)
        - "confidence" (number between 0.0 and 1.0)
        - "reason" (string explanation)
        """
        
        provider = get_llm_provider()
        if provider == "none" or not provider:
            return {"score": 100, "confidence": 1.0, "reason": "No LLM configured for evaluation"}
            
        try:
            if provider == "openai":
                response = await self._call_openai(prompt)
            else:
                response = await self._call_anthropic(prompt)
                
            import json, re
            cleaned = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                raise ValueError("No JSON object found")
            result = json.loads(match.group())
            
            # Application of escalation criteria
            if result.get("confidence", 1.0) < 0.4:
                span.attributes["human_review_required"] = True
                
            return result
        except Exception as e:
            return {"score": 0, "confidence": 0.0, "reason": f"Evaluation failed: {e}", "error": True}

    # ── Provider calls ────────────────────────────────────────────────────

    async def _call_openai(self, user_prompt: str) -> str:
        from openai import AsyncOpenAI  # deferred import — optional dependency
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    async def _call_anthropic(self, user_prompt: str) -> str:
        from anthropic import AsyncAnthropic  # deferred import — optional dependency
        client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text if message.content else ""

    # ── Response parsing ──────────────────────────────────────────────────

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response, stripping any markdown fences."""
        # Strip code fences that some models add despite instructions
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
        # Find the first {...} block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
        data = json.loads(match.group())
        # Normalise verdict strings to upper-case
        for key in ("tool_selection", "parameter_correctness",
                    "reasoning_faithfulness", "workflow_order", "task_completion"):
            if key in data and isinstance(data[key], str):
                v = data[key].upper()
                data[key] = v if v in ("PASS", "WARN", "FAIL") else "WARN"
        return data

    # ── Rule-based fallback ───────────────────────────────────────────────

    def _rule_based_fallback(self, trace: Trace) -> LLMJudgeResult:
        """
        Derive LLMJudgeResult verdicts from already-available numeric metrics
        stored on the trace, without any LLM call.
        """
        m = trace.metrics or {}

        def _score(key: str) -> float:
            return float(m.get(key, 1.0))

        def _verdict(s: float) -> str:
            if s >= 0.8: return "PASS"
            if s >= 0.5: return "WARN"
            return "FAIL"

        anomaly_types = {a.get("type", "") for a in (trace.anomalies or [])}
        has_injection  = "PROMPT_INJECTION" in anomaly_types
        has_hijacking  = "GOAL_HIJACKING"   in anomaly_types

        tool_sel   = _verdict(_score("tool_selection_accuracy"))
        param_corr = _verdict(_score("parameter_correctness"))
        faithful   = "FAIL" if has_injection or has_hijacking else _verdict(_score("overall_reliability_score"))
        wf_order   = _verdict(_score("workflow_correctness"))
        task_comp  = _verdict(_score("task_completion_rate"))

        parts = [
            f"Tool selection: {tool_sel}.",
            f"Parameter correctness: {param_corr}.",
            f"Reasoning faithfulness: {faithful}.",
            f"Workflow order: {wf_order}.",
            f"Task completion: {task_comp}.",
        ]
        if anomaly_types:
            parts.append(f"Anomalies: {', '.join(sorted(anomaly_types))}.")
        explanation = " ".join(parts) + " (Rule-based evaluation — no LLM provider configured.)"

        return LLMJudgeResult(
            trace_id=trace.trace_id,
            tool_selection=tool_sel,
            parameter_correctness=param_corr,
            reasoning_faithfulness=faithful,
            workflow_order=wf_order,
            task_completion=task_comp,
            explanation=explanation,
            confidence_score=None,
            source="rule_based",
            judge_backend="rule_based_fallback",
            model=None,
        )


# ── Helpers ───────────────────────────────────────────────────────────────

def _build_user_prompt(summary: Dict[str, Any]) -> str:
    steps_text = "\n".join(
        f"  {i+1}. {s[SemanticAttributes.TOOL_NAME]}({json.dumps(s['parameters'])}) "
        f"→ status={s['status']}"
        + (f", error={s['error']}" if s["error"] else "")
        + f"\n     output: {s[SemanticAttributes.OUTPUT]}"
        for i, s in enumerate(summary["steps"])
    ) or "  (no tool calls)"

    return _USER_TEMPLATE.format(
        task=summary["task"],
        scenario=summary["scenario"],
        n_steps=summary["n_steps"],
        steps=steps_text,
        final_output=summary["final_output"],
        anomalies=", ".join(summary["anomalies"]) if summary["anomalies"] else "none",
    )


def _dict_to_result(d: Dict[str, Any], trace_id: str) -> LLMJudgeResult:
    """Reconstruct an LLMJudgeResult from a repository row dict."""
    return LLMJudgeResult(
        trace_id=trace_id,
        tool_selection=d.get("tool_selection", "WARN"),
        parameter_correctness=d.get("parameter_correctness") or d.get("param_correct", "WARN"),
        reasoning_faithfulness=d.get("reasoning_faithfulness") or d.get("faithfulness", "WARN"),
        workflow_order=d.get("workflow_order", "WARN"),
        task_completion=d.get("task_completion", "WARN"),
        explanation=d.get("explanation", ""),
        confidence_score=d.get("confidence_score"),
        source=d.get("source", "llm"),
        judge_backend=d.get("judge_backend", "rule_based_fallback" if d.get("source") == "rule_based" else "llm"),
        model=d.get("model"),
        created_at=d.get("created_at", time.time()),
    )
