#!/usr/bin/env python3
"""
Seed AXIO Cortex living memory from a Markdown file.

Splits the file by `## ` headings and stores each section as an embedded chunk in
a target memory namespace, plus structured facts. Requires the Postgres backend.

Usage (from axio-console-v2.1):
    py scripts/seed_cortex_memory.py                         # identity seed -> console
    py scripts/seed_cortex_memory.py AXIO_CORTEX_MEMORY.md console
    py scripts/seed_cortex_memory.py AXIO_CODE_PLAYBOOK.md  code

The target mode defaults to `console` (the cross-mode master namespace). Use a
specific mode (e.g. `code`) to seed that mode's own skill/playbook. Identity
facts are written only when seeding into `console`, preserving the identity seed.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("AXIO_MEMORY_BACKEND", "postgres")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.memory import MemoryManager, VALID_MODES  # noqa: E402


def split_sections(md: str) -> list[tuple[str, str]]:
    """Return (heading, body) pairs for each `## ` section."""
    parts = re.split(r"^##\s+", md, flags=re.MULTILINE)
    sections = []
    for chunk in parts[1:]:
        lines = chunk.splitlines()
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if body:
            sections.append((heading, body))
    return sections


def main() -> int:
    args = [a for a in sys.argv[1:]]
    path = Path(args[0]) if args else ROOT / "AXIO_CORTEX_MEMORY.md"
    target_mode = (args[1] if len(args) > 1 else "console").strip().lower()

    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"File not found: {path}")
        return 1
    if target_mode not in VALID_MODES:
        print(f"Invalid target mode {target_mode!r}; valid: {VALID_MODES}")
        return 1

    md = path.read_text(encoding="utf-8")
    sections = split_sections(md)
    print(f"Loaded {len(sections)} section(s) from {path.name} -> mode '{target_mode}'")

    mgr = MemoryManager(target_mode)
    if not mgr._postgres_backend:
        print("WARNING: Postgres backend not active; set AXIO_MEMORY_BACKEND=postgres")

    stored = 0
    for heading, body in sections:
        text = f"AXIO Cortex memory [{target_mode}] — {heading}:\n{body}"
        mgr.store_chunk(text, metadata={
            "source_type": "memory_seed", "title": heading, "doc": path.name,
        })
        print(f"  stored chunk: {heading}")
        stored += 1

    # A short note so a mode prefix references the seeded doc.
    mgr.update_facts({"notes": [f"Seeded skill/memory from {path.name} ({stored} sections)."]})

    # Identity facts only when seeding the identity doc into the console master.
    if target_mode == "console":
        MemoryManager("chat").update_facts({
            "user_name": "Michael",
            "preferred_language": "Spanish",
            "preferred_tone": "concise, direct, technically precise",
            "key_projects": ["AXIO", "AXIO Cortex", "IOAF"],
            "notes": ["Michael is the creator/architect of AXIO; building AXIO Cortex living memory."],
        })
        mgr.update_facts({
            "cross_mode_entities": ["Michael", "AXIO", "AXIO Cortex", "IOAF", "VegaBuildsAI/AXIO-Cortex"],
            "global_preferences": {
                "language": "Spanish",
                "validation": "real end-to-end, nothing undone",
                "workflow": "incremental, clean git hygiene, local-first",
            },
        })

    print(f"\nSeeded {stored} chunks into AXIO Cortex (mode '{target_mode}').")
    print(f"Stats ({target_mode}):", mgr.stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
