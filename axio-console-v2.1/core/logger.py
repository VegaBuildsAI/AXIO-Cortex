"""
AXIO Core — Audit Logger
Appends JSONL entries to logs/<mode>_audit.jsonl for every model call and tool invocation.
All four modes share this logger for a unified audit trail.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import LOG_DIR


class AuditLogger:
    """Structured JSONL logger for model calls, tool invocations, and routing decisions."""

    def __init__(self, mode: str = "axio"):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.path = LOG_DIR / f"{mode}_audit.jsonl"

    def log_turn(
        self,
        prompt: str,
        response: str,
        model: str,
        route: str = "",
        elapsed: float = None,
        workspace: str = None,
        loaded_files: list = None,
    ):
        """Log a model conversation turn (chat / cowork)."""
        entry = {
            "ts":               datetime.now().isoformat(),
            "mode":             self.mode,
            "type":             "turn",
            "route":            route,
            "model":            model,
            "prompt_preview":   prompt[:300],
            "response_preview": response[:300],
        }
        if elapsed is not None:
            entry["elapsed_seconds"] = elapsed
        if workspace:
            entry["workspace"] = workspace
        if loaded_files:
            entry["loaded_files"] = loaded_files
        self._write(entry)

    def log_tool(
        self,
        task: str,
        tool: str,
        args: dict,
        result: str,
        model: str = "",
    ):
        """Log a single tool invocation (code agent / revrec)."""
        entry = {
            "ts":             datetime.now().isoformat(),
            "mode":           self.mode,
            "type":           "tool",
            "model":          model,
            "task_preview":   task[:200],
            "tool":           tool,
            "args":           {k: str(v)[:200] for k, v in (args or {}).items()},
            "result_preview": result[:300],
        }
        self._write(entry)

    def log_usage(
        self,
        model: str,
        tokens: dict,
        cost_usd: float = None,
        route: str = "",
        elapsed: float = None,
    ):
        """Log token usage + estimated cost for a Claude turn.

        tokens: {input, output, cache_read, cache_write}.
        """
        entry = {
            "ts":       datetime.now().isoformat(),
            "mode":     self.mode,
            "type":     "usage",
            "model":    model,
            "route":    route,
            "tokens":   tokens,
            "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
        }
        if elapsed is not None:
            entry["elapsed_seconds"] = elapsed
        self._write(entry)

    def log_event(self, event: str, detail: str = ""):
        """Log a generic lifecycle event (session created, mode switched, etc.)."""
        entry = {
            "ts":     datetime.now().isoformat(),
            "mode":   self.mode,
            "type":   "event",
            "event":  event,
            "detail": detail[:200],
        }
        self._write(entry)

    def log_metrics(self, event: str, metrics: dict):
        """Log structured operational metrics without flattening or truncation."""
        self._write({
            "ts": datetime.now().isoformat(),
            "mode": self.mode,
            "type": "metrics",
            "event": event,
            "metrics": metrics,
        })

    def _write(self, entry: dict):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
