"""Shared tool-approval policy: ask y/n, or let agents run automatically.

Every interactive approver (Chat/Cowork tool loop, Code mode, multi-agent
runs, RevRec) checks `auto_approves(tool)` before prompting. The level is
process-wide, starts from AXIO_AUTO_APPROVE (core/config.py) and is switched at
runtime with `auto on|all|off` in any mode.

  off  ask for every gated tool (default)
  on   auto-approve execute (run_command, run_python, npm scripts, browser)
       and writes outside the workspace; still ask for destructive (delete)
       and external (git push, fork, PR create/merge) actions
  all  auto-approve everything, including destructive and external
"""

from __future__ import annotations

from core.config import AUTO_APPROVE_LEVELS, AXIO_AUTO_APPROVE

_ON_RISKS = frozenset({"execute", "write"})
_level = AXIO_AUTO_APPROVE

USAGE = (
    "auto            show the approval mode\n"
    "  auto on         run commands/scripts without asking; still ask before delete and git push/PR/merge\n"
    "  auto all        approve everything automatically (including delete and push)\n"
    "  auto off        ask y/n for every gated tool (default)"
)


def get_level() -> str:
    return _level


def set_level(level: str) -> str:
    global _level
    level = (level or "").strip().lower()
    if level not in AUTO_APPROVE_LEVELS:
        raise ValueError(f"Unknown approval mode {level!r}; use: {', '.join(AUTO_APPROVE_LEVELS)}")
    _level = level
    return _level


def auto_approves(tool) -> bool:
    """True when the current level approves this tool without asking."""
    if _level == "all":
        return True
    if _level == "on":
        return getattr(tool, "risk", "") in _ON_RISKS
    return False


def describe(level: str = None) -> str:
    level = level or _level
    return {
        "off": "Approval: OFF (ask) - every gated tool asks y/n.",
        "on": "Approval: AUTO - commands and scripts run without asking; delete and git push/PR/merge still ask.",
        "all": "Approval: AUTO ALL - everything runs without asking, including delete and git push/PR/merge.",
    }[level]


def handle_auto_command(text: str) -> str | None:
    """Handle `auto`, `auto on|all|off` (optionally `/auto`). None if not ours."""
    words = (text or "").strip().lower().lstrip("/").split()
    if not words or words[0] != "auto" or len(words) > 2:
        return None
    if len(words) == 1:
        return describe() + "\n  " + USAGE
    arg = {"yes": "on", "true": "on", "no": "off", "false": "off"}.get(words[1], words[1])
    if arg not in AUTO_APPROVE_LEVELS:
        return None  # e.g. "auto complete": an ordinary message, not a command
    set_level(arg)
    return describe()


def announce(tool, args_summary: str = "") -> None:
    """One line in place of the prompt, so auto-approved actions stay visible."""
    detail = f" {args_summary}" if args_summary else ""
    print(f"  [auto-approved {getattr(tool, 'risk', '')}] {getattr(tool, 'name', '')}{detail}")
