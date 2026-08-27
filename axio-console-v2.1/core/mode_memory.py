from __future__ import annotations

import uuid
from datetime import datetime

from core.memory import MemoryManager, _handle_memory_cmd
from core.memory_consolidation import trigger_exit_consolidation
from core.memory_durability import save_session_snapshot


SHARED_MEMORY_MODES = ("chat", "cowork", "code", "console")


def shared_recall_modes(mode: str) -> list[str]:
    if mode not in SHARED_MEMORY_MODES:
        return [mode]
    modes = [mode, "console"]
    for candidate in ("chat", "cowork", "code"):
        if candidate != mode:
            modes.append(candidate)
    return modes


class ModeMemorySession:
    def __init__(self, mode: str, allowed_recall_modes: list[str] = None):
        self.mode = mode
        self.memory = MemoryManager(mode)
        self.allowed_recall_modes = allowed_recall_modes or shared_recall_modes(mode)
        now = datetime.now().isoformat()
        self.session = {
            "id": str(uuid.uuid4()),
            "name": f"{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "mode": mode,
            "model": "",
            "created": now,
            "updated": now,
            "messages": [],
        }
        self.turn_metadata = []
        self._exit_consolidation_started = False
        save_session_snapshot(self.session)

    def prefix(self, query: str = "") -> str:
        return self.memory.build_memory_prefix(
            query,
            allowed_modes=self.allowed_recall_modes,
        )

    def record_turn(
        self,
        user_text: str,
        assistant_text: str,
        model: str = "",
        metadata: dict = None,
    ):
        self.record_user(user_text, metadata=metadata)
        self.record_assistant(
            assistant_text,
            model=model,
            metadata=metadata,
        )

    def record_user(self, user_text: str, metadata: dict = None):
        now = datetime.now().isoformat()
        self.session["updated"] = now
        self.session["messages"].append({
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": user_text,
            "created_at": now,
            "metadata": dict(metadata or {}),
        })
        save_session_snapshot(self.session)
        self.memory.persist_live_session(self.session)

    def record_assistant(
        self,
        assistant_text: str,
        model: str = "",
        metadata: dict = None,
    ):
        now = datetime.now().isoformat()
        if model:
            self.session["model"] = model
        self.session["updated"] = now
        self.session["messages"].append({
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": assistant_text,
            "created_at": now,
            "metadata": dict(metadata or {}),
        })
        self.turn_metadata.append(dict(metadata or {}))
        user_text = next(
            (
                message.get("content", "")
                for message in reversed(self.session["messages"][:-1])
                if message.get("role") == "user"
            ),
            "",
        )
        save_session_snapshot(self.session)
        self.memory.persist_live_session(self.session)
        self.memory.auto_update_facts(user_text, assistant_text)

    def record_private(self, text: str, metadata: dict = None):
        meta = {"source_type": "manual_private", "mode": self.mode}
        if metadata:
            meta.update(metadata)
        self.memory.store_chunk(text, meta)
        self.memory.update_facts({"notes": [text[:300]]})

    def record_global(self, text: str, metadata: dict = None):
        meta = {"source_type": "manual_global", "mode": "console", "origin_mode": self.mode}
        if metadata:
            meta.update(metadata)
        console = MemoryManager("console")
        console.store_chunk(text, meta)
        console.update_facts({"notes": [text[:300]], "last_updated": datetime.now().isoformat()})

    def store(self, ollama_client=None, trigger_consolidation: bool = True):
        if self.session["messages"]:
            self.memory.store_session(self.session, ollama_client=ollama_client)
            if trigger_consolidation and not getattr(
                self, "_exit_consolidation_started", False
            ):
                self._exit_consolidation_started = trigger_exit_consolidation()

    def handle_command(self, command: str) -> bool:
        lower = command.lower().strip()
        if lower == "memory" or lower.startswith("memory set "):
            _handle_memory_cmd(command, self.memory)
            return True
        if lower == "memory global":
            _handle_memory_cmd("memory", MemoryManager("console"))
            return True
        if lower.startswith("memory share "):
            self.record_global(command[len("memory share "):].strip())
            print("  Memory shared globally.\n")
            return True
        if lower.startswith("memory private "):
            self.record_private(command[len("memory private "):].strip())
            print("  Memory saved privately.\n")
            return True
        if lower.startswith("memory recall "):
            query = command[len("memory recall "):].strip()
            hits = self.memory.recall(query, allowed_modes=self.allowed_recall_modes)
            if not hits:
                print("  No memory hits.\n")
                return True
            print("\n  Memory recall results:")
            for hit in hits:
                meta = hit.get("metadata") or {}
                mode = meta.get("mode", "unknown")
                text = str(hit.get("text", "")).replace("\n", " ")[:240]
                print(f"    [{mode}] {text}")
            print()
            return True
        if lower == "memory status":
            stats = self.memory.stats()
            print("\n  Memory status:")
            for key in (
                "primary", "backend", "local_mirror", "pending_events",
                "facts_count", "embedding_count", "last_session",
            ):
                if key in stats:
                    print(f"    {key}: {stats[key]}")
            print()
            return True
        if lower == "memory sources":
            rows = self.memory.source_counts()
            print("\n  Memory sources:")
            if not rows:
                print("    Local fallback active; Postgres source inventory unavailable.")
            for row in rows:
                print(f"    {row['mode']}/{row['source_type']}: {row['count']}")
            print()
            return True
        if lower in ("memory pending", "memory reconcile"):
            if lower == "memory reconcile":
                replayed = self.memory.reconcile_pending()
                print(f"  Reconciled {replayed} pending event(s).")
            print(f"  Pending events: {self.memory.stats().get('pending_events', 0)}\n")
            return True
        return False
