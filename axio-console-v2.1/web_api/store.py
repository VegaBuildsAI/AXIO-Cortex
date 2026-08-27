from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    """Small local JSON store. One file per conversation, written atomically."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def create(self, mode: str, title: str, workspace_id: str | None = None) -> dict:
        now = utc_now()
        conversation = {
            "id": str(uuid.uuid4()),
            "mode": mode,
            "title": (title or "New conversation").strip()[:120],
            "workspace_id": workspace_id,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self.save(conversation)
        return conversation

    def save(self, conversation: dict) -> None:
        conversation["updated_at"] = utc_now()
        target = self.root / f"{conversation['id']}.json"
        pending = target.with_suffix(".json.tmp")
        with self._lock:
            pending.write_text(
                json.dumps(conversation, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            pending.replace(target)

    def get(self, conversation_id: str) -> dict | None:
        try:
            uuid.UUID(conversation_id)
        except ValueError:
            return None
        target = self.root / f"{conversation_id}.json"
        if not target.is_file():
            return None
        try:
            with self._lock:
                return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def list(self) -> list[dict]:
        conversations = []
        with self._lock:
            for path in self.root.glob("*.json"):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["message_count"] = len(value.get("messages", []))
                    conversations.append(value)
                except (OSError, json.JSONDecodeError):
                    continue
        return sorted(
            conversations,
            key=lambda value: value.get("updated_at", ""),
            reverse=True,
        )

    def delete(self, conversation_id: str) -> bool:
        conversation = self.get(conversation_id)
        if not conversation:
            return False
        target = self.root / f"{conversation_id}.json"
        with self._lock:
            target.unlink(missing_ok=True)
        return True

    def add_message(self, conversation_id: str, role: str, content: str, **metadata) -> dict:
        with self._lock:
            conversation = self.get(conversation_id)
            if not conversation:
                raise KeyError(conversation_id)
            message = {
                "id": str(uuid.uuid4()),
                "role": role,
                "content": content,
                "created_at": utc_now(),
                **metadata,
            }
            conversation.setdefault("messages", []).append(message)
            if (
                role == "user"
                and conversation.get("title") == "New conversation"
            ):
                conversation["title"] = content.replace("\n", " ").strip()[:64]
            self.save(conversation)
            return message

