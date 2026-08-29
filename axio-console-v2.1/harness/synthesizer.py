"""
AXIO Harness -- Synthesizer  (Plan Fase C · C4)

Combines the per-step results of many agents into one coherent answer for the
user. Groups by phase, surfaces failures and user-escalations first, and keeps
the raw agent outputs available underneath the summary.
"""

from __future__ import annotations

from dataclasses import dataclass

from harness.plan import Plan, DONE, FAILED, SKIPPED


@dataclass
class StepResult:
    step_id: int
    agent: str
    status: str            # DONE / FAILED / SKIPPED / ESCALATE
    output: str = ""


def synthesize(plan: Plan, results: list[StepResult]) -> str:
    by_id = {r.step_id: r for r in results}
    lines: list[str] = []

    failures = [r for r in results if r.status in (FAILED, "ESCALATE")]
    if failures:
        lines.append("! Unresolved steps:")
        for r in failures:
            lines.append(f"  [{r.step_id}] {r.agent}: {r.output or r.status}")
        lines.append("")

    done = sum(1 for r in results if r.status == DONE)
    lines.append(f"Completed {done}/{len(plan.steps)} steps across "
                 f"{len({s.phase for s in plan.steps})} phase(s).")
    lines.append("")

    from harness.plan import PHASES
    for ph in PHASES:
        steps = plan.by_phase(ph)
        if not steps:
            continue
        lines.append(f"-- {ph} --")
        for s in steps:
            r = by_id.get(s.id)
            mark = {DONE: "[ok]", FAILED: "[x]", SKIPPED: "[-]"}.get(
                r.status if r else "", "[ ]")
            summary = (r.output.splitlines()[0][:100] if r and r.output else s.description)
            lines.append(f"  {mark} [{s.id}] {s.agent:<10} {summary}")
        lines.append("")

    return "\n".join(lines).rstrip()
