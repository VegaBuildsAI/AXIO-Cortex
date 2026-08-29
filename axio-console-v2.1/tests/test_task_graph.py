"""Fase C · C5 / Fase E6 — task graph dependency ordering."""
import pytest

from harness.plan import Plan, PlanStep
from harness.task_graph import levels, execution_order, CycleError


def _step(i, deps=(), phase="IMPLEMENT"):
    return PlanStep(id=i, phase=phase, description=f"s{i}", agent="FSAgent",
                    depends_on=deps)


def test_independent_steps_share_a_level():
    plan = Plan("t", [_step(1), _step(2), _step(3)])
    lv = levels(plan)
    assert len(lv) == 1
    assert {s.id for s in lv[0]} == {1, 2, 3}


def test_dependency_pushes_to_next_level():
    plan = Plan("t", [_step(1), _step(2), _step(3, deps=(1, 2))])
    lv = levels(plan)
    assert {s.id for s in lv[0]} == {1, 2}
    assert [s.id for s in lv[1]] == [3]


def test_execution_order_respects_deps():
    plan = Plan("t", [_step(1, deps=(2,)), _step(2), _step(3, deps=(1,))])
    order = [s.id for s in execution_order(plan)]
    assert order.index(2) < order.index(1) < order.index(3)


def test_cycle_detected():
    # 1 -> 2 -> 1 is a cycle; deps exist and are non-self, so Plan accepts it
    # but the task graph must reject it.
    plan = Plan("t", [_step(1, deps=(2,)), _step(2, deps=(1,))])
    with pytest.raises(CycleError):
        levels(plan)
