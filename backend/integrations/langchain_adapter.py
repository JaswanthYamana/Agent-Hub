"""
integrations/langchain_adapter.py – LangChain callback handler for Flight Recorder.

Implements LangChain's ``BaseCallbackHandler`` interface so that any chain,
agent, or LLM built with LangChain automatically emits spans to the platform
without modifying application code.

Installation:
    pip install langchain langchain-core

Usage:
    from sdk import Tracer
    from integrations.langchain_adapter import FlightRecorderCallbackHandler
    from langchain_openai import ChatOpenAI
    from langchain.agents import AgentExecutor

    tracer   = Tracer(project_id="my-project", export_url="http://localhost:8000")
    handler  = FlightRecorderCallbackHandler(tracer, task="Book a flight")

    llm = ChatOpenAI(callbacks=[handler])
    agent_executor = AgentExecutor(agent=..., tools=[...], callbacks=[handler])

    with handler.trace:        # opens root trace
        agent_executor.invoke({"input": "Book cheapest SYD→DEL flight"})
    tracer.export(handler.trace)

Each LangChain event maps to a span kind:
  - on_llm_start / end      → LLM span
  - on_tool_start / end      → TOOL span
  - on_chain_start / end     → CHAIN span
  - on_retriever_run         → RETRIEVER span
  - on_agent_action          → AGENT span attribute (recorded on root)
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Union

# LangChain is an optional dependency — we use TYPE_CHECKING to avoid hard dep
try:
    from langchain_core.callbacks.base import BaseCallbackHandler
    from langchain_core.outputs import LLMResult
    _LC_AVAILABLE = True
except ImportError:
    # Provide a stub so the module is importable even without langchain installed
    class BaseCallbackHandler:  # type: ignore[no-redef]
        """Stub — install langchain-core to use this adapter."""
    class LLMResult:  # type: ignore[no-redef]
        pass
    _LC_AVAILABLE = False

try:
    from sdk import Tracer, _SpanCtx, _TraceCtx, _current_trace
except ImportError:
    from backend.sdk import Tracer, _SpanCtx, _TraceCtx, _current_trace  # type: ignore


class FlightRecorderCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that records all chain/tool/LLM events as spans.

    Parameters
    ----------
    tracer:
        A configured ``Tracer`` instance.
    task:
        Human-readable task description for the root trace.
    scenario:
        Scenario tag (e.g. ``"normal"``, ``"tool_error"``).
    """

    def __init__(
        self,
        tracer:   Tracer,
        task:     str = "LangChain execution",
        scenario: str = "normal",
    ) -> None:
        if not _LC_AVAILABLE:
            raise ImportError(
                "langchain-core is required. Install with: pip install langchain-core"
            )
        super().__init__()
        self._tracer   = tracer
        self._task     = task
        self._scenario = scenario
        # Root trace context (open with `with handler.trace:` or call start/end manually)
        self.trace: _TraceCtx = tracer.start_trace(task=task, scenario=scenario)
        # Stack of open _SpanCtx objects keyed by run_id
        self._spans: Dict[str, _SpanCtx] = {}
        # Token usage accumulator
        self._token_counts: Dict[str, Any] = {}

    # ── LLM events ─────────────────────────────────────────────────────────

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        model_name = (serialized.get("kwargs", {}) or {}).get("model_name", "llm")
        span = self._tracer._make_ctx(
            model_name, "LLM", self.trace
        )
        span._attrs["prompt_count"] = len(prompts)
        span._attrs["model"]        = model_name
        span.__enter__()
        self._spans[str(run_id)] = span

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span is None:
            return
        # Capture token usage if available
        usage = getattr(response, "llm_output", {}) or {}
        if isinstance(usage, dict):
            tu = usage.get("token_usage", {}) or {}
            if tu:
                span.set_token_usage(
                    prompt=tu.get("prompt_tokens", 0),
                    completion=tu.get("completion_tokens", 0),
                )
        # Capture first generation text
        try:
            gen_text = response.generations[0][0].text[:500]
            span.set_output(gen_text)
        except (IndexError, AttributeError):
            pass
        span.__exit__(None, None, None)

    def on_llm_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_error(str(error), error_type=type(error).__name__)
            span.__exit__(type(error), error, None)

    # ── Tool events ─────────────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "tool")
        span = self._tracer._make_ctx(tool_name, "TOOL", self.trace)
        span._attrs["input"] = input_str[:1000]
        span.__enter__()
        self._spans[str(run_id)] = span

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_output(str(output)[:1000])
            span.__exit__(None, None, None)

    def on_tool_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_error(str(error), error_type=type(error).__name__)
            span.__exit__(type(error), error, None)

    # ── Chain events ────────────────────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        if serialized is None:
            serialized = {}
        chain_name = serialized.get("id", ["unknown_chain"])[-1]
        span = self._tracer._make_ctx(chain_name, "CHAIN", self.trace)
        span._attrs["inputs"] = str(inputs)[:500]
        span.__enter__()
        self._spans[str(run_id)] = span

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_output(str(outputs)[:500])
            span.__exit__(None, None, None)

    def on_chain_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_error(str(error), error_type=type(error).__name__)
            span.__exit__(type(error), error, None)

    # ── Retriever events ────────────────────────────────────────────────────

    def on_retriever_start(
        self,
        serialized: Dict[str, Any],
        query: str,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        span = self._tracer._make_ctx("retriever", "RETRIEVER", self.trace)
        span._attrs["query"] = query[:500]
        span.__enter__()
        self._spans[str(run_id)] = span

    def on_retriever_end(
        self,
        documents: Any,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            count = len(documents) if hasattr(documents, "__len__") else "unknown"
            span.set_output({"document_count": count})
            span.__exit__(None, None, None)
