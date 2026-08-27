#!/usr/bin/env python3
"""
Index Michael's Second Brain vault into AXIO Cortex for immediate recall.

Walks every .md file, splits large notes by `## ` sections (further splitting
oversized bodies), embeds each chunk with nomic-embed-text, and stores it in the
`console` memory namespace so EVERY mode (chat/cowork/code) recalls it via RAG.

Re-runnable / idempotent: deletes previous `second_brain` chunks before
re-indexing, so you just run it again after editing your vault.

Usage (from axio-console-v2.1, with the Postgres Cortex container up):
    py scripts/ingest_second_brain.py
    py scripts/ingest_second_brain.py "C:/Users/AXIO/Documents/Second Brain"
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

from core.memory import MemoryManager   # noqa: E402
from core.db import connect             # noqa: E402

DEFAULT_VAULT = Path(r"C:\Users\AXIO\Documents\Second Brain")
TARGET_MODE = "console"     # cross-mode master namespace -> all modes recall it
SOURCE_TYPE = "second_brain"
MAX_CHARS = 4000            # ~1k tokens per chunk keeps embeddings focused


def chunks_for_file(text: str, rel: str, stem: str):
    """Yield (heading, body) chunks for one markdown file."""
    text = text.strip()
    if not text:
        return
    raw = []
    if re.search(r"^##\s+", text, flags=re.MULTILINE):
        parts = re.split(r"^##\s+", text, flags=re.MULTILINE)
        preamble = parts[0].strip()
        if preamble:
            raw.append(("(intro)", preamble))
        for chunk in parts[1:]:
            lines = chunk.splitlines()
            heading = lines[0].strip() if lines else ""
            body = "\n".join(lines[1:]).strip()
            if body:
                raw.append((heading, body))
    else:
        raw.append((stem, text))

    for heading, body in raw:
        if len(body) <= MAX_CHARS:
            yield heading, body
        else:
            for i in range(0, len(body), MAX_CHARS):
                yield heading, body[i:i + MAX_CHARS]


def main() -> int:
    vault = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VAULT
    if not vault.exists():
        print(f"Vault not found: {vault}")
        return 1

    mgr = MemoryManager(TARGET_MODE)
    if not mgr._postgres_backend:
        print("WARNING: Postgres backend not active. Start the Cortex container and "
              "set AXIO_MEMORY_BACKEND=postgres, then re-run.")
        return 1

    # Idempotent: clear previous Second Brain chunks before re-indexing.
    with connect() as conn:
        conn.execute(
            "DELETE FROM memory_embeddings WHERE mode = %s AND source_type = %s",
            (TARGET_MODE, SOURCE_TYPE),
        )
        conn.commit()
    print(f"Cleared previous '{SOURCE_TYPE}' chunks from namespace '{TARGET_MODE}'.")

    files = sorted(vault.rglob("*.md"))
    stored = 0
    skipped = 0
    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped += 1
            continue
        rel = path.relative_to(vault).as_posix()
        for heading, body in chunks_for_file(content, rel, path.stem):
            text = f"[Second Brain] {rel} — {heading}:\n{body}"
            try:
                mgr.store_chunk(text, metadata={
                    "source_type": SOURCE_TYPE, "path": rel, "title": heading,
                })
                stored += 1
            except Exception as exc:   # keep going on a single bad chunk
                skipped += 1
                print(f"  ! skip {rel} [{heading}]: {exc}")

    mgr.update_facts({"notes": [
        f"Second Brain vault indexed for recall: {len(files)} files -> {stored} chunks "
        f"(source '{SOURCE_TYPE}', namespace '{TARGET_MODE}')."
    ]})

    print(f"\nIndexed {stored} chunks from {len(files)} files (skipped {skipped}).")
    print(f"Stats ({TARGET_MODE}):", mgr.stats())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
