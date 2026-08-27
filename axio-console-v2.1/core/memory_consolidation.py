from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCRIPT = ROOT / "scripts" / "axio_memory_runtime.py"


def _runtime_python() -> Path:
    """Prefer the project runtime, falling back to the active interpreter."""
    if os.name == "nt":
        candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ROOT / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


def trigger_exit_consolidation() -> bool:
    """Start one non-blocking Cortex consolidation after a session is stored.

    The memory runtime owns the cross-process writer lock. If the continuous
    runtime is already active, this one-shot process exits harmlessly and the
    active runtime performs the pending consolidation.
    """
    if not RUNTIME_SCRIPT.exists():
        return False

    env = os.environ.copy()
    env["AXIO_MEMORY_BACKEND"] = "postgres"
    kwargs = {
        "cwd": str(ROOT),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen(
            [
                str(_runtime_python()),
                str(RUNTIME_SCRIPT),
                "--once",
                "--consolidate-only",
            ],
            **kwargs,
        )
    except OSError:
        return False
    return True
