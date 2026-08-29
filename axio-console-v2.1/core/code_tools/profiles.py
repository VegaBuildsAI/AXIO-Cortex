"""Per-mode tool profiles over the single 42-tool registry.

Chat, Cowork, and Code all draw their tools from the same
``CODE_TOOL_REGISTRY``; a profile is just the subset of tool *names* a mode is
allowed to call. The registry's per-tool risk/approval gate still applies to
every call regardless of profile — a profile is role-scoping, not a security
boundary on its own.

Keep names here in sync with the registry; ``profile_tool_names`` silently drops
any name the registry does not define so a future rename can't crash a mode.
"""

from __future__ import annotations

from . import CODE_TOOL_REGISTRY


# Chat: an assistant "with hands" — read, produce documents, and use the web.
CHAT_TOOLS: tuple[str, ...] = (
    "read_file", "write_file",
    "create_docx", "create_xlsx", "create_pptx", "create_pdf",
    "web_search", "web_fetch", "web_extract",
    "browser_open", "browser_snapshot", "browser_click",
)

# Cowork: everything Chat has, plus a robust workspace/file + retrieval +
# read-only-git + runtime-inspection set. Destructive/execute tools are included
# but stay behind the registry's approval gate. The heavy github/git-write flow
# is left to Code mode.
COWORK_TOOLS: tuple[str, ...] = CHAT_TOOLS + (
    "edit_file", "apply_patch", "list_dir", "create_dir", "delete_file",
    "search_files", "grep_files", "read_docx",
    "index_workspace", "semantic_search", "search_docs",
    "inspect_python_environment", "run_python",
    "inspect_node_environment", "run_npm_script",
    "git_status", "git_diff",
    "run_command", "verification_gate",
)


def all_tool_names() -> tuple[str, ...]:
    """Every tool the registry defines (Code mode's full profile)."""
    return tuple(tool.name for tool in CODE_TOOL_REGISTRY.tools)


_PROFILES: dict[str, tuple[str, ...]] = {
    "chat": CHAT_TOOLS,
    "cowork": COWORK_TOOLS,
}


def profile_tool_names(mode: str) -> tuple[str, ...]:
    """Resolve a mode name to its allowed tool names, dropping unknown names.

    ``code`` (and any unknown mode) resolves to the full 42-tool registry.
    """
    names = _PROFILES.get(mode.lower())
    if names is None:
        return all_tool_names()
    known = {tool.name for tool in CODE_TOOL_REGISTRY.tools}
    return tuple(name for name in names if name in known)
