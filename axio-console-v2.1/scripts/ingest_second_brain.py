#!/usr/bin/env python3
"""
Import Michael's Second Brain vault into the AXIO Cortex (Postgres).

The Postgres Cortex is the one brain; the Obsidian vault is only an import
source and is opened read-only. Every non-empty .md note (skipping .obsidian/,
.git/) is split by `## ` sections, embedded with nomic-embed-text and stored in
the `console` namespace as source_type `second_brain`, with `chunk_index`,
`section_part` and `note_mtime` in each chunk's metadata so a note can be
rebuilt in order from the DB (brain_read).

Safety:
  * Ollama is checked (a real 768-dim test embedding) BEFORE anything changes.
  * Notes are replaced one at a time, and only after every chunk of that note
    has been embedded. There is no clear-all: if Ollama dies mid-run, notes not
    yet processed keep their previous chunks.
  * Only source_type `second_brain` is touched; self_learned, memory_seed,
    exemplar, session summaries and facts are never modified.
  * Holds the self-memory single-writer lock, so it never races the scheduled
    AXIO Memory Sync, and records note mtimes in the runtime state so that sync
    does not redo the work.

Usage (from axio-console-v2.1, with the Cortex container and Ollama up):
    .venv\\Scripts\\python.exe scripts/ingest_second_brain.py
    .venv\\Scripts\\python.exe scripts/ingest_second_brain.py "D:/other/vault"
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("AXIO_MEMORY_BACKEND", "postgres")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import memory_runtime as runtime  # noqa: E402
from core.config import (  # noqa: E402
    SECOND_BRAIN_NAMESPACE,
    SECOND_BRAIN_SOURCE_TYPE,
    SECOND_BRAIN_VAULT,
)
from core.memory import MemoryManager  # noqa: E402
from core.self_memory import SingleInstanceLock  # noqa: E402


def main() -> int:
    vault = Path(sys.argv[1]) if len(sys.argv) > 1 else SECOND_BRAIN_VAULT
    if not vault.exists():
        print(f"Vault not found: {vault}")
        return 1

    mgr = MemoryManager(SECOND_BRAIN_NAMESPACE)
    if not mgr._postgres_backend:
        print("ABORT: Postgres backend not active. Start the Cortex container and "
              "set AXIO_MEMORY_BACKEND=postgres. Nothing was changed.")
        return 1
    try:
        mgr._postgres_backend.healthcheck()
    except Exception as exc:
        print(f"ABORT: Postgres Cortex unavailable ({exc}). Nothing was changed.")
        return 1

    probe = mgr.embed_text("AXIO Second Brain import probe")
    if not probe or len(probe) != 768:
        print("ABORT: Ollama embeddings unavailable (nomic-embed-text, 768-dim). "
              "Start Ollama and re-run. Nothing was changed.")
        return 1

    lock = SingleInstanceLock()
    if not lock.acquire():
        print("ABORT: another Cortex writer (memory runtime) holds the lock. "
              "Re-run when it finishes. Nothing was changed.")
        return 1
    try:
        return _import(mgr, vault)
    finally:
        lock.release()


def _import(mgr: MemoryManager, vault: Path) -> int:
    notes = list(runtime.iter_vault_notes(vault))
    use_state = vault.resolve() == Path(runtime.VAULT).resolve()
    state = runtime._load_state() if use_state else None
    files = state.setdefault("files", {}) if state is not None else {}

    stored = ok = failed = 0
    for path, rel in notes:
        try:
            n = runtime._ingest(mgr, path, SECOND_BRAIN_SOURCE_TYPE, "path", rel, rel, "Second Brain")
        except Exception as exc:
            failed += 1
            print(f"  ! {rel}: not replaced, previous chunks kept ({exc})")
            continue
        ok += 1
        stored += n
        files["brain::" + rel] = path.stat().st_mtime
        print(f"  imported {rel} ({n} chunks)")

    # Notes deleted from the vault: drop their chunks (note by note).
    vault_rels = {rel for _path, rel in notes}
    removed = 0
    for row in mgr._postgres_backend.list_chunks(SECOND_BRAIN_SOURCE_TYPE, limit=100000):
        rel = (row.get("metadata") or {}).get("path")
        if rel and rel not in vault_rels:
            mgr.delete_chunks(SECOND_BRAIN_SOURCE_TYPE, "path", rel)
            vault_rels.add(rel)  # delete each orphan path once
            files.pop("brain::" + rel, None)
            removed += 1
            print(f"  removed {rel} (no longer in vault)")

    if state is not None:
        runtime._save_state(state)

    print(f"\nImported {ok}/{len(notes)} notes -> {stored} chunks; "
          f"{failed} failed (kept previous version); {removed} removed.")
    print(f"Stats ({SECOND_BRAIN_NAMESPACE}):", mgr.stats())
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
