"""
AXIO Harness -- Task Graph  (Plan Fase C · C5)

Reads the `depends_on` edges of a Plan and produces an execution order that
respects dependencies. Steps with no dependency between them land in the same
"level" and are therefore candidates for parallel dispatch (Fase C · C8). Steps
that depend on earlier work land in later levels behind a rendezvous barrier.

Pure, synchronous, and LLM-free so it is fully unit-testable.
"""

from __future__ import annotations

from harness.plan import Plan, PlanStep


class CycleError(ValueError):
    """Raised when the plan's depends_on edges form a cycle."""


def levels(plan: Plan) -> list[list[PlanStep]]:
    """Group steps into dependency levels via Kahn's algorithm.

    levels()[0] has no dependencies; every step in level N depends only on steps
    in levels < N. Steps within one level are mutually independent and may run
    concurrently. Order within a level follows ascending step id for determinism.
    """
    steps = {s.id: s for s in plan.steps}
    indeg = {sid: 0 for sid in steps}
    dependents: dict[int, list[int]] = {sid: [] for sid in steps}
    for s in plan.steps:
        for dep in s.depends_on:
            indeg[s.id] += 1
            dependents[dep].append(s.id)

    ready = sorted(sid for sid, d in indeg.items() if d == 0)
    result: list[list[PlanStep]] = []
    seen = 0
    while ready:
        result.append([steps[sid] for sid in ready])
        seen += len(ready)
        nxt: list[int] = []
        for sid in ready:
            for child in dependents[sid]:
                indeg[child] -= 1
                if indeg[child] == 0:
                    nxt.append(child)
        ready = sorted(nxt)

    if seen != len(steps):
        stuck = sorted(sid for sid, d in indeg.items() if d > 0)
        raise CycleError(f"Dependency cycle among steps {stuck}")
    return result


def execution_order(plan: Plan) -> list[PlanStep]:
    """Flat, dependency-respecting order (levels concatenated)."""
    return [s for level in levels(plan) for s in level]


def parallel_groups(plan: Plan) -> list[list[PlanStep]]:
    """Alias for levels(): each inner list is a group safe to run in parallel."""
    return levels(plan)
