from __future__ import annotations

from datetime import datetime

from core.memory import MemoryManager, _handle_memory_cmd


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
            "name": f"{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "mode": mode,
            "model": "",
            "created": now,
            "updated": now,
            "messages": [],
        }
        self.turn_metadata = []

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
        now = datetime.now().isoformat()
        if model:
            self.session["model"] = model
        self.session["updated"] = now
        self.session["messages"].append({"role": "user", "content": user_text})
        self.session["messages"].append({"role": "assistant", "content": assistant_text})
        self.turn_metadata.append(dict(metadata or {}))
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

    def store(self, ollama_client=None):
        if self.session["messages"]:
            self.memory.store_session(self.session, ollama_client=ollama_client)

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
        return False
