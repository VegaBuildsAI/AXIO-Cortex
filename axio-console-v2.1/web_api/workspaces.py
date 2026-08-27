from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from pathlib import Path

from core.config import MAX_FILE_BYTES, TEXT_EXTENSIONS


BLOCKED_NAMES = {".env", ".git", "__pycache__", "node_modules", ".venv", "venv"}


class WorkspaceRegistry:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._items = self._load()

    def _load(self) -> dict[str, dict]:
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        pending = self.state_file.with_suffix(".tmp")
        pending.write_text(
            json.dumps(self._items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        pending.replace(self.state_file)

    def open(self, path: str) -> dict:
        root = Path(path).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Workspace path must be a directory.")
        with self._lock:
            for item in self._items.values():
                if Path(item["path"]) == root:
                    return item
            workspace = {
                "id": str(uuid.uuid4()),
                "name": root.name,
                "path": str(root),
            }
            self._items[workspace["id"]] = workspace
            self._save()
            return workspace

    def list(self) -> list[dict]:
        return list(self._items.values())

    def get(self, workspace_id: str) -> dict:
        workspace = self._items.get(workspace_id)
        if not workspace:
            raise KeyError(workspace_id)
        return workspace

    def _root(self, workspace_id: str) -> Path:
        return Path(self.get(workspace_id)["path"]).resolve(strict=True)

    def _file_id(self, workspace_id: str, relative: str) -> str:
        digest = hashlib.sha256(f"{workspace_id}:{relative}".encode()).hexdigest()
        return digest[:24]

    def _is_allowed(self, path: Path) -> bool:
        return (
            path.suffix.lower() in TEXT_EXTENSIONS
            and not any(part in BLOCKED_NAMES for part in path.parts)
        )

    def resolve(self, workspace_id: str, relative: str, must_exist: bool = True) -> Path:
        root = self._root(workspace_id)
        candidate = (root / relative).resolve(strict=must_exist)
        if os.path.commonpath([str(root), str(candidate)]) != str(root):
            raise ValueError("Path escapes the active workspace.")
        if candidate.name == ".env" or any(part in BLOCKED_NAMES for part in candidate.parts):
            raise ValueError("Protected path.")
        return candidate

    def files(self, workspace_id: str, limit: int = 400) -> list[dict]:
        root = self._root(workspace_id)
        results = []
        for path in sorted(root.rglob("*")):
            if len(results) >= limit:
                break
            if not path.is_file() or not self._is_allowed(path):
                continue
            relative = path.relative_to(root).as_posix()
            results.append(
                {
                    "id": self._file_id(workspace_id, relative),
                    "name": path.name,
                    "relative_path": relative,
                    "size": path.stat().st_size,
                }
            )
        return results

    def resolve_file_id(self, workspace_id: str, file_id: str) -> tuple[Path, str]:
        for item in self.files(workspace_id):
            if item["id"] == file_id:
                return self.resolve(workspace_id, item["relative_path"]), item["relative_path"]
        raise KeyError(file_id)

    def read_file(self, workspace_id: str, file_id: str) -> dict:
        path, relative = self.resolve_file_id(workspace_id, file_id)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"File exceeds {MAX_FILE_BYTES:,} bytes.")
        return {
            "id": file_id,
            "name": path.name,
            "relative_path": relative,
            "content": path.read_text(encoding="utf-8", errors="replace"),
        }

