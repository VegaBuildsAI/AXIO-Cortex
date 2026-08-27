#!/usr/bin/env python3
"""Idempotent migration to the resilient AXIO Cortex memory layout.

This does not delete legacy data.  It establishes the global profile in the
console namespace and copies only missing legacy JSON session/fact files from
the former project-local .axio-data root into C:\\Users\\AXIO\\.axio.  The
legacy Chroma directory is deliberately retained; the exact Postgres mirror is
rebuilt separately in ``chroma-resilient``.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AXIO_DATA_ROOT  # noqa: E402
from core.memory import MemoryManager  # noqa: E402


GLOBAL_PROFILE = {
    "user_name": "Michael",
    "preferred_language": "Spanish",
    "preferred_tone": "concise, direct, technically precise",
    "key_projects": ["AXIO", "AXIO Cortex", "IOAF"],
}


def copy_missing_legacy_files() -> int:
    legacy = ROOT / ".axio-data"
    copied = 0
    if not legacy.exists() or legacy.resolve() == AXIO_DATA_ROOT.resolve():
        return 0
    for directory in ("memory", "sessions", "ui"):
        source = legacy / directory
        destination = AXIO_DATA_ROOT / directory
        if not source.exists():
            continue
        destination.mkdir(parents=True, exist_ok=True)
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            target = destination / path.relative_to(source)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
    return copied


def main() -> int:
    if AXIO_DATA_ROOT != Path.home() / ".axio":
        print(f"Refusing migration: AXIO_DATA_ROOT is {AXIO_DATA_ROOT}, expected {Path.home() / '.axio'}")
        return 1
    copied = copy_missing_legacy_files()
    console = MemoryManager("console")
    console.update_facts({"global_profile": GLOBAL_PROFILE})
    replayed = console.reconcile_pending()
    print(f"AXIO_DATA_ROOT={AXIO_DATA_ROOT}")
    print(f"Copied missing legacy files: {copied}")
    print(f"Replayed pending events: {replayed}")
    print(f"Pending events: {console.stats().get('pending_events', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
