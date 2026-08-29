"""
AXIO Harness -- Orchestrator  (Plan Fase C · C1 / C6 / C9)

Top-level plan runner. Takes a Plan, orders it into dependency levels
(task_graph), and executes level by level. Within a level, independent steps run
concurrently; between levels a rendezvous barrier guarantees dependencies are
satisfied before dependents start. Each step is dispatched to its assigned agent
with a timeout (monitor) and a fallback chain (fallback engine); every event is
published to the event bus for visibility and appended to the orchestrator log.

The per-agent execution is injected as `run_agent(spec, task) -> response dict`,
so the orchestration logic is testable without a live model. `response` is
`{"status": "ok", "result": ...}` on success, or a CANNOT_HANDLE / AGENT_TIMEOUT
/ ERROR signal on failure.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from agents.base import AgentSpec
from agents.registry import get
from harness import fallback, monitor
from harness.event_bus import EventBus
from harness.plan import Plan, PlanStep, DONE, FAILED, SKIPPED, RUNNING
from harness.synthesizer import StepResult, synthesize
from harness.task_graph import levels

RunAgent = Callable[[AgentSpec, str], dict]


class Orchestrator:
    def __init__(self, run_agent: RunAgent, *, bus: EventBus | None = None,
                 timeout_s: float = monitor.DEFAULT_TIMEOUT_S,
                 parallel: bool = True, max_workers: int = 4) -> None:
        self.run_agent = run_agent
        self.bus = bus or EventBus()
        self.timeout_s = timeout_s
        self.parallel = parallel
        self.max_workers = max_workers

    # ── a single step, with timeout + fallback ───────────────────────────────
    def _dispatch(self, name: str, task: str) -> dict:
        spec = get(name)
        result, timed_out = monitor.run_with_timeout(
            lambda: self.run_agent(spec, task), self.timeout_s, name)
        if timed_out:
            monitor.log_event(None, name, "TIMEOUT")
        return result

    def _run_step(self, step: PlanStep, context: str) -> StepResult:
        step.status = RUNNING
        task = step.description if not context else f"{step.description}\n\nContext:\n{context}"
        self.bus.publish("ORCHESTRATOR", step.agent, "STEP_DISPATCH",
                         {"step": step.id, "phase": step.phase})

        fr = fallback.run_with_fallback(step.agent, task, self._dispatch)
        resp = fr.response

        if fr.escalated_to_user or resp.get("status") not in ("ok", None):
            status = "ESCALATE" if fr.escalated_to_user else FAILED
            step.status = FAILED
            monitor.log_event(step.id, step.agent,
                              "ESCALATE" if fr.escalated_to_user else "FAILED",
                              detail=f"trail={fr.trail}")
            return StepResult(step.id, fr.trail[-1] if fr.trail else step.agent,
                              status, resp.get("reason") or resp.get("result", ""))

        step.status = DONE
        outcome = "FALLBACK" if len(fr.trail) > 1 else "OK"
        monitor.log_event(step.id, fr.trail[-1], outcome, detail=f"trail={fr.trail}")
        return StepResult(step.id, fr.trail[-1], DONE, str(resp.get("result", "")))

    # ── whole plan, level by level ───────────────────────────────────────────
    def run(self, plan: Plan) -> tuple[str, list[StepResult]]:
        results: dict[int, StepResult] = {}
        failed_ids: set[int] = set()

        for level in levels(plan):
            runnable, skipped = [], []
            for step in level:
                blocked = [d for d in step.depends_on if d in failed_ids]
                (skipped if blocked else runnable).append(step)

            for step in skipped:
                step.status = SKIPPED
                failed_ids.add(step.id)          # cascade the skip to its dependents
                results[step.id] = StepResult(step.id, step.agent, SKIPPED,
                                              "skipped: upstream step failed")
                monitor.log_event(step.id, step.agent, "SKIPPED")

            def _ctx(step: PlanStep) -> str:
                return "\n".join(
                    f"[{d}] {results[d].output}" for d in step.depends_on
                    if d in results and results[d].output)

            if self.parallel and len(runnable) > 1:
                with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
                    futs = {ex.submit(self._run_step, s, _ctx(s)): s for s in runnable}
                    for fut in futs:
                        r = fut.result()
                        results[r.step_id] = r
                        if r.status in (FAILED, SKIPPED, "ESCALATE"):
                            failed_ids.add(r.step_id)
            else:
                for s in runnable:
                    r = self._run_step(s, _ctx(s))
                    results[r.step_id] = r
                    if r.status in (FAILED, SKIPPED, "ESCALATE"):
                        failed_ids.add(r.step_id)

        ordered = [results[s.id] for s in plan.steps if s.id in results]
        return synthesize(plan, ordered), ordered
