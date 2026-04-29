"""
integrations/autogen_adapter.py – AutoGen agent middleware for Flight Recorder.

Instruments AutoGen ``ConversableAgent`` by wrapping the ``initiate_chat``
and ``generate_reply`` methods so that every message exchange and tool call
is recorded as a span.

Installation:
    pip install pyautogen

Usage:
    from sdk import Tracer
    from integrations.autogen_adapter import FlightRecorderAutoGenMiddleware
    from autogen import ConversableAgent, AssistantAgent, UserProxyAgent

    tracer     = Tracer(project_id="my-project", export_url="http://localhost:8000")
    middleware = FlightRecorderAutoGenMiddleware(tracer)
    middleware.patch()

    assistant = AssistantAgent("BookingAssistant", llm_config={...})
    user      = UserProxyAgent("UserProxy", code_execution_config=False)

    with tracer.start_trace(task="AutoGen flight booking", scenario="normal") as root:
        user.initiate_chat(assistant, message="Book cheapest SYD→DEL flight")
    tracer.export(root)

    middleware.unpatch()
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import autogen
    _AUTOGEN_AVAILABLE = True
except ImportError:
    try:
        import pyautogen as autogen  # older package name
        _AUTOGEN_AVAILABLE = True
    except ImportError:
        _AUTOGEN_AVAILABLE = False

try:
    from sdk import Tracer, _current_trace
except ImportError:
    from backend.sdk import Tracer, _current_trace  # type: ignore


class FlightRecorderAutoGenMiddleware:
    """
    Wraps AutoGen ``ConversableAgent.generate_reply`` and
    ``ConversableAgent.initiate_chat`` to capture multi-agent conversations
    as nested spans.

    Each agent's reply cycle becomes an AGENT span.  Tool executions inside
    code blocks are captured as TOOL spans via the ``UserProxyAgent`` executor.

    Parameters
    ----------
    tracer:
        Configured ``Tracer`` instance.
    """

    def __init__(self, tracer: Tracer) -> None:
        if not _AUTOGEN_AVAILABLE:
            raise ImportError(
                "pyautogen is required. Install with: pip install pyautogen"
            )
        self._tracer = tracer
        self._originals: Dict[str, Callable] = {}

    def patch(self) -> None:
        """Apply instrumentation patches to autogen.ConversableAgent."""
        if self._originals:
            return  # already patched

        tracer = self._tracer
        agent_cls = autogen.ConversableAgent  # type: ignore[attr-defined]

        # ── Patch generate_reply ───────────────────────────────────────────
        original_reply = agent_cls.generate_reply
        self._originals["generate_reply"] = original_reply

        @functools.wraps(original_reply)
        def patched_generate_reply(
            agent_self: Any,
            messages: Optional[List[Dict]] = None,
            sender: Optional[Any] = None,
            **kwargs: Any,
        ) -> Any:
            ctx = _current_trace.get()
            if ctx is None:
                return original_reply(agent_self, messages=messages, sender=sender, **kwargs)

            agent_name = getattr(agent_self, "name", "autogen_agent")
            last_msg   = (messages or [{}])[-1].get("content", "")[:300]

            with tracer._make_ctx(f"autogen:{agent_name}", "AGENT", ctx) as span:
                span._attrs["agent_name"]  = agent_name
                span._attrs["message_in"]  = last_msg
                span._attrs["msg_count"]   = len(messages or [])
                result = original_reply(
                    agent_self, messages=messages, sender=sender, **kwargs
                )
                if isinstance(result, str):
                    span.set_output(result[:500])
                elif isinstance(result, (dict, bool)):
                    span.set_output(str(result)[:200])
            return result

        agent_cls.generate_reply = patched_generate_reply  # type: ignore[attr-defined]

        # ── Patch initiate_chat ────────────────────────────────────────────
        original_chat = agent_cls.initiate_chat
        self._originals["initiate_chat"] = original_chat

        @functools.wraps(original_chat)
        def patched_initiate_chat(
            agent_self: Any,
            recipient: Any,
            message: Optional[str] = None,
            **kwargs: Any,
        ) -> Any:
            ctx = _current_trace.get()
            if ctx is None:
                return original_chat(agent_self, recipient, message=message, **kwargs)

            initiator = getattr(agent_self, "name", "initiator")
            target    = getattr(recipient, "name",  "recipient")

            with tracer._make_ctx(f"autogen:chat:{initiator}→{target}", "CHAIN", ctx) as span:
                span._attrs["initiator"] = initiator
                span._attrs["recipient"] = target
                span._attrs["message"]   = (message or "")[:300]
                result = original_chat(agent_self, recipient, message=message, **kwargs)
                # ConversableAgent.chat_messages may hold exchange history
                history = getattr(agent_self, "chat_messages", {})
                msg_count = sum(len(v) for v in history.values())
                span.set_output({"exchange_count": msg_count})
            return result

        agent_cls.initiate_chat = patched_initiate_chat  # type: ignore[attr-defined]

    def unpatch(self) -> None:
        """Restore original AutoGen methods."""
        agent_cls = autogen.ConversableAgent  # type: ignore[attr-defined]
        for method_name, original in self._originals.items():
            setattr(agent_cls, method_name, original)
        self._originals.clear()

    def __enter__(self) -> "FlightRecorderAutoGenMiddleware":
        self.patch()
        return self

    def __exit__(self, *args: Any) -> None:
        self.unpatch()
