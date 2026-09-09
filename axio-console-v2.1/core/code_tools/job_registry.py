"""In-process registry of detached background jobs (dev servers / watchers).

`node_tools._launch_detached` starts long-running npm scripts with `subprocess.Popen`
and returns immediately (fire-and-forget) so the agent is never blocked. Before this
module there was no way to see or stop those jobs — a real gap for the UI's
"Background jobs" panel. This registry tracks each launched job and exposes liveness
and a stop action.

Scope: the registry lives in the process that launched the job. In the web UI the
orchestrated Code path launches dev servers inside the `web_api` process, so
`GET /api/jobs` sees them. Jobs launched by the separate terminal Code process are
tracked in that process only (by design — separate memory).
"""
from __future__ import annotations

import os
import subprocess
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _Job:
    id: str
    pid: int | None
    script: str
    workspace: str
    log_path: str
    started_at: str
    proc: subprocess.Popen | None = None


_lock = threading.Lock()
_jobs: dict[str, _Job] = {}


def register(*, pid: int | None, script: str, workspace: str, log_path: str,
             proc: subprocess.Popen | None = None) -> str:
    """Record a launched background job. Returns the new job id."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = _Job(
            id=job_id, pid=pid, script=script, workspace=workspace,
            log_path=log_path, started_at=_now_iso(), proc=proc,
        )
    return job_id


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in (out.stdout or "")
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _alive(job: _Job) -> bool:
    if job.proc is not None:
        return job.proc.poll() is None
    return _pid_alive(job.pid)


def _to_dict(job: _Job) -> dict:
    return {
        "id": job.id,
        "pid": job.pid,
        "script": job.script,
        "workspace": job.workspace,
        "log_path": job.log_path,
        "started_at": job.started_at,
        "status": "running" if _alive(job) else "stopped",
    }


def list_jobs() -> list[dict]:
    """All tracked jobs, newest first, each with live status."""
    with _lock:
        jobs = list(_jobs.values())
    return sorted((_to_dict(j) for j in jobs), key=lambda d: d["started_at"], reverse=True)


def stop(job_id: str) -> dict:
    """Terminate a running job's process (best-effort). Raises KeyError if unknown."""
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        raise KeyError(job_id)
    if job.proc is not None and job.proc.poll() is None:
        try:
            job.proc.terminate()
        except OSError:
            pass
    elif _pid_alive(job.pid):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(job.pid), "/F", "/T"],
                               capture_output=True, timeout=10)
            else:
                os.kill(job.pid, 15)
        except (OSError, subprocess.SubprocessError):
            pass
    return _to_dict(job)


def tail_log(job_id: str, max_bytes: int = 8000) -> str:
    """Return the tail of a job's log file (or an explanatory string)."""
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        raise KeyError(job_id)
    try:
        with open(job.log_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return f"(log unavailable: {exc})"


def clear() -> None:
    """Drop all records (used by tests)."""
    with _lock:
        _jobs.clear()
