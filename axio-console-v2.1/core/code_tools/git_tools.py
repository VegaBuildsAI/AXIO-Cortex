"""Read-only Git evidence tools."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .registry import CodeTool, ToolResult


def _git_run(working_dir: str, arguments: list[str], max_chars: int = 50_000) -> ToolResult:
    root = Path(working_dir).expanduser()
    if not root.is_absolute():
        return ToolResult("ERROR: working_dir must be absolute", ok=False)
    root = root.resolve()
    if not root.is_dir():
        return ToolResult(f"ERROR: Working directory not found: {root}", ok=False)
    git = shutil.which("git")
    if not git:
        return ToolResult("ERROR: git executable not found", ok=False)
    try:
        process = subprocess.run([git, "-C", str(root), *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, shell=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult(f"ERROR running git: {exc}", ok=False)
    output = "\n".join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
    if len(output) > max_chars:
        output = output[:max_chars] + f"\n... truncated at {max_chars} chars"
    if process.returncode:
        return ToolResult(f"ERROR: git exited {process.returncode}\n{output}", ok=False)
    return ToolResult(output or "(no output)")


def git_status(working_dir: str) -> ToolResult:
    return _git_run(working_dir, ["status", "--short", "--branch"])


def git_diff(working_dir: str, staged: bool = False, paths: list[str] | None = None, max_chars: int = 50_000) -> ToolResult:
    arguments = ["diff"]
    if staged:
        arguments.append("--cached")
    if paths:
        arguments.append("--")
        arguments.extend(str(path) for path in paths)
    return _git_run(working_dir, arguments, max(1_000, min(int(max_chars), 200_000)))


TOOLS = [
    CodeTool("git_status", "Read concise Git branch and worktree status without changing the repository.", {"type": "object", "properties": {"working_dir": {"type": "string"}}, "required": ["working_dir"]}, git_status, "read"),
    CodeTool("git_diff", "Read a bounded unstaged or staged Git diff, optionally limited to paths.", {"type": "object", "properties": {"working_dir": {"type": "string"}, "staged": {"type": "boolean"}, "paths": {"type": "array", "items": {"type": "string"}}, "max_chars": {"type": "integer", "minimum": 1000, "maximum": 200000}}, "required": ["working_dir"]}, git_diff, "read"),
]
