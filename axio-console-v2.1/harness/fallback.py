"""
AXIO Harness -- Fallback Engine  (Plan Fase C · C3)

An agent that cannot complete a task returns a structured signal instead of a
result:

    {"status": "AGENT_CANNOT_HANDLE",
     "reason": "requires shell execution, not in my tools",
     "suggested_fallback": "RunAgent",
     "original_task": "create_dir('.instructions/...') failed"}

The engine detects that signal, picks the next agent (the signal's suggestion if
valid, else the spec's declared fallback), re-dispatches, and counts hops. Hard
limit: 2 fallbacks per step. After that the plan pauses and the user is asked —
no infinite loops. `fallback=None` on a spec means "escalate to the user".

`dispatch` is injected (agent_name, task) -> response dict, so the routing logic
is fully unit-testable without a live model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agents.registry import AGENT_REGISTRY

CANNOT_HANDLE = "AGENT_CANNOT_HANDLE"
MAX_HOPS = 2

Dispatch = Callable[[str, str], dict]   # (agent_name, task) -> response dict


def is_cannot_handle(response: dict) -> bool:
    return isinstance(response, dict) and response.get("status") == CANNOT_HANDLE


def cannot_handle(reason: str, suggested_fallback: str | None = None,
                  original_task: str = "") -> dict:
    """Build a well-formed CANNOT_HANDLE signal (used by agents/tests)."""
    return {
        "status": CANNOT_HANDLE,
        "reason": reason,
        "suggested_fallback": suggested_fallback,
        "original_task": original_task,
    }


def next_agent(response: dict, current: str) -> str | None:
    """Choose the next agent after a CANNOT_HANDLE, or None to escalate to user.

    Preference: the signal's suggested_fallback if it names a real agent;
    otherwise the current agent's declared spec.fallback.
    """
    suggested = response.get("suggested_fallback")
    if suggested and suggested in AGENT_REGISTRY and suggested != current:
        return suggested
    spec = AGENT_REGISTRY.get(current)
    return spec.fallback if spec else None


@dataclass
class FallbackResult:
    response: dict
    trail: list[str] = field(default_factory=list)   # agents tried, in order
    escalated_to_user: bool = False
    hops: int = 0


def run_with_fallback(agent: str, task: str, dispatch: Dispatch,
                      max_hops: int = MAX_HOPS) -> FallbackResult:
    """Dispatch `task` to `agent`, following the fallback chain on CANNOT_HANDLE.

    Returns a FallbackResult carrying the final response, the ordered trail of
    agents that were tried, and whether the plan escalated to the user (either
    because the chain hit a terminal agent with no fallback, or because it
    exceeded `max_hops`).
    """
    trail: list[str] = []
    current: str | None = agent
    hops = 0
    response: dict = {}

    while current is not None:
        response = dispatch(current, task)
        trail.append(current)

        if not is_cannot_handle(response):
            return FallbackResult(response=response, trail=trail, hops=hops)

        if hops >= max_hops:
            return FallbackResult(response=response, trail=trail,
                                  escalated_to_user=True, hops=hops)

        nxt = next_agent(response, current)
        if nxt is None:                      # terminal agent -> user
            return FallbackResult(response=response, trail=trail,
                                  escalated_to_user=True, hops=hops)
        current = nxt
        hops += 1

    return FallbackResult(response=response, trail=trail,
                          escalated_to_user=True, hops=hops)
