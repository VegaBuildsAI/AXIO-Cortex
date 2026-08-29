"""
AXIO Harness -- Plan model  (Plan Fase A · A3)

The structured Plan Mode representation. A plan is an ordered list of PlanSteps
grouped into the eight lifecycle phases. Every step names the agent that will
execute it, the tools it may use, the steps it depends on, a verify condition,
and a rollback action — exactly the fields the orchestrator reads to dispatch
work, wait on dependencies, and recover from failure.

This replaces the old "always 3 generic steps" behaviour with a contextual,
multi-phase plan whose step count scales with task complexity.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

# The 8-phase lifecycle. Order matters: it defines the default execution sweep.
PHASES: tuple[str, ...] = (
    "DISCOVER",   # read the workspace before planning
    "ANALYZE",    # understand existing structure
    "DESIGN",     # architecture decisions; may ask the user
    "IMPLEMENT",  # the body of the work
    "TEST",       # never optional
    "REVIEW",     # lint, format, edge cases
    "SHIP",       # atomic commit
    "DOCUMENT",   # update skills + memory
)

# Status values a step moves through during execution.
PENDING, RUNNING, DONE, FAILED, SKIPPED = "PENDING", "RUNNING", "DONE", "FAILED", "SKIPPED"


@dataclass
class PlanStep:
    id: int
    phase: str
    description: str
    agent: str                              # AgentSpec name that executes this step
    tools: tuple[str, ...] = ()
    depends_on: tuple[int, ...] = ()         # step ids that must finish first
    verify: str = ""                        # post-condition the step must satisfy
    rollback: str = ""                      # how to undo this step on failure
    status: str = PENDING

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise ValueError(f"Step {self.id}: unknown phase '{self.phase}'. Valid: {PHASES}")
        # Normalize sequence-ish fields that may arrive as lists from JSON.
        self.tools = tuple(self.tools)
        self.depends_on = tuple(self.depends_on)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    task: str
    steps: list[PlanStep] = field(default_factory=list)

    def __post_init__(self) -> None:
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate step ids in plan")
        known = set(ids)
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in known:
                    raise ValueError(f"Step {s.id} depends on unknown step {dep}")
                if dep == s.id:
                    raise ValueError(f"Step {s.id} depends on itself")

    def by_id(self, step_id: int) -> PlanStep:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(f"No step with id {step_id}")

    def by_phase(self, phase: str) -> list[PlanStep]:
        return [s for s in self.steps if s.phase == phase]

    def phase_summary(self) -> list[str]:
        """Human-readable one line per phase that has steps (for the approval view)."""
        out: list[str] = []
        for ph in PHASES:
            steps = self.by_phase(ph)
            if not steps:
                continue
            out.append(f"{ph}: {len(steps)} step(s)")
            for s in steps:
                dep = f"  (after {', '.join(map(str, s.depends_on))})" if s.depends_on else ""
                out.append(f"  [{s.id}] {s.agent:<10} {s.description}{dep}")
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        steps = [PlanStep(**s) for s in data.get("steps", [])]
        return cls(task=data.get("task", ""), steps=steps)

    def to_dict(self) -> dict:
        return {"task": self.task, "steps": [s.to_dict() for s in self.steps]}
