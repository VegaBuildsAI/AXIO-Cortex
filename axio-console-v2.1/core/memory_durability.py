"""Crash-safe local journal and Postgres replay queue for AXIO memory.

The local files are a write-ahead mirror, not a competing source of truth:
Postgres remains primary whenever it is reachable.  Atomic JSON files make
completed events recoverable after a forced process termination and allow
idempotent replay after a database outage.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from core.config import JOURNAL_DIR, OUTBOX_DIR


_LOCK = threading.RLock()
PENDING_DIR = OUTBOX_DIR / "pending"
DEAD_DIR = OUTBOX_DIR / "dead"        # quarantine for permanently-failing events
MAX_REPLAY_ATTEMPTS = 5              # dead-letter a poison event after this many tries


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(pending, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        # On Windows os.replace can transiently fail with PermissionError if a
        # concurrent reader has the target open; retry briefly before giving up.
        for attempt in range(5):
            try:
                pending.replace(path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        pending.unlink(missing_ok=True)


def save_session_snapshot(session: dict) -> Path:
    """Persist the current raw session after every message."""
    session_id = str(session.get("id") or uuid.uuid4())
    session["id"] = session_id
    mode = str(session.get("mode", "chat"))
    path = JOURNAL_DIR / mode / f"{session_id}.json"
    with _LOCK:
        atomic_write_json(path, session)
    return path


def enqueue(operation: str, mode: str, payload: dict, event_id: str | None = None) -> str:
    """Create a durable pending event before attempting the Postgres write."""
    event_id = event_id or str(uuid.uuid4())
    event = {
        "event_id": event_id,
        "operation": operation,
        "mode": mode,
        "payload": payload,
    }
    with _LOCK:
        atomic_write_json(PENDING_DIR / f"{event_id}.json", event)
    return event_id


def acknowledge(event_id: str) -> None:
    """Remove a pending event only after Postgres committed it."""
    with _LOCK:
        (PENDING_DIR / f"{event_id}.json").unlink(missing_ok=True)


def pending_events() -> list[dict]:
    if not PENDING_DIR.exists():
        return []
    events = []
    with _LOCK:
        for path in sorted(PENDING_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime):
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
                event["_path"] = str(path)
                events.append(event)
            except (OSError, json.JSONDecodeError):
                continue
    return events


def pending_count() -> int:
    return len(pending_events())


def record_attempt(event: dict, error: object) -> int:
    """Persist an incremented retry counter on a pending event.

    Returns the new attempt count (0 if the file could not be updated). Only
    call this for *permanent* failures -- transient DB outages must not count
    toward dead-lettering, or a long outage would discard healthy events.
    """
    path_str = event.get("_path")
    if not path_str:
        return 0
    path = Path(path_str)
    with _LOCK:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        attempts = int(data.get("_attempts", 0)) + 1
        data["_attempts"] = attempts
        data["_last_error"] = str(error)[:500]
        atomic_write_json(path, data)
        return attempts


def dead_letter(event: dict) -> None:
    """Move a permanently-failing event out of the pending queue into dead/."""
    path_str = event.get("_path")
    if not path_str:
        return
    path = Path(path_str)
    DEAD_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        try:
            path.replace(DEAD_DIR / path.name)
        except OSError:
            path.unlink(missing_ok=True)
