#!/usr/bin/env python3
"""Bootstrap/update the local Chroma mirror from canonical Postgres vectors."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.memory import MemoryManager, VALID_MODES  # noqa: E402
from core.memory_backends.postgres_backend import PostgresMemoryBackend  # noqa: E402


def _embedding_list(value):
    if hasattr(value, "to_list"):
        return value.to_list()
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def _metadata(value, mode: str) -> dict:
    raw = dict(value or {})
    raw.setdefault("mode", mode)
    return {
        str(key): val if isinstance(val, (str, int, float, bool)) else str(val)
        for key, val in raw.items()
        if val is not None
    }


def main() -> int:
    source = PostgresMemoryBackend("console")
    rows = source.all_embeddings()
    managers = {mode: MemoryManager(mode) for mode in VALID_MODES}
    mirrored = 0
    pruned = 0
    for mode in VALID_MODES:
        manager = managers[mode]
        collection = manager._chroma
        if not collection:
            continue
        mode_rows = [row for row in rows if row["mode"] == mode]
        pg_ids = {str(row["id"]) for row in mode_rows}

        # Prune vectors that no longer exist in Postgres (a row deleted upstream
        # must not linger in the local mirror -- otherwise "rebuild" is a lie and
        # the Chroma<->Postgres parity check can never reach true parity).
        try:
            existing = set(collection.get(include=[]).get("ids", []))
        except Exception:
            existing = set()
        stale = list(existing - pg_ids)
        if stale:
            collection.delete(ids=stale)
            pruned += len(stale)

        for start in range(0, len(mode_rows), 100):
            batch = mode_rows[start:start + 100]
            collection.upsert(
                ids=[str(row["id"]) for row in batch],
                documents=[row["content"] for row in batch],
                embeddings=[_embedding_list(row["embedding"]) for row in batch],
                metadatas=[_metadata(row["metadata"], mode) for row in batch],
            )
            mirrored += len(batch)
    counts = {
        mode: managers[mode]._chroma.count() if managers[mode]._chroma else 0
        for mode in VALID_MODES
    }
    print(f"Postgres embeddings: {len(rows)}")
    print(f"Mirrored rows: {mirrored}")
    print(f"Pruned stale rows: {pruned}")
    print(f"Chroma counts: {counts}")
    return 0 if mirrored == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
