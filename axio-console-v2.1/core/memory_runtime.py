"""
AXIO Memory Runtime — automatic knowledge ingestion + self-consolidation loop.

Two jobs run each cycle:

  1) SYNC  — incrementally re-index changed knowledge files (the AXIO seed docs
             + the Second Brain vault) by mtime, so recall always has current
             context. Only changed/added/removed files are touched.

  2) LEARN — consolidation: review recent sessions the platform itself produced,
             distill durable lessons with the LOCAL model, and store them back as
             memory. This is the model "learning from itself" — continual RAG
             memory, not weight retraining.

Run via scripts/axio_memory_runtime.py:
    py scripts/axio_memory_runtime.py            # loop (Ctrl-C to stop)
    py scripts/axio_memory_runtime.py --once     # single pass and exit
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from .config import (
    AXIO_DATA_ROOT,
    MODELS,
    SECOND_BRAIN_NAMESPACE,
    SECOND_BRAIN_SKIP_DIRS,
    SECOND_BRAIN_SOURCE_TYPE,
    SECOND_BRAIN_VAULT,
)
from .db import connect
from .logger import AuditLogger
from .memory import MemoryManager
from .memory_durability import atomic_write_json, pending_count
from .models import OllamaClient
from .self_memory import (
    SelfMemoryEngine,
    SingleInstanceLock,
    load_self_memory_config,
    resource_gate_reasons,
)

ROOT = Path(__file__).resolve().parents[1]
VAULT = SECOND_BRAIN_VAULT  # read-only import source; see core/config.py
# Canonical AXIO knowledge docs — kept in sync in the Cortex (Docker Postgres).
SEED_DOCS = [
    ROOT / "AXIO_CORTEX_MEMORY.md",              # identity + hybrid architecture
    ROOT / "AXIO_AI_WORKFLOW.md",                # tools / skills / MCP / tool-calling
    ROOT / "AXIO_IOAF_TechSpec_v2.1.md",         # technical spec (console implementation)
    ROOT / "AXIO_IOAF_Manifesto_v2.1.md",        # IOAF vision / manifesto
    ROOT.parent / "AXIO_CONSOLE_UI_IMPLEMENTATION_PLAN.md",  # console UI implementation plan
]
TARGET_MODE = "console"
STATE_FILE = AXIO_DATA_ROOT / "memory_runtime_state.json"
MAX_CHARS = 4000
MIRROR_VERSION = 2  # Postgres + local Chroma write-through format


# ── state ────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"files": {}, "consolidate_watermark": None}


def _save_state(state: dict) -> None:
    atomic_write_json(STATE_FILE, state)


# ── chunking ─────────────────────────────────────────────────────────────
def _split_sections_parts(text: str, stem: str):
    """Return (heading, body, section_part) chunks; part>0 = continuation slice."""
    text = text.strip()
    if not text:
        return []
    raw = []
    if re.search(r"^##\s+", text, flags=re.MULTILINE):
        parts = re.split(r"^##\s+", text, flags=re.MULTILINE)
        if parts[0].strip():
            raw.append(("(intro)", parts[0].strip()))
        for chunk in parts[1:]:
            lines = chunk.splitlines()
            heading = lines[0].strip() if lines else ""
            body = "\n".join(lines[1:]).strip()
            if body:
                raw.append((heading, body))
    else:
        raw.append((stem, text))
    out = []
    for heading, body in raw:
        if len(body) <= MAX_CHARS:
            out.append((heading, body, 0))
        else:
            for part, i in enumerate(range(0, len(body), MAX_CHARS)):
                out.append((heading, body[i:i + MAX_CHARS], part))
    return out


def _split_sections(text: str, stem: str):
    return [(heading, body) for heading, body, _part in _split_sections_parts(text, stem)]


def iter_vault_notes(vault: Path = None):
    """Yield (path, rel) for every non-empty note, skipping .obsidian/.git.

    The vault is only read here; nothing in AXIO writes to it.
    """
    vault = Path(vault or VAULT)
    if not vault.exists():
        return
    for path in sorted(vault.rglob("*.md")):
        rel_parts = path.relative_to(vault).parts
        if any(part in SECOND_BRAIN_SKIP_DIRS for part in rel_parts[:-1]):
            continue
        try:
            if not path.is_file() or path.stat().st_size == 0:
                continue
        except OSError:
            continue
        yield path, path.relative_to(vault).as_posix()


def _delete_chunks(mgr: MemoryManager, source_type: str, key: str, value: str) -> None:
    """Delete the prior Postgres row(s) and their local Chroma mirror."""
    mgr.delete_chunks(source_type, key, value)


class EmbeddingUnavailable(RuntimeError):
    """Raised before any delete when a note cannot be fully embedded."""


def _ingest(mgr, path: Path, source_type: str, del_key: str, del_val: str,
            path_meta: str, label: str) -> int:
    """Replace one file's chunks: embed every section FIRST, then swap.

    If any embedding fails (Ollama down/mid-restart) nothing is deleted, so the
    previous version of the note stays recallable and the next cycle retries.
    Each chunk records its `chunk_index` (order within the note), its
    `section_part` (continuation slice of an oversized section) and the file's
    `note_mtime`, so brain_read can rebuild the note from Postgres alone.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    note_mtime = path.stat().st_mtime
    prepared = []
    for index, (heading, body, part) in enumerate(_split_sections_parts(text, path.stem)):
        chunk_text = f"[{label}] {path_meta} — {heading}:\n{body}"
        embedding = mgr.embed_text(chunk_text)
        if not embedding:
            raise EmbeddingUnavailable(f"embedding unavailable for {path_meta} [{heading}]")
        prepared.append((chunk_text, embedding, {
            "source_type": source_type, "doc": path.name, "path": path_meta,
            "title": heading, "chunk_index": index, "section_part": part,
            "note_mtime": note_mtime,
        }))
    _delete_chunks(mgr, source_type, del_key, del_val)
    for chunk_text, embedding, metadata in prepared:
        mgr.store_chunk(chunk_text, metadata=metadata, embedding=embedding)
    return len(prepared)


# ── job 1: file sync ─────────────────────────────────────────────────────
def _bootstrap(state: dict, log) -> None:
    """Record current mtimes without re-embedding (index already exists)."""
    files = state["files"]
    for doc in SEED_DOCS:
        if doc.exists():
            files["seed::" + doc.name] = doc.stat().st_mtime
    for p, rel in iter_vault_notes():
        files["brain::" + rel] = p.stat().st_mtime
    log("  bootstrapped state from existing index (no re-embed needed)")


def sync_files(mgr, state: dict, log) -> int:
    files = state.setdefault("files", {})

    seed_changed = [d for d in SEED_DOCS
                    if d.exists() and files.get("seed::" + d.name) != d.stat().st_mtime]
    vault_changed = []
    seen = set()
    for p, rel in iter_vault_notes():
        seen.add("brain::" + rel)
        if files.get("brain::" + rel) != p.stat().st_mtime:
            vault_changed.append((p, rel))
    removed = [k for k in files if k.startswith("brain::") and k not in seen]

    if not (seed_changed or vault_changed or removed):
        return 0

    # Embeddings need Ollama. If it's down, skip WITHOUT touching state or
    # deleting anything, so we retry cleanly next cycle (no data loss).
    if (seed_changed or vault_changed) and not OllamaClient().is_running():
        log(
            "  SYNC SKIPPED: Ollama offline — "
            f"{len(vault_changed)} Second Brain note(s), {len(seed_changed)} seed doc(s) "
            f"and {len(removed)} removal(s) pending; the brain stays stale until "
            "Ollama is running (will retry next cycle)"
        )
        return 0

    changed = 0
    failed = 0
    for doc in seed_changed:
        try:
            n = _ingest(mgr, doc, "memory_seed", "doc", doc.name, doc.name, "AXIO")
        except Exception as exc:
            failed += 1
            log(f"  ! seed {doc.name} not synced (kept previous chunks): {exc}")
            continue
        files["seed::" + doc.name] = doc.stat().st_mtime
        changed += 1
        log(f"  synced seed {doc.name} ({n} chunks)")
    for p, rel in vault_changed:
        try:
            n = _ingest(mgr, p, SECOND_BRAIN_SOURCE_TYPE, "path", rel, rel, "Second Brain")
        except Exception as exc:
            failed += 1
            log(f"  ! brain {rel} not synced (kept previous chunks): {exc}")
            continue
        files["brain::" + rel] = p.stat().st_mtime
        changed += 1
        log(f"  synced brain {rel} ({n} chunks)")
    for key in removed:
        rel = key[len("brain::"):]
        _delete_chunks(mgr, SECOND_BRAIN_SOURCE_TYPE, "path", rel)
        del files[key]
        changed += 1
        log(f"  removed brain {rel}")
    if failed:
        log(f"  {failed} file(s) left pending; will retry next cycle")

    return changed


def brain_status(vault: Path = None) -> dict:
    """Read-only comparison of the vault (import source) against Postgres.

    Returns notes in vault vs imported, stale notes (missing, edited since
    import, or imported before chunk_index existed), orphaned DB notes,
    per-source chunk counts for the shared namespaces and last import time.
    """
    vault_notes = {rel: p.stat().st_mtime for p, rel in iter_vault_notes(vault)}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT metadata->>'path' AS path,
                   max((metadata->>'note_mtime')::float8) AS note_mtime,
                   bool_and(metadata ? 'chunk_index') AS indexed,
                   max(metadata->>'ts') AS imported_at,
                   count(*) AS chunks
            FROM memory_embeddings
            WHERE mode = %s AND source_type = %s
            GROUP BY 1
            """,
            (SECOND_BRAIN_NAMESPACE, SECOND_BRAIN_SOURCE_TYPE),
        ).fetchall()
        counts = conn.execute(
            """
            SELECT mode, source_type, count(*) AS count
            FROM memory_embeddings
            WHERE mode <> 'revrec'
            GROUP BY 1, 2 ORDER BY 1, 2
            """
        ).fetchall()
    imported = {row["path"]: row for row in rows if row["path"]}
    stale = []
    for rel, mtime in vault_notes.items():
        row = imported.get(rel)
        if row is None:
            stale.append((rel, "not imported"))
        elif not row["indexed"] or row["note_mtime"] is None:
            stale.append((rel, "no chunk_index (pre-upgrade import)"))
        elif abs(float(row["note_mtime"]) - mtime) > 0.001:
            stale.append((rel, "edited since import"))
    orphans = sorted(path for path in imported if path not in vault_notes)
    last_import = max((str(row["imported_at"]) for row in rows if row["imported_at"]), default=None)
    return {
        "vault": str(Path(vault or VAULT)),
        "vault_notes": len(vault_notes),
        "imported_notes": len(imported),
        "imported_current": len(vault_notes) - len(stale),
        "brain_chunks": sum(int(row["chunks"]) for row in rows),
        "stale": stale,
        "orphans": orphans,
        "last_import": last_import,
        "source_counts": [dict(row) for row in counts],
    }


def plan_sync(state: dict) -> dict:
    """Read-only preview of file work; used by strict dry-run."""
    files = state.get("files", {})
    seed_changed = sum(
        1 for doc in SEED_DOCS
        if doc.exists() and files.get("seed::" + doc.name) != doc.stat().st_mtime
    )
    seen = set()
    vault_changed = 0
    for path, rel in iter_vault_notes():
        key = "brain::" + rel
        seen.add(key)
        if files.get(key) != path.stat().st_mtime:
            vault_changed += 1
    removed = sum(1 for key in files if key.startswith("brain::") and key not in seen)
    return {"seed_changed": seed_changed, "vault_changed": vault_changed, "removed": removed}


# ── job 2: self-consolidation (learn from own sessions) ──────────────────
_CONSOLIDATE_PROMPT = (
    "Eres el sistema de memoria de AXIO. A partir de estos resúmenes de sesiones "
    "recientes, extrae SOLO lecciones duraderas y generalizables: preferencias de "
    "Michael, decisiones de arquitectura, hechos recurrentes y cómo trabajar mejor. "
    "Ignora detalles efímeros. Devuelve 1-5 viñetas concisas en español, sin "
    "preámbulo.\n\nRESÚMENES:\n{body}\n\nLECCIONES DURADERAS:"
)


def _recent_summaries(since_iso, limit=20):
    with connect() as conn:
        if since_iso:
            rows = conn.execute(
                "SELECT id, mode, ended_at, summary FROM sessions "
                "WHERE ended_at > %s AND summary <> '' "
                "ORDER BY ended_at ASC LIMIT %s",
                (since_iso, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, mode, ended_at, summary FROM sessions "
                "WHERE summary <> '' ORDER BY ended_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
    return rows


def consolidate(mgr, state: dict, log, engine: SelfMemoryEngine = None) -> int:
    rows = [r for r in _recent_summaries(state.get("consolidate_watermark")) if r.get("summary")]
    if not rows:
        log("  consolidate: no new sessions to learn from")
        return 0
    rows = sorted(rows, key=lambda r: str(r["ended_at"]))
    oc = OllamaClient()
    if not oc.is_running():
        log("  consolidate skipped (Ollama offline)")
        return 0
    engine = engine or SelfMemoryEngine(mgr, state, client=oc, log=log)
    try:
        processed = engine.consolidate_summaries(rows)
    except Exception as exc:
        log(f"  consolidate error: {exc}")
        return 0
    if not processed:
        return 0
    if not engine.dry_run:
        state["consolidate_watermark"] = str(rows[-1]["ended_at"])
    verb = "would consolidate" if engine.dry_run else "consolidated"
    log(f"  {verb} {len(rows)} session(s) -> self-memory engine")
    return processed


# ── loop ─────────────────────────────────────────────────────────────────
def _run_cycles(
    mgr,
    interval,
    consolidate_every,
    once,
    do_sync,
    do_consolidate,
    do_reflect,
    force_reflect,
    dry_run,
    log,
) -> int:
    config = load_self_memory_config()
    state = _load_state()
    audit = AuditLogger("self_memory")
    engine = SelfMemoryEngine(mgr, state, config=config, dry_run=dry_run, log=log)

    pending_full_resync = (
        state.get("mirror_version") != MIRROR_VERSION
        or bool(state.get("pending_full_resync"))
    )
    if pending_full_resync and not dry_run:
        state["files"] = {}
        state["pending_full_resync"] = True
        _save_state(state)
        log("  local mirror upgrade: full canonical re-sync pending")
    if (
        do_sync
        and not dry_run
        and not pending_full_resync
        and not state.get("files")
        and mgr.stats().get("embedding_count", 0) > 20
    ):
        _bootstrap(state, log)
        _save_state(state)

    if not dry_run:
        replayed = mgr.reconcile_pending()
        if replayed:
            log(f"  reconciled {replayed} pending event(s) into Postgres")

    cycle = 0
    try:
        while True:
            cycle += 1
            engine.reset_metrics()
            prefix = "[memory-runtime dry-run]" if dry_run else "[memory-runtime]"
            log(f"{prefix} cycle {cycle} — {datetime.now().strftime('%H:%M:%S')}")
            if do_sync:
                try:
                    if dry_run:
                        preview = plan_sync(state)
                        log(f"  files dry-run: {json.dumps(preview, sort_keys=True)}")
                    else:
                        if sync_files(mgr, state, log) == 0:
                            log("  files: up to date")
                        if pending_full_resync and state.get("files") and OllamaClient().is_running():
                            state["pending_full_resync"] = False
                            state["mirror_version"] = MIRROR_VERSION
                            pending_full_resync = False
                            log("  local mirror upgrade complete (canonical re-sync done)")
                except Exception as exc:
                    log(f"  sync error: {exc}")

            heavy_cycle = once or cycle % consolidate_every == 0
            wants_heavy = (do_consolidate and heavy_cycle) or do_reflect
            if wants_heavy:
                reasons = resource_gate_reasons(config)
                if reasons:
                    log("  self-memory deferred by resource gate: " + ", ".join(reasons))
                else:
                    if do_consolidate and heavy_cycle:
                        try:
                            consolidate(mgr, state, log, engine=engine)
                            engine.mine_sources()
                        except Exception as exc:
                            log(f"  self-memory consolidate/mine error: {exc}")
                    if do_reflect:
                        try:
                            if engine.reflect(force=force_reflect):
                                log("  reflection pass completed" if not dry_run else "  reflection dry-run planned")
                        except Exception as exc:
                            log(f"  reflection error: {exc}")

            if not dry_run:
                _save_state(state)
            metrics = engine.finish_metrics(pending_count())
            if dry_run:
                log("  dry-run metrics: " + json.dumps(metrics, sort_keys=True))
            else:
                audit.log_metrics("cycle", metrics)
            if once:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        log("\n[memory-runtime] stopped; state saved." if not dry_run else "\n[memory-runtime] dry-run stopped.")
    if not dry_run:
        _save_state(state)
    return 0


def run(interval=60, consolidate_every=None, once=False,
        do_sync=True, do_consolidate=True, do_reflect=True,
        force_reflect=False, dry_run=False, log=print) -> int:
    mgr = MemoryManager(TARGET_MODE)
    if not mgr._postgres_backend:
        log("Postgres Cortex not active (start axio-cortex-postgres). Aborting.")
        return 1
    try:
        mgr._postgres_backend.healthcheck()
    except Exception as exc:
        log(f"Postgres Cortex unavailable ({exc}). Local outbox remains intact.")
        return 1

    config = load_self_memory_config()
    consolidate_every = consolidate_every or int(config["consolidate_every"])
    if dry_run:
        return _run_cycles(
            mgr, interval, consolidate_every, once, do_sync, do_consolidate,
            do_reflect, force_reflect, True, log,
        )

    lock = SingleInstanceLock()
    if not lock.acquire():
        log("[memory-runtime] another writer holds the self-memory lock; yielding.")
        return 0
    try:
        return _run_cycles(
            mgr, interval, consolidate_every, once, do_sync, do_consolidate,
            do_reflect, force_reflect, False, log,
        )
    finally:
        lock.release()
