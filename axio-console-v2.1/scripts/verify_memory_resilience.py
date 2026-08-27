#!/usr/bin/env python3
"""Read-only health check for the live AXIO Cortex memory path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AXIO_DATA_ROOT, CHROMA_DIR  # noqa: E402
from core.memory import MemoryManager, VALID_MODES  # noqa: E402
from core.memory_durability import pending_count  # noqa: E402
from core.mode_memory import shared_recall_modes  # noqa: E402


def main() -> int:
    # Cover EVERY mode (incl. revrec) so the Chroma<->Postgres parity check is
    # meaningful: source_counts() spans all modes, so omitting revrec here made
    # the check a guaranteed false FAIL once any revrec vector existed.
    managers = {mode: MemoryManager(mode) for mode in VALID_MODES}
    console = managers["console"]
    profile = console.get_facts().get("global_profile", {})
    prefix = managers["cowork"].build_memory_prefix(
        "quien soy yo y que data tienes almacenada?",
        allowed_modes=shared_recall_modes("cowork"),
    )

    # Per-mode counts on both sides (Chroma keeps one collection per mode).
    pg_by_mode: dict[str, int] = {}
    for row in console.source_counts():
        pg_by_mode[row["mode"]] = pg_by_mode.get(row["mode"], 0) + int(row["count"])
    chroma_by_mode = {
        mode: (manager._chroma.count() if manager._chroma else 0)
        for mode, manager in managers.items()
    }
    pg_total = sum(pg_by_mode.values())
    chroma_total = sum(chroma_by_mode.values())

    all_modes = sorted(set(pg_by_mode) | set(chroma_by_mode))
    mode_mismatches = {
        mode: (pg_by_mode.get(mode, 0), chroma_by_mode.get(mode, 0))
        for mode in all_modes
        if pg_by_mode.get(mode, 0) != chroma_by_mode.get(mode, 0)
    }

    checks = {
        "data_root_is_unified": AXIO_DATA_ROOT == Path.home() / ".axio",
        "postgres_is_primary": all(manager.stats().get("primary") == "postgres" for manager in managers.values()),
        "global_profile_present": profile.get("user_name") == "Michael",
        "cowork_receives_profile": "User name: Michael" in prefix,
        "shared_modes_include_console": "console" in shared_recall_modes("cowork"),
        "outbox_drained": pending_count() == 0,
        "chroma_matches_postgres_total": chroma_total == pg_total,
        "chroma_matches_postgres_per_mode": not mode_mismatches,
    }
    print(f"AXIO_DATA_ROOT={AXIO_DATA_ROOT}")
    print(f"CHROMA_DIR={CHROMA_DIR}")
    print(f"Postgres embeddings per mode={pg_by_mode} (total {pg_total})")
    print(f"Chroma counts per mode={chroma_by_mode} (total {chroma_total})")
    if mode_mismatches:
        print(f"Per-mode mismatches (postgres, chroma)={mode_mismatches}")
    print(f"Pending events={pending_count()}")
    for name, passed in checks.items():
        print(f"{name}={'PASS' if passed else 'FAIL'}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
