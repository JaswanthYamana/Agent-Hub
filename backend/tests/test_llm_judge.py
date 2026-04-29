# pyre-ignore-all-errors
"""
tests/test_llm_judge.py – Unit tests for evaluation.llm_judge

Run with:  pytest backend/tests/test_llm_judge.py -v
(from the repo root, with PYTHONPATH=backend)
"""
from __future__ import annotations

import json
import time
import types
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest  # pyre-ignore[21]

# ---------------------------------------------------------------------------
# Minimal stub models so tests don't require the full backend package tree
# ---------------------------------------------------------------------------

class _SpanStatus:
    ERROR   = types.SimpleNamespace(value="error")
    SUCCESS = types.SimpleNamespace(value="success")

class _SpanKind:
    TOOL  = "TOOL"
    LLM   = "LLM"

class _Span:
    def __init__(self, **kw):
        self.span_id      = kw.get("span_id", "s1")
        self.name         = kw.get("name", "tool_call")
        self.kind         = kw.get("kind", _SpanKind.TOOL)
        self.tool_name    = kw.get("tool_name")
        self.input_data   = kw.get("input_data", {})
        self.output_data  = kw.get("output_data", "ok")
        self.status       = kw.get("status", _SpanStatus.SUCCESS)
        self.error        = kw.get("error")
        self.attributes   = kw.get("attributes", {})
        self.error_message = kw.get("error_message") or kw.get("error")

class _Trace:
    def __init__(self, **kw):
        self.trace_id = kw.get("trace_id", "trace-001")
        self.task     = kw.get("task", "Get weather in Paris")
        self.scenario = kw.get("scenario", "weather_api")
        self.spans    = kw.get("spans", [])
        self.anomalies= kw.get("anomalies", [])
        self.metrics  = kw.get("metrics", {})

# Patch the import paths before importing the module under test
import sys, importlib

# Save original sys.modules entries so other test files get the real packages
_saved_modules = {k: sys.modules.get(k) for k in [
    "core", "core.config", "core.models", "storage", "storage.repository"
]}

# Stub core.config
config_mod: Any = types.ModuleType("core.config")  # pyre-ignore[16]
config_mod.OPENAI_API_KEY    = ""  # pyre-ignore[16]
config_mod.ANTHROPIC_API_KEY = ""  # pyre-ignore[16]
config_mod.OPENAI_MODEL      = "gpt-4o"  # pyre-ignore[16]
config_mod.ANTHROPIC_MODEL   = "claude-3-5-sonnet-20241022"  # pyre-ignore[16]
config_mod.get_llm_provider  = lambda: "none"
# Thresholds consumed by anomaly.detector and evaluation.metrics  # pyre-ignore[16]
config_mod.MAX_TOOL_CALLS           = 15  # pyre-ignore[16]
config_mod.REASONING_LOOP_THRESHOLD = 3  # pyre-ignore[16]
config_mod.MAX_STEP_DURATION_MS     = 10_000  # pyre-ignore[16]
config_mod.Z_SCORE_THRESHOLD        = 2.5  # pyre-ignore[16]
config_mod.DATABASE_URL = "postgresql://localhost/test_db"  # pyre-ignore[16]
config_mod.API_KEY      = ""  # pyre-ignore[16]
config_mod.ENABLE_AUTH  = False  # pyre-ignore[16]
config_mod.DEFAULT_DOMAIN = "flight_booking"  # pyre-ignore[16]
config_mod.DOMAINS = {
    "flight_booking": {
        "name": "Flight Booking",
        "scenarios": {
            "normal", "tool_error", "param_error", "reasoning_loop",
            "hallucination", "idpi", "schema_poison", "schema_poisoning",
            "memory_poison", "prompt_injection", "partial_completion",
            "goal_hijacking", "jailbreak", "context_overflow",
        },
        "optimal_path": [
            "flight_search_api", "price_comparison_tool",
            "booking_api", "payment_api", "email_api",
        ],
        "required_params": {
            "flight_search_api":     ["origin", "destination", "date", "passengers"],
            "price_comparison_tool": ["flight_ids"],
            "booking_api":           ["flight_id", "passenger_name", "passenger_email", "payment_token"],
            "payment_api":           ["booking_id", "amount", "payment_method"],
            "email_api":             ["to", "subject", "body"],
        },
        "unauthorized_tools": {"web_search", "document_retriever"},
    },
    "generic": {
        "name": "Generic",
        "scenarios": set(),
        "optimal_path": [],
        "required_params": {},
        "unauthorized_tools": set(),
    },
}
def _get_domain(scenario: str):
    for d in config_mod.DOMAINS.values():
        if scenario in d.get("scenarios", set()):
            return d
    return config_mod.DOMAINS["generic"]  # pyre-ignore[16]
config_mod.get_domain = _get_domain
sys.modules["core"]        = types.ModuleType("core")
sys.modules["core.config"] = config_mod

# Stub core.models
models_mod: Any = types.ModuleType("core.models")  # pyre-ignore[16]
models_mod.Trace       = _Trace  # pyre-ignore[16]
models_mod.Span        = _Span  # pyre-ignore[16]
models_mod.SpanKind    = _SpanKind  # pyre-ignore[16]
models_mod.SpanStatus  = _SpanStatus

from enum import Enum
class _SemanticAttributes(str, Enum):
    TOOL_NAME = "tool.name"
    INPUT_PARAMS = "tool.input_params"
    OUTPUT = "tool.output"
  # pyre-ignore[16]
models_mod.SemanticAttributes = _SemanticAttributes

class _LLMJudgeResult:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
    def model_dump(self, **_):
        return self.__dict__
  # pyre-ignore[16]
models_mod.LLMJudgeResult = _LLMJudgeResult
sys.modules["core.models"] = models_mod

# Stub storage.repository
repo_mod: Any = types.ModuleType("storage.repository")  # pyre-ignore[16]
repo_mod.get_judge_result  = AsyncMock(return_value=None)  # pyre-ignore[16]
repo_mod.save_judge_result = AsyncMock(return_value=None)
sys.modules["storage"]            = types.ModuleType("storage")
sys.modules["storage.repository"] = repo_mod

# Now import the module under test
sys.path.insert(0, "backend")
import importlib.util, os

_spec: Any = importlib.util.spec_from_file_location(
    "evaluation.llm_judge",
    os.path.join(os.path.dirname(__file__), "..", "evaluation", "llm_judge.py"),
)  # pyre-ignore[6, 9]
llm_judge_mod = importlib.util.module_from_spec(_spec)  # pyre-ignore[16]
_spec.loader.exec_module(llm_judge_mod)

# Register so that patch("evaluation.llm_judge.*") works in tests
sys.modules["evaluation.llm_judge"] = llm_judge_mod

# Restore real sys.modules entries so downstream test files (test_metrics,
# test_replay, etc.) import the genuine backend packages instead of stubs.
for _k, _v in _saved_modules.items():
    if _v is None:
        sys.modules.pop(_k, None)
    else:
        sys.modules[_k] = _v
del _saved_modules

summarize_trace  = llm_judge_mod.summarize_trace
LLMJudgeEngine   = llm_judge_mod.LLMJudgeEngine
_build_user_prompt = llm_judge_mod._build_user_prompt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trace(**kw) -> _Trace:
    return _Trace(**kw)

def _tool_span(tool_name="search", status=None, error=None) -> _Span:
    s = _Span(
        kind=_SpanKind.TOOL,
        name=tool_name,
        tool_name=tool_name,
        input_data={"q": "Paris weather"},
        output_data="sunny 22°C",
        status=status or _SpanStatus.SUCCESS,
        error=error,
    )
    return s

# ---------------------------------------------------------------------------
# Tests: summarize_trace
# ---------------------------------------------------------------------------

class TestSummarizeTrace:
    def test_basic(self):
        spans = [_tool_span("weather_api"), _tool_span("calendar_add")]
        trace = _make_trace(task="Do X", scenario="s1", spans=spans, anomalies=[])
        s = summarize_trace(trace)
        assert s["task"] == "Do X"
        assert s["n_steps"] == 2
        assert s["steps"][0][models_mod.SemanticAttributes.TOOL_NAME] == "weather_api"

    def test_empty_spans(self):
        trace = _make_trace(task="Empty", scenario="s1", spans=[], anomalies=[])
        s = summarize_trace(trace)
        assert s["n_steps"] == 0
        assert s["steps"] == []
        assert s["final_output"] == "none"

    def test_anomalies_included(self):
        trace = _make_trace(
            task="T", scenario="s",
            spans=[_tool_span()],
            anomalies=[{"type": "PROMPT_INJECTION", "severity": "HIGH"}],
        )
        s = summarize_trace(trace)
        assert "PROMPT_INJECTION" in s["anomalies"]

    def test_error_span_includes_error_field(self):
        err_span = _tool_span("bad_tool", status=_SpanStatus.ERROR, error="Timeout")
        trace = _make_trace(task="T", scenario="s", spans=[err_span], anomalies=[])
        s = summarize_trace(trace)
        assert s["steps"][0]["error"] == "Timeout"

    def test_non_tool_spans_excluded(self):
        llm_span = _Span(kind=_SpanKind.LLM, name="reasoning")
        tool_span = _tool_span("api_call")
        trace = _make_trace(task="T", scenario="s", spans=[llm_span, tool_span], anomalies=[])
        s = summarize_trace(trace)
        assert s["n_steps"] == 1
        assert s["steps"][0][models_mod.SemanticAttributes.TOOL_NAME] == "api_call"


# ---------------------------------------------------------------------------
# Tests: LLMJudgeEngine.evaluate — cache path
# ---------------------------------------------------------------------------

class TestEvaluateCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_result_without_llm_call(self):
        cached_row = {
            "tool_selection": "PASS",
            "parameter_correctness": "PASS",
            "reasoning_faithfulness": "PASS",
            "workflow_order": "PASS",
            "task_completion": "PASS",
            "explanation": "cached explanation",
            "confidence_score": 0.9,
            "source": "llm",
            "model": "gpt-4o",
            "created_at": time.time(),
        }
        trace = _make_trace()
        with patch.object(repo_mod, "get_judge_result", AsyncMock(return_value=cached_row)):
            engine = LLMJudgeEngine()
            result = await engine.evaluate(trace)
        assert result.source == "llm"
        assert result.explanation == "cached explanation"


# ---------------------------------------------------------------------------
# Tests: LLMJudgeEngine.evaluate — rule-based fallback (no LLM key)
# ---------------------------------------------------------------------------

class TestEvaluateRuleBasedFallback:
    @pytest.mark.asyncio
    async def test_fallback_when_no_provider(self):
        trace = _make_trace(
            metrics={"tool_selection_accuracy": 0.9, "parameter_correctness": 0.8,
                     "workflow_correctness": 0.9, "task_completion_rate": 1.0,
                     "overall_reliability_score": 0.9},
        )
        with patch.object(repo_mod, "get_judge_result", AsyncMock(return_value=None)), \
             patch.object(repo_mod, "save_judge_result", AsyncMock()):
            engine = LLMJudgeEngine()
            result = await engine.evaluate(trace)
        assert result.source == "rule_based"
        assert result.tool_selection == "PASS"
        assert result.model is None

    @pytest.mark.asyncio
    async def test_fallback_fail_on_injection_anomaly(self):
        trace = _make_trace(
            metrics={"overall_reliability_score": 0.95},
            anomalies=[{"type": "PROMPT_INJECTION"}],
        )
        with patch.object(repo_mod, "get_judge_result", AsyncMock(return_value=None)), \
             patch.object(repo_mod, "save_judge_result", AsyncMock()):
            engine = LLMJudgeEngine()
            result = await engine.evaluate(trace)
        assert result.reasoning_faithfulness == "FAIL"


# ---------------------------------------------------------------------------
# Tests: LLMJudgeEngine._parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    engine: Any  # pyre-ignore[16]
    
    def setup_method(self):
        self.engine = LLMJudgeEngine()

    def test_valid_json(self):
        payload = {
            "tool_selection": "PASS",
            "parameter_correctness": "FAIL",
            "reasoning_faithfulness": "WARN",
            "workflow_order": "PASS",
            "task_completion": "PASS",
            "explanation": "All good",  # pyre-ignore[16]
            "confidence_score": 0.85,
        }
        result = self.engine._parse_response(json.dumps(payload))
        assert result["tool_selection"] == "PASS"
        assert result["confidence_score"] == 0.85
  # pyre-ignore[16]
    def test_strips_markdown_fences(self):
        raw = "```json\n{\"tool_selection\": \"pass\", \"parameter_correctness\": \"fail\", \"reasoning_faithfulness\": \"warn\", \"workflow_order\": \"pass\", \"task_completion\": \"pass\", \"explanation\": \"ok\", \"confidence_score\": 0.7}\n```"
        result = self.engine._parse_response(raw)
        assert result["tool_selection"] == "PASS"   # normalised to upper
        assert result["parameter_correctness"] == "FAIL"
  # pyre-ignore[16]
    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            self.engine._parse_response("not json at all")

    def test_unknown_verdict_normalised_to_warn(self):
        payload = json.dumps({
            "tool_selection": "okay",
            "parameter_correctness": "PASS",
            "reasoning_faithfulness": "PASS",
            "workflow_order": "PASS",
            "task_completion": "PASS",
            "explanation": "x",  # pyre-ignore[16]
            "confidence_score": 0.5,
        })
        result = self.engine._parse_response(payload)
        assert result["tool_selection"] == "WARN"


# ---------------------------------------------------------------------------
# Tests: LLMJudgeEngine.evaluate — live LLM call path (mocked)
# ---------------------------------------------------------------------------

class TestEvaluateLiveLLMPath:
    @pytest.mark.asyncio
    async def test_calls_openai_and_returns_structured_result(self):
        fake_response = json.dumps({
            "tool_selection": "PASS",
            "parameter_correctness": "PASS",
            "reasoning_faithfulness": "PASS",
            "workflow_order": "WARN",
            "task_completion": "PASS",
            "explanation": "Mostly good, minor order issue.",
            "confidence_score": 0.8,
        })
        trace = _make_trace(spans=[_tool_span()])
        with patch.object(repo_mod, "get_judge_result", AsyncMock(return_value=None)), \
             patch.object(repo_mod, "save_judge_result", AsyncMock()), \
             patch.object(config_mod, "get_llm_provider", return_value="openai"), \
             patch("evaluation.llm_judge.get_llm_provider", return_value="openai"):
            engine = LLMJudgeEngine()
            engine._call_openai = AsyncMock(return_value=fake_response)
            result = await engine.evaluate(trace)
        assert result.source == "llm"
        assert result.workflow_order == "WARN"
        assert result.confidence_score == 0.8

    @pytest.mark.asyncio
    async def test_exception_triggers_rule_based_fallback(self):
        trace = _make_trace(metrics={"overall_reliability_score": 0.75})
        with patch.object(repo_mod, "get_judge_result", AsyncMock(return_value=None)), \
             patch.object(repo_mod, "save_judge_result", AsyncMock()), \
             patch("evaluation.llm_judge.get_llm_provider", return_value="openai"):
            engine = LLMJudgeEngine()
            engine._call_openai = AsyncMock(side_effect=RuntimeError("connection error"))
            result = await engine.evaluate(trace)
        assert result.source == "rule_based"
