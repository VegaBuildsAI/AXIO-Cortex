# AXIO Cortex — Memory Subsystem
> Current-state briefing for the memory brain. Authoritative over `docs/ARCHITECTURE.md` (which describes the superseded ChromaDB-era design). Data root: `C:\Users\AXIO\.axio`.

## What it is
"AXIO Cortex" is the platform's living, persistent memory — an implementation of **IOAF three-tier memory** that makes sessions stateful and cumulative across time and across modes (chat/cowork/code share; revrec is isolated). Two evolutions layer on top: **Resilient Cortex** (Postgres system-of-record + crash-safe local mirror + durable replay) and **Continuous Self-Memory** (a bounded local-RAG loop that distills lessons from the platform's own sessions — **not** weight training/fine-tuning).

## The three tiers
- **Tier 1 — short-term:** raw session history. Crash-safe local journals (`.axio/journals/{mode}/{id}.json`) + Postgres `sessions`/`messages`. Persist-**before**-inference (`persist_live_session`).
- **Tier 2 — medium-term (RAG):** embedded chunks (session summaries, seed docs, the Second Brain vault, self-learned lessons). **Postgres/pgvector primary + Chroma mirror** (`.axio/chroma-resilient/`, collections `axio_{mode}`). Recall = pgvector cosine top-N → Chroma → keyword fallback.
- **Tier 3 — long-term:** structured key-value facts per mode (Postgres `memory_facts` UNIQUE(mode,key) + atomic JSON mirror `.axio/memory/{mode}_memory.json`), plus a cross-mode `console` master with a deterministic `global_profile` injected into chat/cowork/code every turn (`build_memory_prefix`, `core/memory.py:886-957`).

Embeddings: **`nomic-embed-text` (768-dim), immutable** — the Postgres backend hard-asserts `dim==768` (`config.py:157-161`, `postgres_backend.py`). Never swap it.

## Backends (selected by `AXIO_MEMORY_BACKEND`, `config.py:166`)
- **Postgres/pgvector** — primary/system-of-record (only when backend == `postgres`).
- **Chroma** — local vector mirror (handled inline in `memory.py`, no separate backend module).
- **JSON + keyword** — implicit last-resort fallback (the **default**; `AXIO_MEMORY_BACKEND` defaults to `json`).
The only backend class is `core/memory_backends/postgres_backend.py` (`PostgresMemoryBackend`). DB: `axio_cortex` @ `127.0.0.1:5432`, user `axio` (`config.py:168-172`).

## Storage (all under `C:\Users\AXIO\.axio`)
| Store | Path | Tier |
|---|---|---|
| Session journals | `journals/{mode}/{id}.json` | 1 |
| Fact mirror | `memory/{mode}_memory.json` | 3 |
| Chroma mirror | `chroma-resilient/` | 2 |
| Durable outbox / dead-letter | `outbox/pending`, `outbox/dead` | — |
| Runtime state | `memory_runtime_state.json` | — |
| Single-writer lock | `self_memory.lock` | — |
| Backups | `backups/*.sql` | — |

## Key files
- `core/memory.py` — `MemoryManager` (per mode; facts, RAG store/recall, session persist, outbox reconcile, `build_memory_prefix`, console master).
- `core/mode_memory.py` — `ModeMemorySession` (record-before-inference lifecycle; shared vs isolated modes; `memory` CLI subcommands). Wired: `modes/chat.py`, `cowork.py`, `code.py`, `revrec.py`.
- `core/memory_durability.py` — atomic writes (fsync+os.replace), journals, durable outbox, dead-letter (`MAX_REPLAY_ATTEMPTS=5`).
- `core/self_memory.py` — `SelfMemoryEngine` (distill/dedup/reinforce/promote/decay/contradiction/compaction, source mining, single-writer lock, resource gate). Needs Postgres.
- `core/memory_runtime.py` — background loop: reconcile → sync files (re-index seed docs + Second Brain vault `C:\Users\AXIO\Documents\Second Brain`) → consolidate → mine → reflect. Flags `--once/--sync-only/--consolidate-only/--reflect-only/--dry-run`.
- `core/memory_consolidation.py` — `trigger_exit_consolidation()` (detached one-shot on clean exit).
- `core/db.py` — psycopg factory + pgvector registration.
- Config: `config/self_memory.yaml`. Scripts: `scripts/axio_memory_runtime.py`, `seed_cortex_memory.py`, `migrate_*`, `mirror_postgres_to_chroma.py`, `verify_memory_resilience.py`, `self_memory_report.py`, `backup_cortex.ps1`, `install_memory_tasks.ps1`; launchers `start_axio_memory.cmd`, `run_memory_runtime.cmd`.
- **Schema (outside repo):** `C:\Users\AXIO\AXIO Model Improvement\docker-compose.yml` + `docker/postgres/init/001_schema.sql`, `002_indexes.sql` (container `axio-cortex-postgres`, image `pgvector/pgvector:pg16`). Tables: `sessions`, `messages`, `memory_facts`, `memory_embeddings (vector(768))`, `audit_logs`, `benchmark_runs`, `model_scores`.

## Scheduled automation (Windows, single-writer)
`AXIO Cortex Startup` (logon) · `AXIO Memory Sync` (19:45, `--once --sync-only`) · `AXIO Memory Consolidate` (02:00, `--once --consolidate-only`) · `AXIO Cortex Backup` (02:30, `pg_dump` + retention).

## What works vs pending
- **Verified working** (per `CLAUDE_CODE_CORTEX_MEMORY_AUDIT_HANDOFF.md`): Postgres-primary + local mirror, persist-before-inference, durable outbox + idempotent replay + dead-lettering, per-mode isolation, deterministic `global_profile`, Postgres↔Chroma parity, continuous self-memory engine. ~491 embeddings, 0 pending at handoff; full suite green.
- **Pending / caveats:** real crash-failover **never exercised in production** (only simulated in unit tests) — controlled drop test awaits Michael's authorization; backend default is `json` (Postgres active only when set); **schema not provisioned by any in-repo migration** (Docker init only); risk areas flagged — per-message write amplification, `reconcile_pending()` cost on hot paths, outbox concurrency between two AXIO processes, unbounded growth of journals/sessions/Chroma (only backups have retention).

## Tests
`tests/test_memory_resilience.py`, `test_memory_postgres_fallback.py`, `test_memory_backend_selection.py`, `test_postgres_backend_unit.py`, `test_db_config.py`, `test_self_memory.py`, `test_memory_runtime_self.py`, `test_memory_consolidation.py`, `test_mode_memory_session.py`, `test_memory_cross_mode*.py`, `test_*_memory_*integration.py`, `test_revrec_isolation.py`.
