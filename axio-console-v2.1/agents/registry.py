"""
AXIO Agents -- Central Registry  (Plan Fase B · B3)

The one module the harness imports to know every sub-agent. Maps agent name ->
AgentSpec. Each spec's tool set, risk, fallback, peer map and internet flag are
the *only* source of authority the dispatcher and fallback engine consult.

Refinement note: the plan called for one file per agent (agents/fs_agent.py …).
Those were consolidated into these declarative specs — each agent's behavioural
detail lives in skills/agents/<name>/SKILL.md, which is where the plan intends
the operational rules to live anyway. This keeps the registry auditable at a
glance and avoids eight near-identical boilerplate modules.
"""

from __future__ import annotations

from agents.base import AgentSpec, LOW, MEDIUM, HIGH

# ── The eight specialists ────────────────────────────────────────────────────

FS_AGENT = AgentSpec(
    name="FSAgent",
    description="Filesystem operations. Always verifies after writing; never uses relative paths.",
    tools=("read_file", "write_file", "edit_file", "list_dir", "create_dir",
           "move_file", "copy_file", "delete_file", "verify_file", "bash"),
    risk=MEDIUM,
    fallback="RunAgent",           # file op fails -> retry as an unrestricted shell op
    internet_access=False,
    peers=("CtxAgent", "RunAgent"),
    bash_scope="file-ops",         # chmod, ln -s, find, tar — never app code
    system_prompt=(
        "You are FSAgent, the filesystem specialist. Read before you edit, "
        "list before you create, verify after you write. Use absolute paths. "
        "If a file op fails repeatedly, return AGENT_CANNOT_HANDLE with "
        "suggested_fallback=RunAgent."
    ),
)

RUN_AGENT = AgentSpec(
    name="RunAgent",
    description="Executes code and commands. Highest risk — every execution needs approval.",
    tools=("run_command", "run_python", "run_powershell", "bash",
           "lint_code", "format_code", "compile_code"),
    risk=HIGH,
    fallback=None,                 # terminal: escalate to the user, never loop back
    internet_access=False,
    peers=("FSAgent",),            # write output to a file / read a script first
    bash_scope="unrestricted",
    system_prompt=(
        "You are RunAgent, the execution specialist and last resort for actions. "
        "Capture full stdout/stderr and exit codes and return them. If you cannot "
        "run something, escalate to the user with the complete error — do not loop."
    ),
)

SEARCH_AGENT = AgentSpec(
    name="SearchAgent",
    description="Read-only local codebase navigation and indexing. No internet.",
    tools=("grep_search", "find_files", "semantic_search", "index_workspace"),
    risk=LOW,
    fallback="WebAgent",           # datum not local -> search the web
    internet_access=False,
    peers=("WebAgent",),
    system_prompt=(
        "You are SearchAgent. Navigate the local codebase, find patterns, index "
        "the workspace. You have no internet. If the answer is not in the "
        "workspace, return AGENT_CANNOT_HANDLE with suggested_fallback=WebAgent."
    ),
)

WEB_AGENT = AgentSpec(
    name="WebAgent",
    description="The ONLY agent with internet access. Search, fetch, extract, screenshot.",
    tools=("web_search", "web_fetch", "web_retrieve", "extract_content",
           "screenshot_url", "check_url"),
    risk=MEDIUM,
    fallback="SearchAgent",        # bidirectional: web down -> look in local/cache
    internet_access=True,
    peers=("SearchAgent", "FSAgent"),
    system_prompt=(
        "You are WebAgent, the sole gateway to the internet. Prefer web_fetch when "
        "you already have a URL. Handle rate limits with backoff and JS-heavy pages "
        "with screenshot_url. Return extracted, structured content — never raw HTML."
    ),
)

GIT_AGENT = AgentSpec(
    name="GitAgent",
    description="Atomic version control. git_push is destructive — double confirmation.",
    tools=("git_status", "git_diff", "git_commit", "git_branch", "git_log",
           "bash", "git_push"),
    risk=HIGH,
    fallback=None,                 # git ops are atomic; not delegated
    internet_access=False,
    peers=("FSAgent", "RunAgent"),
    bash_scope="git-only",         # only `git *` command prefixes
    system_prompt=(
        "You are GitAgent. Make atomic commits with meaningful messages. Only "
        "`git *` shell commands are permitted. git_push requires explicit double "
        "confirmation and is the only destructive operation you own."
    ),
)

TEST_AGENT = AgentSpec(
    name="TestAgent",
    description="Quality gate. Runs tests, coverage, verification_gate before SHIP.",
    tools=("run_tests", "coverage_report", "verification_gate", "lint_results", "bash"),
    risk=LOW,
    fallback="RunAgent",           # runner misconfigured -> run tests by hand
    internet_access=False,
    peers=("FSAgent", "RunAgent"),
    bash_scope="test-only",        # only test runners: pytest, npm test, cargo test, go test
    system_prompt=(
        "You are TestAgent, the quality gate. Run tests, measure coverage, and "
        "make verification_gate pass before any SHIP. Only invoke test runners via "
        "bash; never modify files. If the gate fails, block the SHIP phase."
    ),
)

PLAN_AGENT = AgentSpec(
    name="PlanAgent",
    description="Meta: builds and updates the task graph, decomposes tasks, assigns agents.",
    tools=("task_create", "task_update", "task_list", "generate_plan", "decompose_task"),
    risk=LOW,
    fallback=None,                 # planning failure escalates to the user
    internet_access=False,
    peers=("FSAgent", "RunAgent", "SearchAgent", "WebAgent",
           "GitAgent", "TestAgent", "CtxAgent"),   # may call any agent
    system_prompt=(
        "You are PlanAgent. Decompose the task into a phased plan (DISCOVER, "
        "ANALYZE, DESIGN, IMPLEMENT, TEST, REVIEW, SHIP, DOCUMENT). Assign an "
        "agent, tools, depends_on, verify and rollback to every step."
    ),
)

CTX_AGENT = AgentSpec(
    name="CtxAgent",
    description="Awareness & memory. The only multimodal agent (vision). Runs first & last.",
    tools=("vision", "memory_read", "memory_write", "browse_files",
           "load_context", "get_screenshot", "clear_context"),
    risk=LOW,
    fallback="SearchAgent",        # local context fails -> search the workspace
    internet_access=False,
    peers=("FSAgent", "WebAgent"),
    system_prompt=(
        "You are CtxAgent, memory and awareness. You are the only agent that reads "
        "images. Load session memory during DISCOVER and write learnings during "
        "DOCUMENT. Leave the workspace better documented than you found it."
    ),
)

AGENT_REGISTRY: dict[str, AgentSpec] = {
    a.name: a for a in (
        FS_AGENT, RUN_AGENT, SEARCH_AGENT, WEB_AGENT,
        GIT_AGENT, TEST_AGENT, PLAN_AGENT, CTX_AGENT,
    )
}


# ── Lookup helpers ───────────────────────────────────────────────────────────

def get(name: str) -> AgentSpec:
    """Return the spec for `name` or raise KeyError with the valid names."""
    try:
        return AGENT_REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown agent '{name}'. Known: {sorted(AGENT_REGISTRY)}")


def internet_agents() -> list[str]:
    """Agents permitted to touch the internet (should be exactly [WebAgent])."""
    return [n for n, a in AGENT_REGISTRY.items() if a.internet_access]
