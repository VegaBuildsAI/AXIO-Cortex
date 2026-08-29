"""
AXIO Agents -- AgentSpec  (Plan Fase B · B2)

One immutable spec per sub-agent: a fixed tool set, a risk level, a fallback
target, an internet-access flag, an allowed peer map, and a bash scope. The
harness reads *only* these specs to decide what a given agent may do — an agent
can never touch a tool outside its declared set.

Two tool vocabularies are reconciled here:
  * TARGET tools  -- the full logical capability set from the architecture plan
                     (e.g. move_file, run_python, web_search, git_commit).
  * LIVE tools    -- the subset of TARGET that is actually implemented today
                     (the 9 concrete tools in modes/code.py). `live_tools()`
                     returns this intersection, which is what the dispatcher
                     hands to the model right now.
As tools get implemented they are added to IMPLEMENTED_TOOLS / TOOL_ALIASES and
the live set grows automatically — no spec changes needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Risk levels ──────────────────────────────────────────────────────────────
LOW, MEDIUM, HIGH = "LOW", "MEDIUM", "HIGH"

# ── Concrete tools implemented today (source of truth: modes/code.py) ────────
IMPLEMENTED_TOOLS: frozenset[str] = frozenset({
    "read_file", "write_file", "edit_file", "list_dir",
    "create_dir", "delete_file", "search_files", "grep_files", "run_command",
})

# Map a plan/logical tool name onto the concrete tool that fulfils it today.
# Identity entries are omitted; only true aliases are listed.
#
# NB: `bash` is deliberately NOT aliased to run_command. The plan gives most
# agents *scoped* bash (file-ops / git-only / test-only allowlists) and only
# RunAgent unrestricted bash. Until that per-agent allowlist enforcement exists,
# mapping bash -> run_command would hand every bash-holding agent unrestricted
# execution and collapse the isolation guarantee. So bash resolves to no live
# tool for now; agents still reach the shell through the explicit run_command
# tool where their spec grants it (RunAgent only today).
TOOL_ALIASES: dict[str, str] = {
    "grep_search":    "grep_files",
    "find_files":     "search_files",
    "run_python":     "run_command",
    "run_powershell": "run_command",
}


def to_concrete(tool: str) -> str | None:
    """Resolve a logical tool name to a concrete implemented tool, or None."""
    concrete = TOOL_ALIASES.get(tool, tool)
    return concrete if concrete in IMPLEMENTED_TOOLS else None


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    tools: tuple[str, ...]              # TARGET capability set (logical names)
    risk: str = LOW
    fallback: str | None = None         # agent name, or None => escalate to user
    internet_access: bool = False
    peers: tuple[str, ...] = ()          # agents this one may call directly
    bash_scope: str | None = None        # None, "unrestricted", or an allowlist tag
    max_steps: int = 8
    system_prompt: str = ""

    def live_tools(self) -> tuple[str, ...]:
        """Concrete, de-duplicated tools this agent can actually use today."""
        seen: list[str] = []
        for t in self.tools:
            c = to_concrete(t)
            if c and c not in seen:
                seen.append(c)
        return tuple(seen)

    def can_call(self, other: str) -> bool:
        """Peer-map guard: may this agent issue a direct peer call to `other`?"""
        return other in self.peers
