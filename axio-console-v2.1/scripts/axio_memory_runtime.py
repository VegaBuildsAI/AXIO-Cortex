#!/usr/bin/env python3
"""
Run the AXIO memory runtime: automatic knowledge ingestion + self-consolidation.

  py scripts/axio_memory_runtime.py                    # loop (Ctrl-C to stop)
  py scripts/axio_memory_runtime.py --once             # single pass and exit
  py scripts/axio_memory_runtime.py --interval 30      # cycle every 30s
  py scripts/axio_memory_runtime.py --consolidate-every 10
  py scripts/axio_memory_runtime.py --dry-run           # preview; writes nothing
  py scripts/axio_memory_runtime.py --reflect-only      # forced deep reflection

Each cycle: (1) re-indexes changed AXIO seed docs + Second Brain files, and
(2) every N cycles, consolidates recent sessions into self-learned memory using
the local model. Requires the axio-cortex-postgres container + Ollama.
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("AXIO_MEMORY_BACKEND", "postgres")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import memory_runtime  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="AXIO memory runtime")
    ap.add_argument("--once", action="store_true", help="run a single pass and exit")
    ap.add_argument("--interval", type=int, default=60,
                    help="seconds between cycles (default 60)")
    ap.add_argument("--consolidate-every", type=int, default=None,
                    help="run self-consolidation every N cycles (config default)")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--sync-only", action="store_true",
                    help="only re-index files; skip consolidation (light/frequent)")
    modes.add_argument("--consolidate-only", action="store_true",
                    help="only consolidate sessions; skip file sync (heavier/rare)")
    modes.add_argument("--reflect-only", action="store_true",
                    help="force one reflection/decay/compaction pass")
    ap.add_argument("--dry-run", action="store_true",
                    help="preview one pass without state, outbox, DB, Chroma, or log writes")
    args = ap.parse_args()
    return memory_runtime.run(
        interval=args.interval,
        consolidate_every=args.consolidate_every,
        once=args.once or args.dry_run or args.reflect_only,
        do_sync=not (args.consolidate_only or args.reflect_only),
        do_consolidate=not (args.sync_only or args.reflect_only),
        do_reflect=not args.sync_only,
        force_reflect=args.reflect_only,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
