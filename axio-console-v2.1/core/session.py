"""
AXIO Core — Session Manager
Handles create / save / load / list / delete / clear for all modes.
Sessions are persisted as JSON files under ~/.axio/sessions/.
Context pruning automatically trims old messages when the session grows too large.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from .config import SESSIONS_DIR, CONTEXT_LIMIT


class SessionManager:
    """Unified session management shared by Chat, Cowork, Code, and RevRec modes."""

    def __init__(self, sessions_dir: Path = None):
        self.dir = sessions_dir or SESSIONS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    # ── create ───────────────────────────────────────────

    def new(self, name: str = None, model: str = "", mode: str = "chat") -> dict:
        """Create and return a fresh session dict (not yet saved to disk)."""
        sid = str(uuid.uuid4())[:8]
        return {
            "id":            sid,
            "name":          name or f"session_{sid}",
            "model":         model,
            "mode":          mode,
            "backend":       "ollama",
            "created":       datetime.now().isoformat(),
            "updated":       datetime.now().isoformat(),
            "messages":      [],
            "message_count": 0,
        }

    # ── persist ──────────────────────────────────────────

    def save(self, session: dict):
        """Prune oversized context, then write session to disk."""
        session["updated"]       = datetime.now().isoformat()
        session["message_count"] = len(session.get("messages", []))

        msgs = session.get("messages", [])
        if len(msgs) > CONTEXT_LIMIT:
            # Keep the most recent N messages so the model always has context
            session["messages"] = msgs[-CONTEXT_LIMIT:]

        path = self.dir / f"{session['name']}.json"
        pending = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(pending, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)

    # ── load ─────────────────────────────────────────────

    def load(self, name: str) -> dict | None:
        """Load a saved session by name. Returns None if not found."""
        path = self.dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    # ── list ─────────────────────────────────────────────

    def list_sessions(self) -> list:
        """Return all saved sessions sorted by most-recently modified."""
        sessions = []
        for p in sorted(
            self.dir.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        ):
            try:
                with open(p, encoding="utf-8") as f:
                    sessions.append(json.load(f))
            except Exception:
                pass
        return sessions

    # ── delete ───────────────────────────────────────────

    def delete(self, name: str) -> bool:
        """Permanently delete a session file. Returns True if found."""
        path = self.dir / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    # ── helpers ──────────────────────────────────────────

    def clear(self, session: dict) -> int:
        """Clear all messages from the session. Returns count cleared."""
        count = len(session.get("messages", []))
        session["messages"] = []
        return count

    def add_turn(self, session: dict, user_text: str, assistant_text: str):
        """Append a user+assistant message pair to the session."""
        session["messages"].append({"role": "user",      "content": user_text})
        session["messages"].append({"role": "assistant", "content": assistant_text})

    def message_count(self, session: dict) -> int:
        return len(session.get("messages", []))
