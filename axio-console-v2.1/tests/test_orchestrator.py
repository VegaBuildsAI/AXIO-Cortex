"""Fase C · C1/C6/C9 / Fase E4·E6·E7 — orchestrator routing, parallel, skip, timeout."""
import time

from agents.base import AgentSpec
from harness.orchestrator import Orchestrator
from harness.plan import Plan, PlanStep, DONE, FAILED, SKIPPED
from harness.event_bus import EventBus


def _plan(steps):
    return Plan("t", steps)


def test_routes_each_step_to_its_agent():
    seen = []
    def run_agent(spec: AgentSpec, task: str):
        seen.append(spec.name)
        return {"status": "ok", "result": f"{spec.name} did it"}
    plan = _plan([
        PlanStep(1, "DISCOVER", "scan", "CtxAgent"),
        PlanStep(2, "IMPLEMENT", "write", "FSAgent", depends_on=(1,)),
        PlanStep(3, "TEST", "test", "TestAgent", depends_on=(2,)),
    ])
    orch = Orchestrator(run_agent, parallel=False)
    _, results = orch.run(plan)
    assert seen == ["CtxAgent", "FSAgent", "TestAgent"]
    assert all(r.status == DONE for r in results)


def test_failed_step_skips_dependents():
    def run_agent(spec, task):
        if spec.name == "FSAgent":
            return {"status": "ERROR", "reason": "disk full"}
        return {"status": "ok", "result": "ok"}
    plan = _plan([
        PlanStep(1, "IMPLEMENT", "write", "FSAgent"),
        PlanStep(2, "TEST", "test", "TestAgent", depends_on=(1,)),
    ])
    _, results = Orchestrator(run_agent, parallel=False).run(plan)
    by = {r.step_id: r for r in results}
    assert by[1].status == FAILED
    assert by[2].status == SKIPPED


def test_independent_steps_run_in_parallel():
    # each agent sleeps 0.2s; 3 independent steps must finish well under 0.6s serial.
    def run_agent(spec, task):
        time.sleep(0.2)
        return {"status": "ok", "result": spec.name}
    plan = _plan([
        PlanStep(1, "ANALYZE", "a", "SearchAgent"),
        PlanStep(2, "ANALYZE", "b", "WebAgent"),
        PlanStep(3, "ANALYZE", "c", "CtxAgent"),
    ])
    t0 = time.time()
    _, results = Orchestrator(run_agent, parallel=True, max_workers=3).run(plan)
    elapsed = time.time() - t0
    assert all(r.status == DONE for r in results)
    assert elapsed < 0.5           # parallel, not 0.6s+ serial


def test_timeout_escalates_via_monitor():
    def run_agent(spec, task):
        time.sleep(0.5)            # exceeds the 0.1s budget
        return {"status": "ok", "result": "late"}
    plan = _plan([PlanStep(1, "IMPLEMENT", "slow", "RunAgent")])
    _, results = Orchestrator(run_agent, parallel=False, timeout_s=0.1).run(plan)
    # RunAgent is terminal (fallback=None) -> timeout escalates to the user.
    assert results[0].status in (FAILED, "ESCALATE")


def test_bus_records_dispatch_events():
    bus = EventBus()
    run_agent = lambda spec, task: {"status": "ok", "result": "x"}
    plan = _plan([PlanStep(1, "IMPLEMENT", "w", "FSAgent")])
    Orchestrator(run_agent, bus=bus, parallel=False).run(plan)
    assert any(m.msg_type == "STEP_DISPATCH" for m in bus.history)
