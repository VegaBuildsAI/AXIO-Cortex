#!/usr/bin/env python3
"""Read-only report for AXIO's continuous self-memory."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("AXIO_MEMORY_BACKEND", "postgres")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.memory_backends.postgres_backend import PostgresMemoryBackend  # noqa: E402


def _metadata(row: dict) -> dict:
    value = row.get("metadata") or {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return dict(value)


def build_report(redact_content: bool = False) -> dict:
    backend = PostgresMemoryBackend("console")
    lessons = backend.list_chunks("self_learned", limit=5000)
    facts = backend.get_facts()
    ranked = sorted(
        lessons,
        key=lambda row: int(_metadata(row).get("reinforced_count", 1)),
        reverse=True,
    )

    def item(row: dict) -> dict:
        meta = _metadata(row)
        result = {
            "id": str(row["id"]),
            "reinforced_count": int(meta.get("reinforced_count", 1)),
            "confidence": float(meta.get("confidence", 0.0)),
            "last_seen": meta.get("last_seen"),
            "promoted": bool(meta.get("promoted")),
        }
        result["content"] = "[redacted]" if redact_content else str(row["content"])
        return result

    supersessions = []
    for row in lessons:
        meta = _metadata(row)
        if meta.get("superseded_by"):
            supersessions.append({
                "id": str(row["id"]),
                "superseded_by": str(meta["superseded_by"]),
                "superseded_at": meta.get("superseded_at"),
            })
    supersessions.sort(key=lambda row: str(row.get("superseded_at", "")), reverse=True)

    return {
        "self_learned_total": len(lessons),
        "promoted_facts": len(facts.get("learned_principles", [])),
        "source_counts": backend.source_counts(),
        "store_content_chars": sum(len(str(row["content"])) for row in lessons),
        "top_reinforced": [item(row) for row in ranked[:10]],
        "recent_supersessions": supersessions[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only AXIO self-memory report")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--redact-content", action="store_true",
        help="show metrics and IDs without printing private lesson text",
    )
    args = parser.parse_args()
    report = build_report(redact_content=args.redact_content)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0

    print("AXIO Self-Memory Report")
    print(f"self_learned: {report['self_learned_total']}")
    print(f"promoted facts: {report['promoted_facts']}")
    print(f"derived content size: {report['store_content_chars']} chars")
    print("top reinforced:")
    for row in report["top_reinforced"]:
        print(
            f"  {row['id']} count={row['reinforced_count']} "
            f"confidence={row['confidence']:.2f} promoted={row['promoted']} "
            f"content={row['content']}"
        )
    print(f"recent supersessions: {len(report['recent_supersessions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
