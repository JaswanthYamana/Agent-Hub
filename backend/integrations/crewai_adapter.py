"""
integrations/crewai_adapter.py – CrewAI task/agent lifecycle hooks for Flight Recorder.

Instruments CrewAI agents by patching the ``execute_task`` method on
``crewai.Agent`` so every task invocation is recorded as an AGENT span,
with nested TOOL spans for any tool calls made during execution.

Installation:
    pip install crewai

Usage:
    from sdk import Tracer
    from integrations.crewai_adapter import FlightRecorderCrewAIAdapter
    from crewai import Agent, Task, Crew

    tracer  = Tracer(project_id="my-project", export_url="http://localhost:8000")
    adapter = FlightRecorderCrewAIAdapter(tracer)

    # Patch BEFORE creating agents
    adapter.patch()

    booking_agent = Agent(
        role="Booking Specialist",
        goal="Book the cheapest available flight",
        tools=[...],
    )

    task = Task(description="Book SYD→DEL for 2025-06-01", agent=booking_agent)
    crew = Crew(agents=[booking_agent], tasks=[task])

    with tracer.start_trace(task="CrewAI flight booking", scenario="normal") as root:
        result = crew.kickoff()
    tracer.export(root)

    # Restore original methods when done
    adapter.unpatch()
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, Optional

try:
    import crewai
    _CREWAI_AVAILABLE = True
except ImportError:
    _CREWAI_AVAILABLE = False

try:
    from sdk import Tracer, _current_trace
except ImportError:
    from backend.sdk import Tracer, _current_trace  # type: ignore


class FlightRecorderCrewAIAdapter:
    """
    Monkey-patches ``crewai.Agent.execute_task`` to wrap each task execution
    in an AGENT span and each tool call in a TOOL span.

    Parameters
    ----------
    tracer:
        Configured ``Tracer`` instance.
    """

    def __init__(self, tracer: Tracer) -> None:
        if not _CREWAI_AVAILABLE:
            raise ImportError(
                "crewai is required. Install with: pip install crewai"
            )
        self._tracer = tracer
        self._original_execute_task: Optional[Callable] = None

    def patch(self) -> None:
        """Apply the instrumentation patches to crewai.Agent."""
        if self._original_execute_task is not None:
            return  # already patched

        tracer = self._tracer
        self._original_execute_task = crewai.Agent.execute_task  # type: ignore[attr-defined]
        original = self._original_execute_task

        @functools.wraps(original)
        def patched_execute_task(agent_self: Any, task: Any, *args: Any, **kwargs: Any) -> Any:
            ctx = _current_trace.get()
            task_desc = getattr(task, "description", str(task))[:200]
            role      = getattr(agent_self, "role", "agent")

            if ctx is None:
                # No active trace — call through without instrumentation
                return original(agent_self, task, *args, **kwargs)

            with tracer._make_ctx(f"crewai:{role}", "AGENT", ctx) as agent_span:
                agent_span._attrs["task"]        = task_desc
                agent_span._attrs["agent_role"]  = role
                agent_span._attrs["agent_goal"]  = getattr(agent_self, "goal", "")[:200]
                result = original(agent_self, task, *args, **kwargs)
                agent_span.set_output(str(result)[:500])
            return result

        crewai.Agent.execute_task = patched_execute_task  # type: ignore[attr-defined]

    def unpatch(self) -> None:
        """Restore original crewai.Agent.execute_task."""
        if self._original_execute_task is not None:
            crewai.Agent.execute_task = self._original_execute_task  # type: ignore[attr-defined]
            self._original_execute_task = None

    def __enter__(self) -> "FlightRecorderCrewAIAdapter":
        self.patch()
        return self

    def __exit__(self, *args: Any) -> None:
        self.unpatch()
