"""Gated PowerShell fallback for workflows without a dedicated tool."""

from __future__ import annotations

import subprocess
from pathlib import Path

from core.config import CODE_COMMAND_TIMEOUT, TIMEOUT

from .registry import CodeTool, ToolResult
from .verification import verification_ids_from_command


def run_command(command: str, working_dir: str | None = None, timeout_seconds: int = CODE_COMMAND_TIMEOUT) -> ToolResult:
    cwd = None
    if working_dir:
        candidate = Path(working_dir).expanduser()
        if not candidate.is_absolute():
            return ToolResult("ERROR: working_dir must be absolute", ok=False)
        cwd = candidate.resolve()
        if not cwd.is_dir():
            return ToolResult(f"ERROR: Working directory not found: {cwd}", ok=False)
    timeout = max(1, min(int(timeout_seconds), TIMEOUT))
    try:
        process = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(f"ERROR: Command timed out after {timeout}s", ok=False)
    except OSError as exc:
        return ToolResult(f"ERROR running command: {exc}", ok=False)
    parts = [f"EXIT CODE: {process.returncode}"]
    if process.stdout.strip():
        parts.append(f"STDOUT:\n{process.stdout.strip()}")
    if process.stderr.strip():
        parts.append(f"STDERR:\n{process.stderr.strip()}")
    checks = tuple(verification_ids_from_command(command)) if process.returncode == 0 else ()
    return ToolResult("\n".join(parts), ok=process.returncode == 0, verification_ids=checks)


TOOLS = [
    CodeTool("run_command", "Run a bounded PowerShell command when no dedicated tool applies. Requires human approval.", {"type": "object", "properties": {"command": {"type": "string"}, "working_dir": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600}}, "required": ["command"]}, run_command, "execute"),
]
