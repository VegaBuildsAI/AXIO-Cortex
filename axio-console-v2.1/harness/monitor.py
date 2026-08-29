"""
AXIO Harness -- Monitor  (Plan Fase C · C10)

Wraps a step's execution with a timeout. If the agent does not return within
`timeout_s`, the monitor stops waiting, emits an AGENT_TIMEOUT signal, and lets
the orchestrator fall back or escalate — the user never sees a raw hang/crash.
Every terminal event is appended to logs/orchestrator.log with a timestamp,
agent id, step id and outcome (OK / TIMEOUT / FALLBACK / ESCALATE).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from core.config import LOG_DIR

AGENT_TIMEOUT = "AGENT_TIMEOUT"
DEFAULT_TIMEOUT_S = 30

_LOG = Path(LOG_DIR) / "orchestrator.log"


def timeout_signal(agent: str, step_id: int | None = None) -> dict:
    return {"status": AGENT_TIMEOUT, "agent": agent, "step": step_id,
            "reason": f"{agent} exceeded timeout"}


def run_with_timeout(fn: Callable[[], dict], timeout_s: float, agent: str,
                     step_id: int | None = None) -> tuple[dict, bool]:
    """Run `fn` in a worker thread, bounded by `timeout_s`.

    Returns (result, timed_out). On timeout the worker is abandoned (Python has no
    safe force-kill) and a timeout_signal is returned so the orchestrator can act.
    """
    import threading

    box: dict[str, dict] = {}

    def _target() -> None:
        try:
            box["result"] = fn()
        except Exception as e:  # surface agent crashes as a structured failure
            box["result"] = {"status": "ERROR", "agent": agent, "reason": str(e)}

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return timeout_signal(agent, step_id), True
    return box.get("result", timeout_signal(agent, step_id)), False


def log_event(step_id: int | None, agent: str, outcome: str, detail: str = "") -> None:
    """Append one orchestrator event line. Best-effort; never raises to caller."""
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().isoformat(timespec="seconds")
        with _LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts}  step={step_id}  agent={agent}  {outcome}  {detail}\n")
    except Exception:
        pass
