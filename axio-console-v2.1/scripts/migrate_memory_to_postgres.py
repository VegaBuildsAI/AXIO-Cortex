#!/usr/bin/env python3
"""
Import existing AXIO JSON memory files into the Postgres backend.

Run from axio-console-v2.1:
    py scripts/migrate_memory_to_postgres.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import MEMORY_DIR
from core.memory import VALID_MODES
from core.memory_backends.postgres_backend import PostgresMemoryBackend


def import_facts() -> int:
    imported = 0
    for mode in VALID_MODES:
        path = MEMORY_DIR / f"{mode}_memory.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        backend = PostgresMemoryBackend(mode)
        backend.update_facts(data)
        imported += 1
        print(f"Imported facts: {path}")
    return imported


def main() -> int:
    count = import_facts()
    print(f"Imported {count} memory fact file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
