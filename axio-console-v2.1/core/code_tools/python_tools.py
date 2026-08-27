"""Python inspection and argument-safe execution tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

from core.coding_skills import inspect_python_environment, resolve_python_interpreter
from core.config import CODE_PYTHON_TIMEOUT, TIMEOUT

from .registry import CodeTool, ToolResult


def inspect_environment(working_dir: str | None = None) -> str:
    return inspect_python_environment(working_dir)


def run_python(
    script_path: str,
    args: list[str] | None = None,
    working_dir: str | None = None,
    timeout_seconds: int = CODE_PYTHON_TIMEOUT,
) -> ToolResult:
    script = Path(script_path).expanduser()
    if not script.is_absolute():
        return ToolResult("ERROR: script_path must be absolute", ok=False)
    script = script.resolve()
    if not script.is_file():
        return ToolResult(f"ERROR: Python file not found: {script}", ok=False)
    if script.suffix.lower() != ".py":
        return ToolResult("ERROR: run_python only executes .py files", ok=False)

    cwd = Path(working_dir).expanduser().resolve() if working_dir else script.parent
    if not cwd.is_dir():
        return ToolResult(f"ERROR: Working directory not found: {cwd}", ok=False)
    interpreter = resolve_python_interpreter(cwd)
    safe_args = [str(item) for item in (args or [])]
    timeout = max(1, min(int(timeout_seconds), TIMEOUT))

    try:
        process = subprocess.run(
            [str(interpreter), str(script), *safe_args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd),
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(f"ERROR: Python timed out after {timeout}s", ok=False)
    except (OSError, ValueError) as exc:
        return ToolResult(f"ERROR running Python: {exc}", ok=False)

    parts = [f"PYTHON: {interpreter}", f"EXIT CODE: {process.returncode}"]
    if process.stdout.strip():
        parts.append(f"STDOUT:\n{process.stdout.strip()}")
    if process.stderr.strip():
        parts.append(f"STDERR:\n{process.stderr.strip()}")
    verification = (f"python:{script.name}",) if process.returncode == 0 else ()
    return ToolResult("\n".join(parts), ok=process.returncode == 0, verification_ids=verification)


TOOLS = [
    CodeTool("inspect_python_environment", "Inspect the selected Python interpreter, virtual environment, dependency files, and installed distributions without changing state.", {"type": "object", "properties": {"working_dir": {"type": "string"}}}, inspect_environment, "read"),
    CodeTool("run_python", "Run an existing Python file with structured arguments and a bounded timeout. Requires human approval.", {"type": "object", "properties": {"script_path": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}, "working_dir": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600}}, "required": ["script_path"]}, run_python, "execute"),
]
