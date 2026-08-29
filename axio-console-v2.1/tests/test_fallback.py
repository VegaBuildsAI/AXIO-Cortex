"""Fase C · C3 / Fase E3 — fallback chain with 2-hop limit."""
from harness import fallback
from harness.fallback import cannot_handle, run_with_fallback, is_cannot_handle


def test_success_no_fallback():
    disp = lambda name, task: {"status": "ok", "result": "done", "agent": name}
    fr = run_with_fallback("FSAgent", "t", disp)
    assert fr.trail == ["FSAgent"]
    assert fr.escalated_to_user is False
    assert fr.response["result"] == "done"


def test_fs_to_run_one_hop():
    # FSAgent can't handle -> engine routes to its spec fallback RunAgent, which succeeds.
    def disp(name, task):
        if name == "FSAgent":
            return cannot_handle("relative path failed", suggested_fallback="RunAgent")
        return {"status": "ok", "result": "mkdir ok", "agent": name}
    fr = run_with_fallback("FSAgent", "create_dir('.x')", disp)
    assert fr.trail == ["FSAgent", "RunAgent"]
    assert fr.hops == 1
    assert fr.response["result"] == "mkdir ok"


def test_two_hop_limit_escalates():
    # everyone keeps saying CANNOT_HANDLE -> after 2 hops, escalate to user.
    disp = lambda name, task: cannot_handle("nope", suggested_fallback="RunAgent")
    fr = run_with_fallback("FSAgent", "t", disp, max_hops=2)
    assert fr.escalated_to_user is True
    assert len(fr.trail) <= 3          # start + at most 2 fallbacks


def test_terminal_agent_escalates_immediately():
    # RunAgent has fallback=None; a CANNOT_HANDLE from it escalates to the user.
    disp = lambda name, task: cannot_handle("no shell")
    fr = run_with_fallback("RunAgent", "t", disp)
    assert fr.trail == ["RunAgent"]
    assert fr.escalated_to_user is True


def test_is_cannot_handle_predicate():
    assert is_cannot_handle(cannot_handle("x")) is True
    assert is_cannot_handle({"status": "ok"}) is False
