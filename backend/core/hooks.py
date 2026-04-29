"""
core/hooks.py – Lightweight async hook registry for platform extension points.

The three teammates' features each plug into the platform via named events:

    "post_ingest"   — fired after external spans are stored (SDK / OTLP ingest).
                      Friend 1 uses this to run real-agent instrumentation hooks.
                      Kwargs: spans (List[Span]), trace_id (str), project_id (str)

    "post_analysis" — fired after anomaly detection + metrics compute for every
                      completed trace (internal demo OR evaluated external trace).
                      Friend 2 uses this for time-series reliability tracking.
                      Kwargs: trace (Trace)

    "pre_attack"    — fired before a red-team attack is executed.
                      Friend 3 uses this for dynamic adversarial evolution.
                      Kwargs: request (RedTeamRequest)

Usage
-----
Register (in any module, executed at import time or during startup):

    from core.hooks import hooks

    @hooks.on("post_analysis")
    async def track_trend(trace) -> None:
        # persist ORS to your time-series store
        ...

Fire (already wired into main.py — nothing extra needed):

    await hooks.fire("post_analysis", trace=trace)

Multiple handlers per event are each called independently; one handler raising
an exception does not prevent subsequent handlers from running.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Dict, List

logger = logging.getLogger(__name__)

HandlerType = Callable[..., Coroutine[Any, Any, None]]


class HookRegistry:
    """Async hook registry with named events and multiple handlers per event."""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[HandlerType]] = defaultdict(list)

    def on(self, event: str) -> Callable[[HandlerType], HandlerType]:
        """Decorator to register an async handler for a named event."""
        def decorator(fn: HandlerType) -> HandlerType:
            self._handlers[event].append(fn)
            logger.debug(
                "Registered hook '%s' for event '%s'",
                getattr(fn, "__name__", repr(fn)), event,
            )
            return fn
        return decorator

    def register(self, event: str, handler: HandlerType) -> None:
        """Imperatively register a handler (alternative to @on decorator)."""
        self._handlers[event].append(handler)
        logger.debug(
            "Registered hook '%s' for event '%s'",
            getattr(handler, "__name__", repr(handler)), event,
        )

    async def fire(self, event: str, **kwargs: Any) -> None:
        """
        Call all handlers registered for ``event``, passing kwargs.

        Each handler is awaited individually.  Exceptions are caught, logged,
        and swallowed so that a broken handler never breaks the hot path.
        """
        for handler in self._handlers.get(event, []):
            try:
                await handler(**kwargs)
            except Exception:
                logger.exception(
                    "Hook handler '%s' raised an error on event '%s'",
                    getattr(handler, "__name__", repr(handler)), event,
                )

    def registered_events(self) -> List[str]:
        """Return the list of events that have at least one handler."""
        return [k for k, v in self._handlers.items() if v]


# ── Global singleton ───────────────────────────────────────────────────────
# Import this in any module that needs hooks:
#   from core.hooks import hooks
hooks = HookRegistry()
