#!/usr/bin/env python3
"""
Seed AXIO Cortex living memory from a Markdown file.

Splits the file by `## ` headings and stores each section as an embedded chunk
in the `console` master namespace (semantic, cross-mode recall), plus a few
structured facts in `chat`/`console`. Requires the Postgres backend.

Run from axio-console-v2.1:
    py scripts/seed_cortex_memory.py [path/to/file.md]
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

from core.memory import MemoryManager  # noqa: E402


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
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "AXIO_CORTEX_MEMORY.md"
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    md = path.read_text(encoding="utf-8")
    sections = split_sections(md)
    print(f"Loaded {len(sections)} section(s) from {path.name}")

    console = MemoryManager("console")
    if not console._postgres_backend:
        print("WARNING: Postgres backend not active; set AXIO_MEMORY_BACKEND=postgres")

    stored = 0
    for heading, body in sections:
        text = f"AXIO Cortex memory — {heading}:\n{body}"
        console.store_chunk(text, metadata={"source_type": "memory_seed", "title": heading})
        print(f"  stored chunk: {heading}")
        stored += 1

    # Structured facts so a mode prefix surfaces identity immediately.
    chat = MemoryManager("chat")
    chat.update_facts({
        "user_name": "Michael",
        "preferred_language": "Spanish",
        "preferred_tone": "concise, direct, technically precise",
        "key_projects": ["AXIO", "AXIO Cortex", "IOAF"],
        "notes": ["Michael is the creator/architect of AXIO; building AXIO Cortex living memory."],
    })
    console.update_facts({
        "cross_mode_entities": ["Michael", "AXIO", "AXIO Cortex", "IOAF", "VegaBuildsAI/AXIO-Cortex"],
        "global_preferences": {
            "language": "Spanish",
            "validation": "real end-to-end, nothing undone",
            "workflow": "incremental, clean git hygiene, local-first",
        },
        "notes": ["Seeded from AXIO_CORTEX_MEMORY.md — who Michael is, what AXIO is, how it works."],
    })

    print(f"\nSeeded {stored} memory chunks + identity facts into AXIO Cortex (console).")
    print("Stats (console):", console.stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
