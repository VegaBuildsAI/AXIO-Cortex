"""
AXIO Harness -- Planner + orchestrated run

Bridges PlanAgent to the Orchestrator. ``build_plan`` asks a model to decompose a
task into a structured, dependency-annotated :class:`Plan` (validated against the
real agent roster and phase set, with a safe heuristic fallback when the model's
JSON is unusable). ``run_orchestrated`` then executes that plan across the agent
fleet — level-by-level, with peer-to-peer delegation, timeouts, and fallback —
and returns the synthesized answer.
"""

from __future__ import annotations

import json
import re

from agents.registry import AGENT_REGISTRY
from harness.agent_runtime import make_run_agent
from harness.event_bus import EventBus
from harness.orchestrator import Orchestrator
from harness.plan import PHASES, Plan, PlanStep

_AGENT_NAMES = set(AGENT_REGISTRY)


def _roster() -> str:
    return "\n".join(f"  - {name}: {spec.description}" for name, spec in AGENT_REGISTRY.items())


def planning_prompt() -> str:
    return (
        "You are PlanAgent, the meta-planner of a multi-agent coding harness.\n"
        "Decompose the user's task into the FEWEST ordered steps that actually "
        "accomplish it. Return ONLY a JSON object, no prose, of the form:\n"
        '{"task": "<restated task>", "steps": ['
        '{"id": 1, "phase": "<PHASE>", "description": "<what to do>", '
        '"agent": "<AgentName>", "depends_on": []}]}\n\n'
        f"Valid phases: {', '.join(PHASES)}.\n"
        f"Agents (assign the single best one per step):\n{_roster()}\n\n"
        "Rules: ids are unique integers starting at 1; depends_on lists only "
        "earlier ids; add a TEST step (TestAgent) after any step that changes "
        "code; only WebAgent may use the internet. Output JSON only."
    )


def _heuristic_agent(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("http", "web", "online", "search the", "google", "url")):
        return "WebAgent"
    if any(k in t for k in ("test", "pytest", "coverage")):
        return "TestAgent"
    if any(k in t for k in ("commit", "git ", "branch", "push", " pr ")):
        return "GitAgent"
    if any(k in t for k in ("find", "grep", "locate", "search for", "where is")):
        return "SearchAgent"
    if any(k in t for k in ("run ", "execute", "command", "python ", "npm ")):
        return "RunAgent"
    return "FSAgent"


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start:end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def plan_from_model_output(task: str, raw: str) -> Plan:
    """Parse model JSON into a validated Plan, coercing bad fields and remapping
    ids so dependencies stay consistent. Falls back to a heuristic single step."""
    data = _extract_json(raw) or {}
    raw_steps = data.get("steps") if isinstance(data.get("steps"), list) else []

    coerced: list[dict] = []
    id_map: dict[int, int] = {}
    for original in raw_steps:
        if not isinstance(original, dict):
            continue
        new_id = len(coerced) + 1
        old_id = original.get("id")
        if isinstance(old_id, int):
            id_map[old_id] = new_id
        phase = str(original.get("phase", "IMPLEMENT")).upper()
        if phase not in PHASES:
            phase = "IMPLEMENT"
        description = str(original.get("description", "")).strip() or "(unspecified step)"
        agent = original.get("agent")
        if agent not in _AGENT_NAMES:
            agent = _heuristic_agent(description)
        deps_raw = original.get("depends_on") or []
        deps = []
        if isinstance(deps_raw, list):
            for d in deps_raw:
                mapped = id_map.get(d)
                if mapped is not None and mapped < new_id:  # backward refs only
                    deps.append(mapped)
        coerced.append({"id": new_id, "phase": phase, "description": description,
                        "agent": agent, "depends_on": tuple(dict.fromkeys(deps))})

    if not coerced:
        coerced = [{"id": 1, "phase": "IMPLEMENT", "description": task,
                    "agent": _heuristic_agent(task), "depends_on": ()}]

    steps = [PlanStep(**s) for s in coerced]
    return Plan(task=data.get("task") or task, steps=steps)


def build_plan(task: str, *, provider: str, model=None, ollama=None, claude=None) -> Plan:
    system = planning_prompt()
    user = f"Task: {task}\n\nReturn the plan JSON now."
    try:
        if provider == "claude" and claude is not None:
            raw = claude.chat([{"role": "user", "content": user}], system=system, print_output=False)
        else:
            raw = ollama.chat_stream(
                model,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                print_output=False,
            )
    except Exception:
        raw = ""
    return plan_from_model_output(task, raw)


def run_orchestrated(task: str, *, provider: str, model=None, ollama=None, claude=None,
                     approve=None, audit=None, memory_prefix: str = "",
                     verbose: bool = True, parallel: bool = True, printer=print) -> str:
    """Plan the task, run it across the agent fleet, and return the synthesis."""
    plan = build_plan(task, provider=provider, model=model, ollama=ollama, claude=claude)
    printer("\n  PLAN (multi-agent):")
    for line in plan.phase_summary():
        printer(f"    {line}")
    printer("")

    bus = EventBus()
    runner = make_run_agent(
        provider=provider, model=model, ollama=ollama, claude=claude,
        approve=approve, audit=audit, memory_prefix=memory_prefix, verbose=verbose, bus=bus,
    )
    orchestrator = Orchestrator(runner, bus=bus, parallel=parallel)
    summary, _results = orchestrator.run(plan)
    return summary
