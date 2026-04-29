"""
sdk.py – Python Tracing SDK for the AI Agent Flight Recorder.

Allows external Python agents to emit structured spans to the platform
without depending on any OpenTelemetry SDK. The SDK can operate in two modes:

  LOCAL mode  (default):
    Spans are collected in memory and returned when the root context exits.
    Useful for testing and for agents that talk directly to the Flight Recorder
    ingest API.

  EXPORT mode (when FLIGHT_RECORDER_URL is set):
    Spans are HTTP-POSTed to <FLIGHT_RECORDER_URL>/api/ingest when the root
    context exits.

Usage example (sync)
────────────────────
    from sdk import Tracer

    tracer = Tracer(project_id="my-project", service_name="booking-agent")

    with tracer.start_trace(task="Book flight SYD→DEL", scenario="normal") as root:
        with tracer.tool_span("flight_search_api") as span:
            span.set_input({"origin": "SYD", "destination": "DEL", "date": "2025-01-01"})
            result = flight_search(origin="SYD", destination="DEL")
            span.set_output(result)

    completed_trace = root.trace   # dict with all spans attached

Usage example (decorator)
─────────────────────────
    tracer = Tracer(project_id="my-project")

    @tracer.trace_tool(name="flight_search_api")
    def search_flights(origin: str, destination: str, date: str):
        return {"flights": [...]}

    with tracer.start_trace(task="Book flight") as root:
        results = search_flights("SYD", "DEL", "2025-01-01")
    tracer.export(root)

Usage example (async)
─────────────────────
    async with tracer.async_tool_span("booking_api") as span:
        span.set_input(params)
        result = await booking_api(params)
        span.set_output(result)
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import json
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# ── Runtime dependency check (httpx is optional) ────────────────────────────
try:
    import httpx as _httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


# ── Context variable: tracks the currently active trace ─────────────────────
# This allows @trace_tool decorators to automatically parent to the active trace
# without requiring explicit context passing.
_current_trace: contextvars.ContextVar[Optional["_TraceCtx"]] = contextvars.ContextVar(
    "_current_trace", default=None
)


# ── Minimal inline Span/Trace to avoid circular imports ─────────────────────
# When sdk.py is used standalone (outside the backend package) we can't import
# from `core.models`.  We use plain dicts here and let the server normalise them.

class _SpanCtx:
    """Context manager returned by Tracer.tool_span / .agent_span etc.

    Supports both synchronous (`with`) and asynchronous (`async with`) usage.
    """

    def __init__(
        self,
        trace_id:      str,
        name:          str,
        kind:          str,
        parent_id:     Optional[str],
        project_id:    str,
        service_name:  str,
        collector:     List[Dict[str, Any]],
        agent_id:      Optional[str] = None,
        environment:   str = "development",
        agent_version: Optional[str] = None,
    ) -> None:
        self.span_id       = str(uuid.uuid4())[:16]
        self.trace_id      = trace_id
        self.name          = name
        self.kind          = kind
        self.parent_id     = parent_id
        self.project_id    = project_id
        self.service_name  = service_name
        self.agent_id      = agent_id
        self.environment   = environment
        self.agent_version = agent_version
        self.collector     = collector
        self.start_time    = time.time()
        self._attrs:   Dict[str, Any] = {}
        self._error:   Optional[str]  = None
        self._error_type: Optional[str] = None
        self._error_category: Optional[str] = None
        self._model_name: Optional[str] = None
        self._status:  str             = "PENDING"

    # ── Fluent setters ─────────────────────────────────────────────────
    def set_input(self, params: Dict[str, Any]) -> "_SpanCtx":
        self._attrs["input_params"] = params
        return self

    def set_output(self, result: Any) -> "_SpanCtx":
        self._attrs["output"] = result
        return self

    def set_attribute(self, key: str, value: Any) -> "_SpanCtx":
        self._attrs[key] = value
        return self

    def set_error(
        self,
        message: str,
        error_type: Optional[str] = None,
        error_category: Optional[str] = None,
    ) -> "_SpanCtx":
        self._error          = message
        self._error_type     = error_type
        self._error_category = error_category
        self._status         = "ERROR"
        return self

    def set_model(self, model_name: str) -> "_SpanCtx":
        """Record the LLM model name for LLM-kind spans."""
        self._model_name = model_name
        return self

    def set_token_usage(self, prompt: int = 0, completion: int = 0) -> "_SpanCtx":
        self._attrs["token_usage"] = {"prompt_tokens": prompt, "completion_tokens": completion}
        return self

    # ── Sync context protocol ──────────────────────────────────────────
    def __enter__(self) -> "_SpanCtx":
        return self

    def _finalise(self, exc_type: Any, exc_val: Any) -> None:
        end_time = time.time()
        if exc_type is not None:
            self._status     = "ERROR"
            self._error      = str(exc_val)
        elif self._status == "PENDING":
            self._status = "OK"

        token_usage = self._attrs.pop("token_usage", {})
        span_dict: Dict[str, Any] = {
            "span_id":            self.span_id,
            "trace_id":           self.trace_id,
            "parent_span_id":     self.parent_id,
            "kind":               self.kind,
            "name":               self.name,
            "start_time":         self.start_time,
            "end_time":           end_time,
            "duration_ms":        round((end_time - self.start_time) * 1000, 2),
            "status":             self._status,
            "attributes":         {**self._attrs, "tool": self.name},
            "error_message":      self._error,
            "error_type":         self._error_type,
            "error_category":     self._error_category,
            "contains_injection": False,
            "injection_payload":  None,
            "service_name":       self.service_name,
            "environment":        self.environment,
            "agent_version":      self.agent_version,
            "project_id":         self.project_id,
            "agent_id":           self.agent_id,
            "token_usage":        token_usage,
            "model_name":         self._model_name,
        }
        self.collector.append(span_dict)

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._finalise(exc_type, exc_val)
        return False   # do not suppress exceptions

    # ── Async context protocol ─────────────────────────────────────────
    async def __aenter__(self) -> "_SpanCtx":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._finalise(exc_type, exc_val)
        return False


class _TraceCtx:
    """Root context returned by Tracer.start_trace."""

    def __init__(
        self,
        task:         str,
        scenario:     str,
        project_id:   str,
        service_name: str,
    ) -> None:
        self.trace_id     = str(uuid.uuid4())
        self.task         = task
        self.scenario     = scenario
        self.project_id   = project_id
        self.service_name = service_name
        self.start_time   = time.time()
        self._spans: List[Dict[str, Any]] = []
        self.trace: Optional[Dict[str, Any]] = None

    def __enter__(self) -> "_TraceCtx":
        self._ctx_token = _current_trace.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        _current_trace.reset(self._ctx_token)
        end_time = time.time()
        self.trace = {
            "trace_id":   self.trace_id,
            "task":       self.task,
            "scenario":   self.scenario,
            "project_id": self.project_id,
            "start_time": self.start_time,
            "end_time":   end_time,
            "success":    exc_type is None,
            "completed":  True,
            "spans":      self._spans,
        }
        return False


class Tracer:
    """
    Entry point for the Flight Recorder SDK.

    Parameters
    ----------
    project_id:
        Which project to associate spans with (default: "default").
    service_name:
        Name of the agent or service emitting spans (default: "external-agent").
    environment:
        Deployment environment label: ``development`` | ``staging`` | ``production``.
    agent_version:
        Semver string identifying the releasing agent (e.g. ``"1.2.3"``).
    export_url:
        Override the export endpoint.  Falls back to FLIGHT_RECORDER_URL env var.
    api_key:
        Optional API key sent as ``X-API-Key`` header.  Falls back to the
        ``FLIGHT_RECORDER_API_KEY`` environment variable.
    """

    def __init__(
        self,
        project_id:    str = "default",
        service_name:  str = "external-agent",
        environment:   str = "development",
        agent_version: Optional[str] = None,
        export_url:    Optional[str] = None,
        agent_id:      Optional[str] = None,
        api_key:       Optional[str] = None,
    ) -> None:
        self.project_id    = project_id
        self.service_name  = service_name
        self.environment   = environment
        self.agent_version = agent_version or os.environ.get("FLIGHT_RECORDER_AGENT_VERSION")
        self._export_url   = export_url or os.environ.get("FLIGHT_RECORDER_URL")
        self._agent_id     = agent_id
        self._api_key      = api_key or os.environ.get("FLIGHT_RECORDER_API_KEY", "")

    def start_trace(self, task: str, scenario: str = "normal") -> _TraceCtx:
        """Open a root trace context. Use as a `with` block."""
        return _TraceCtx(
            task=task, scenario=scenario,
            project_id=self.project_id, service_name=self.service_name,
        )

    def tool_span(
        self, name: str, parent: Optional[_TraceCtx | _SpanCtx] = None
    ) -> _SpanCtx:
        """Open a TOOL span. Must be called inside a start_trace context."""
        return self._make_ctx(name, "TOOL", parent)

    def llm_span(
        self, name: str = "llm_call", parent: Optional[_TraceCtx | _SpanCtx] = None
    ) -> _SpanCtx:
        return self._make_ctx(name, "LLM", parent)

    def retriever_span(
        self, name: str, parent: Optional[_TraceCtx | _SpanCtx] = None
    ) -> _SpanCtx:
        return self._make_ctx(name, "RETRIEVER", parent)

    def agent_span(
        self, name: str = "agent", parent: Optional[_TraceCtx | _SpanCtx] = None
    ) -> _SpanCtx:
        return self._make_ctx(name, "AGENT", parent)

    def _make_ctx(
        self,
        name: str,
        kind: str,
        parent: Optional[Any] = None,
        agent_id: Optional[str] = None,
    ) -> _SpanCtx:
        # Resolve parent: explicit argument > context-var active trace
        if parent is None:
            parent = _current_trace.get()
        if parent is None:
            raise RuntimeError(
                "Span must be created inside a start_trace context, or use "
                "`with tracer.start_trace(...)` before creating spans."
            )
        if isinstance(parent, _TraceCtx):
            trace_id  = parent.trace_id
            parent_id = None
            collector = parent._spans
        else:
            trace_id  = parent.trace_id
            parent_id = parent.span_id
            collector = parent.collector
        return _SpanCtx(
            trace_id=trace_id, name=name, kind=kind, parent_id=parent_id,
            project_id=self.project_id, service_name=self.service_name,
            collector=collector, agent_id=agent_id or self._agent_id,
            environment=self.environment, agent_version=self.agent_version,
        )

    def _build_payload(self, trace_ctx: _TraceCtx) -> Dict[str, Any]:
        return {
            "trace_id":     trace_ctx.trace_id,
            "spans":        trace_ctx._spans,
            "project_id":   self.project_id,
            "service_name": self.service_name,
        }

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    def export(self, trace_ctx: _TraceCtx, retries: int = 3) -> bool:
        """POST completed trace to the Flight Recorder ingest endpoint.

        Retries up to *retries* times on transient failures with exponential
        back-off (0.5 s → 1 s → 2 s).
        Returns True on success, False if all attempts are exhausted.
        """
        if not _HTTPX_OK:
            print("[SDK] httpx not installed; skipping export.")
            return False
        url = self._export_url
        if not url:
            return False
        url = url.rstrip("/") + "/api/ingest"
        payload = self._build_payload(trace_ctx)
        for attempt in range(retries):
            try:
                with _httpx.Client(timeout=10) as client:
                    resp = client.post(url, json=payload, headers=self._headers())
                    if resp.status_code == 200:
                        return True
                    print(f"[SDK] Export HTTP {resp.status_code} (attempt {attempt+1}): {resp.text}")
            except Exception as exc:
                print(f"[SDK] Export failed (attempt {attempt+1}): {exc}")
            if attempt < retries - 1:
                import time as _time
                _time.sleep(0.5 * (2 ** attempt))
        return False

    async def async_export(self, trace_ctx: _TraceCtx, retries: int = 3) -> bool:
        """Async version of export — uses httpx.AsyncClient with retry."""
        if not _HTTPX_OK:
            return False
        url = self._export_url
        if not url:
            return False
        url = url.rstrip("/") + "/api/ingest"
        payload = self._build_payload(trace_ctx)
        for attempt in range(retries):
            try:
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(url, json=payload, headers=self._headers())
                    if resp.status_code == 200:
                        return True
                    print(f"[SDK] Async export HTTP {resp.status_code} (attempt {attempt+1})")
            except Exception as exc:
                print(f"[SDK] Async export failed (attempt {attempt+1}): {exc}")
            if attempt < retries - 1:
                await asyncio.sleep(0.5 * (2 ** attempt))
        return False

    def trace_tool(
        self,
        name: Optional[str] = None,
        kind: str = "TOOL",
        capture_args: bool = True,
    ) -> Callable[[F], F]:
        """
        Decorator factory that wraps a sync or async function in a span.

        Uses ``contextvars`` to automatically attach to the active trace —
        no explicit parent argument required.

        Usage::

            @tracer.trace_tool(name="flight_search_api")
            def search_flights(origin: str, destination: str) -> dict:
                ...

            @tracer.trace_tool(name="async_booking_api")
            async def book_flight(flight_id: str) -> dict:
                ...
        """
        def decorator(fn: F) -> F:
            span_name = name or fn.__name__

            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args, **kwargs):
                    ctx = _current_trace.get()
                    if ctx is None:
                        return await fn(*args, **kwargs)
                    async with self._make_ctx(span_name, kind, ctx) as span:
                        if capture_args:
                            span.set_input(kwargs)
                        result = await fn(*args, **kwargs)
                        span.set_output(result if isinstance(result, (dict, list, str, int, float, bool)) else str(result))
                        return result
                return async_wrapper  # type: ignore[return-value]
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args, **kwargs):
                    ctx = _current_trace.get()
                    if ctx is None:
                        return fn(*args, **kwargs)
                    with self._make_ctx(span_name, kind, ctx) as span:
                        if capture_args:
                            span.set_input(kwargs)
                        result = fn(*args, **kwargs)
                        span.set_output(result if isinstance(result, (dict, list, str, int, float, bool)) else str(result))
                        return result
                return sync_wrapper  # type: ignore[return-value]
        return decorator  # type: ignore[return-value]

    # Convenience aliases
    def trace_llm(self, name: Optional[str] = None) -> Callable[[F], F]:
        return self.trace_tool(name=name, kind="LLM")

    def trace_retriever(self, name: Optional[str] = None) -> Callable[[F], F]:
        return self.trace_tool(name=name, kind="RETRIEVER")

    # Convenience span method matching the user-requested API:
    # `with tracer.span("tool_call", tool="search_flights")`
    def span(
        self,
        name: str,
        tool: Optional[str] = None,
        kind: str = "TOOL",
        parent: Optional[Any] = None,
    ) -> _SpanCtx:
        """Convenience alias for creating any span type inline."""
        ctx = self._make_ctx(tool or name, kind, parent)
        if tool:
            ctx._attrs["tool"] = tool
        return ctx


# ── Automatic instrumentation helpers ────────────────────────────────────────

def wrap_openai(tracer_instance: "Tracer") -> None:
    """
    Monkey-patch the OpenAI client so every ``chat.completions.create`` call
    automatically emits an LLM span via *tracer_instance*.

    Must be called *after* ``import openai``.  Safe to call multiple times
    (idempotent guard via ``_FR_PATCHED`` marker).

    Usage::

        import openai
        from sdk import Tracer, wrap_openai

        tracer = Tracer(project_id="my-agent", export_url="http://localhost:8000")
        wrap_openai(tracer)

        with tracer.start_trace(task="Summarise document") as root:
            response = openai.OpenAI().chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello"}],
            )
    """
    try:
        import openai as _openai  # type: ignore[import]
    except ImportError:
        return  # openai not installed — silently skip

    from openai.resources.chat import completions as _completions  # type: ignore[import]

    if getattr(_completions.Completions.create, "_FR_PATCHED", False):
        return  # already patched

    _original_create = _completions.Completions.create

    @functools.wraps(_original_create)
    def _patched_create(self_client, *args, **kwargs):
        active = _current_trace.get()
        if active is None:
            return _original_create(self_client, *args, **kwargs)

        model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        ctx = tracer_instance._make_ctx(f"llm:{model}", "LLM", active)
        ctx._model_name = model
        ctx._attrs["llm_input"] = messages
        ctx.__enter__()
        try:
            result = _original_create(self_client, *args, **kwargs)
            choice  = result.choices[0] if result.choices else None
            content = choice.message.content if choice else ""
            ctx._attrs["llm_output"] = content
            if result.usage:
                ctx.set_token_usage(
                    prompt=result.usage.prompt_tokens,
                    completion=result.usage.completion_tokens,
                )
            ctx.__exit__(None, None, None)
            return result
        except Exception as exc:
            ctx.set_error(str(exc), type(exc).__name__)
            ctx.__exit__(type(exc), exc, None)
            raise

    _patched_create._FR_PATCHED = True  # type: ignore[attr-defined]
    _completions.Completions.create = _patched_create  # type: ignore[method-assign]


def wrap_langchain_tools(tracer_instance: "Tracer", tools: list) -> list:
    """
    Wrap a list of LangChain ``BaseTool`` instances so that every ``.run()``
    and ``._run()`` call emits a TOOL span.

    Returns the same list (wrapping is in-place via subclassing).

    Usage::

        from langchain.tools import DuckDuckGoSearchRun
        from sdk import Tracer, wrap_langchain_tools

        tracer = Tracer(project_id="rag-agent")
        tools = wrap_langchain_tools(tracer, [DuckDuckGoSearchRun()])
    """
    wrapped = []
    for tool in tools:
        # Wrap the tool's _run method
        original_run = tool._run

        @functools.wraps(original_run)
        def _wrapped_run(*args, _tool=tool, _orig=original_run, **kwargs):
            active = _current_trace.get()
            if active is None:
                return _orig(*args, **kwargs)
            tool_name = getattr(_tool, "name", _tool.__class__.__name__)
            with tracer_instance._make_ctx(tool_name, "TOOL", active) as span:
                span.set_input({"args": list(args), **kwargs})
                result = _orig(*args, **kwargs)
                span.set_output(str(result)[:2000])
                return result

        tool._run = _wrapped_run  # type: ignore[method-assign]
        wrapped.append(tool)
    return wrapped


def wrap_retriever(tracer_instance: "Tracer", retriever: Any) -> Any:
    """
    Wrap a LangChain ``BaseRetriever`` so that every ``get_relevant_documents``
    / ``invoke`` call emits a RETRIEVER span with the query and retrieved docs.

    Usage::

        from langchain_community.vectorstores import FAISS
        from sdk import Tracer, wrap_retriever

        tracer     = Tracer(project_id="rag-agent")
        vectorstore = FAISS.from_documents(docs, embeddings)
        retriever   = wrap_retriever(tracer, vectorstore.as_retriever())
    """
    for method_name in ("get_relevant_documents", "invoke"):
        orig = getattr(retriever, method_name, None)
        if orig is None:
            continue

        @functools.wraps(orig)
        def _wrapped(query, *args, _orig=orig, **kwargs):
            active = _current_trace.get()
            if active is None:
                return _orig(query, *args, **kwargs)
            with tracer_instance._make_ctx("retriever", "RETRIEVER", active) as span:
                span.set_input({"query": query})
                docs = _orig(query, *args, **kwargs)
                retrieved = [
                    getattr(d, "page_content", str(d))[:500]
                    for d in (docs if isinstance(docs, list) else [docs])
                ]
                span.set_output({"retrieved_docs": retrieved})
                span._attrs["retrieved_doc_count"] = len(retrieved)
                return docs

        setattr(retriever, method_name, _wrapped)
    return retriever


# ── Module-level convenience instance ────────────────────────────────────────
# Pre-configured tracer that reads project/URL from environment variables.
# Import as: `from sdk import tracer`
tracer = Tracer(
    project_id=os.environ.get("FLIGHT_RECORDER_PROJECT", "default"),
    service_name=os.environ.get("FLIGHT_RECORDER_SERVICE", "external-agent"),
    environment=os.environ.get("FLIGHT_RECORDER_ENV", "development"),
    agent_version=os.environ.get("FLIGHT_RECORDER_AGENT_VERSION"),
)
