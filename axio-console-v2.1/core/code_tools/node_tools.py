"""Node.js environment inspection and npm-script execution."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from core.config import CODE_NODE_TIMEOUT, TIMEOUT

from .registry import CodeTool, ToolResult

# Scripts that start a persistent process (dev server / watcher) and never exit
# on their own. Running these with a blocking, output-capturing subprocess would
# freeze the whole console until the timeout, so they are launched detached.
_LONG_RUNNING_NAMES = {"dev", "start", "serve", "watch", "preview", "storybook"}
# Precise server/watch markers only — deliberately NOT bare "vite"/"next", which
# also appear in one-shot scripts like "vite build".
_LONG_RUNNING_MARKERS = (
    "nodemon", "--watch", "webpack serve", "webpack-dev-server",
    "http-server", "live-server", "vite dev", "vite serve", "vite preview",
    "next dev", "nuxt dev", "astro dev", "remix dev", "ng serve",
)


def _is_long_running(script: str, script_body: str) -> bool:
    if script.lower() in _LONG_RUNNING_NAMES:
        return True
    body = str(script_body or "").lower()
    return any(marker in body for marker in _LONG_RUNNING_MARKERS)


def _launch_detached(command: list[str], root: Path, script: str) -> ToolResult:
    """Start a persistent script in the background, logging to a file, and return
    immediately so the agent/console is never blocked by a server that won't exit."""
    log_path = root / f".axio-dev-{script}.log"
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        log_file = open(log_path, "w", encoding="utf-8")
    except OSError as exc:
        return ToolResult(f"ERROR: cannot open log file {log_path}: {exc}", ok=False)
    try:
        proc = subprocess.Popen(
            command, cwd=str(root), stdout=log_file, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=creationflags, close_fds=True,
        )
    except OSError as exc:
        log_file.close()
        return ToolResult(f"ERROR launching npm '{script}': {exc}", ok=False)
    finally:
        log_file.close()  # the child keeps its own inherited handle
    from . import job_registry

    job_id = job_registry.register(
        pid=proc.pid, script=script, workspace=str(root),
        log_path=str(log_path), proc=proc,
    )
    return ToolResult(
        f"Started long-running npm script '{script}' in the background (PID {proc.pid}, job {job_id}).\n"
        f"Working dir: {root}\n"
        f"Logs: {log_path}\n"
        "It is left running so the agent is not blocked. Read the log file for the "
        "dev URL, or open that URL in the Browser preview. It is tracked in the "
        "Background jobs panel and can be stopped from there.",
        ok=True,
    )


def _working_directory(path: str) -> Path:
    root = Path(path).expanduser()
    if not root.is_absolute():
        raise ValueError("working_dir must be absolute")
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Working directory not found: {root}")
    return root


def _version(executable: str | None) -> str:
    if not executable:
        return "not found"
    try:
        process = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=15, shell=False)
        return (process.stdout or process.stderr).strip() or f"exit {process.returncode}"
    except OSError as exc:
        return f"error: {exc}"


def inspect_node_environment(working_dir: str) -> str:
    root = _working_directory(working_dir)
    node = shutil.which("node")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    lines = [
        f"Working directory: {root}",
        f"Node executable: {node or 'not found'}",
        f"Node version: {_version(node)}",
        f"npm executable: {npm or 'not found'}",
        f"npm version: {_version(npm)}",
    ]

    package_path = root / "package.json"
    if package_path.is_file():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
            dependencies = package.get("dependencies", {}) if isinstance(package, dict) else {}
            dev_dependencies = package.get("devDependencies", {}) if isinstance(package, dict) else {}
            lines.extend([
                f"package.json: {package_path}",
                "npm scripts: " + (", ".join(sorted(scripts)) if isinstance(scripts, dict) and scripts else "(none)"),
                f"dependencies: {len(dependencies) if isinstance(dependencies, dict) else 0}",
                f"devDependencies: {len(dev_dependencies) if isinstance(dev_dependencies, dict) else 0}",
            ])
        except (OSError, json.JSONDecodeError) as exc:
            lines.append(f"package.json error: {exc}")
    else:
        lines.append("package.json: not found")
    lockfiles = [name for name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock") if (root / name).exists()]
    lines.append("lockfiles: " + (", ".join(lockfiles) if lockfiles else "(none)"))
    lines.append(f"node_modules: {'present' if (root / 'node_modules').is_dir() else 'absent'}")
    return "\n".join(lines)


def run_npm_script(
    working_dir: str,
    script: str,
    args: list[str] | None = None,
    timeout_seconds: int = CODE_NODE_TIMEOUT,
) -> ToolResult:
    root = _working_directory(working_dir)
    package_path = root / "package.json"
    if not package_path.is_file():
        return ToolResult(f"ERROR: package.json not found in {root}", ok=False)
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ToolResult(f"ERROR reading package.json: {exc}", ok=False)
    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
    if not isinstance(scripts, dict) or script not in scripts:
        return ToolResult(f"ERROR: npm script '{script}' is not defined", ok=False)
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        return ToolResult("ERROR: npm executable not found", ok=False)
    timeout = max(1, min(int(timeout_seconds), TIMEOUT))
    command = [npm, "run", script]
    if args:
        command.extend(["--", *[str(item) for item in args]])
    # A persistent dev server/watcher never returns; run it detached instead of
    # blocking the console for the full timeout (the root cause of a frozen session).
    if _is_long_running(script, scripts.get(script, "")):
        return _launch_detached(command, root, script)
    try:
        process = subprocess.run(command, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        return ToolResult(f"ERROR: npm script timed out after {timeout}s", ok=False)
    except OSError as exc:
        return ToolResult(f"ERROR running npm: {exc}", ok=False)
    parts = [f"NPM SCRIPT: {script}", f"EXIT CODE: {process.returncode}"]
    if process.stdout.strip():
        parts.append(f"STDOUT:\n{process.stdout.strip()}")
    if process.stderr.strip():
        parts.append(f"STDERR:\n{process.stderr.strip()}")
    verification = (f"npm:{script}",) if process.returncode == 0 else ()
    return ToolResult("\n".join(parts), ok=process.returncode == 0, verification_ids=verification)


TOOLS = [
    CodeTool("inspect_node_environment", "Inspect Node/npm versions, package scripts, dependencies, lockfiles, and node_modules without changing state.", {"type": "object", "properties": {"working_dir": {"type": "string"}}, "required": ["working_dir"]}, inspect_node_environment, "read"),
    CodeTool("run_npm_script", "Run one script declared in package.json with structured arguments and a bounded timeout. Requires human approval.", {"type": "object", "properties": {"working_dir": {"type": "string"}, "script": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600}}, "required": ["working_dir", "script"]}, run_npm_script, "execute"),
]
