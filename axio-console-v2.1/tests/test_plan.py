"""Fase A · A3 / A4 — Plan + PlanStep model."""
import pytest

from harness.plan import Plan, PlanStep, PHASES


def test_rejects_unknown_phase():
    with pytest.raises(ValueError):
        PlanStep(id=1, phase="BOGUS", description="x", agent="FSAgent")


def test_rejects_unknown_dependency():
    with pytest.raises(ValueError):
        Plan("t", [PlanStep(1, "IMPLEMENT", "x", "FSAgent", depends_on=(9,))])


def test_rejects_self_dependency():
    with pytest.raises(ValueError):
        Plan("t", [PlanStep(1, "IMPLEMENT", "x", "FSAgent", depends_on=(1,))])


def test_roundtrip_dict():
    plan = Plan("build feature", [
        PlanStep(1, "DISCOVER", "read workspace", "CtxAgent"),
        PlanStep(2, "IMPLEMENT", "write code", "FSAgent", depends_on=(1,),
                 verify="file exists", rollback="delete file"),
    ])
    again = Plan.from_dict(plan.to_dict())
    assert again.task == "build feature"
    assert again.steps[1].depends_on == (1,)
    assert again.steps[1].rollback == "delete file"


def test_phase_summary_orders_by_lifecycle():
    plan = Plan("t", [
        PlanStep(2, "TEST", "run tests", "TestAgent"),
        PlanStep(1, "DISCOVER", "scan", "CtxAgent"),
    ])
    summary = "\n".join(plan.phase_summary())
    assert summary.index("DISCOVER") < summary.index("TEST")


def test_eight_phases_defined():
    assert PHASES == ("DISCOVER", "ANALYZE", "DESIGN", "IMPLEMENT",
                      "TEST", "REVIEW", "SHIP", "DOCUMENT")
