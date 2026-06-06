# AXIO Cortex Live-Memory Audit — Findings & Resolution

Audit of the Postgres/pgvector live-memory implementation against the goal of
evolving AXIO Console into AXIO Cortex with local-first living memory.
Companion to `CLAUDE_CODE_AUDIT_HANDOFF.md`.

Branch: `fix/cortex-live-memory-p1` · Tests: 28 → 42 (all passing) ·
Validated end-to-end against the live `axio-cortex-postgres` container.

---

## Correction to the first-pass P1 finding

The first pass claimed: *"pgvector adapter was never registered, so every
embedding store/recall fails against a live database."* **This was overstated.**

Live verification showed an existing `session_summary` embedding already in the
database, and store/recall both succeed **even with the `pgvector` Python
package uninstalled**. The reason: pgvector defines an implicit
`float8[] → vector` cast, so psycopg's default array adaptation is coerced into
the `vector` column. Embedding persistence was therefore **already working**.

What remained genuinely valuable:
- Registering the pgvector adapter is still the cleaner, canonical path (and
  supports numpy), so it is done **best-effort** — used when the package is
  present, skipped silently when absent (the implicit cast covers that case).
- The registration must **not** be mandatory: an earlier version raised when
  the package was missing, which — combined with the graceful fallback below —
  would have silently downgraded a working Postgres backend to JSON.

---

## Findings by severity (final status)

### P1 — Critical

1. **No graceful fallback when Postgres is configured but unavailable.** *(Real,
   fixed.)* The Postgres branches of `MemoryManager` (`get_facts`,
   `update_facts`, `recall`, `store_chunk`, `stats`, backend construction) had
   no error handling; a down DB, missing driver, or non-768 embedding crashed
   every prompt and every session exit. Now each degrades to JSON/keyword
   memory with a one-time warning.
   `core/memory.py`, commit `3e80e1d`.

2. ~~pgvector adapter never registered → all embeddings fail.~~ **Overstated —
   see correction above.** Store/recall worked via the implicit cast. Adapter
   registration added best-effort; the embedding-dimension crash is now caught
   by the fallback in (1). `core/db.py`, commits `3e80e1d`, `2b9aef6`.

### P2 — Medium

3. **Cross-mode recall was Postgres-only.** *(Fixed.)* Under the default
   Chroma/JSON backend, `allowed_modes` was ignored (one Chroma collection per
   mode; keyword fallback scanned only the current mode), so chat/cowork/code
   never recalled each other. `recall()` now fans out across every allowed
   mode's collection and merges by distance; the keyword fallback scans facts
   across allowed modes. `core/memory.py`, commit `9cee761`.

4. **RevRec stored canned content and leaked into `console`.** *(Fixed.)* It
   stored a hard-coded "session completed" message and still wrote its summary
   to the shared `console` namespace. Now it wraps `rev_agent.run_agent` /
   `run_agent_claude` to capture the real analysed tasks (with fact extraction),
   and `ISOLATED_MODES = ("revrec",)` keeps it out of `console`. Full model
   responses are not captured (rev_agent prints/returns None and is wrapped, not
   modified); the memos are already written to `OUTPUT_DIR`.
   `modes/revrec.py`, `core/memory.py`, commit `ae9e36d`.

5. **Chat `/load` ambiguity.** *(Fixed.)* Two `/load` branches existed; the
   file-context one was unreachable. Renamed to `/loadfile` and documented.
   `modes/chat.py`, commit `269fa0e`.

6. **Chat memory test covered dead code.** *(Fixed.)* The test exercised
   `_save_and_store_memory`, which production never calls. Repointed at the real
   path (`_store_chat_memory` → `ModeMemorySession.store`); removed the orphaned
   helper, the dead `mem` variable, and an unused import.
   `modes/chat.py`, `tests/test_chat_memory_persistence.py`, commit `a7b1207`.

### Architecture

7. **Postgres was not a Tier-1 system of record.** *(Fixed.)* The schema
   defined `sessions`/`messages` and the `session_id`/`source_session_id` FKs,
   but the backend only wrote `memory_facts`/`memory_embeddings`. Added
   `persist_session()` (writes the session row, one message row per turn, and
   the linked summary embedding in one transaction); `update_facts()` now records
   `source_session_id`; `store_session()` links facts to the session.
   `core/memory_backends/postgres_backend.py`, `core/memory.py`, commit `57c2219`.

---

## Live validation (against `axio-cortex-postgres`)

- Sessions + messages persisted with correct summaries and per-turn rows.
- Embeddings carry `session_id`; facts carry `source_session_id`.
- Cross-mode recall returns ranked results over real pgvector.
- Store/recall confirmed working both with and without the `pgvector` package.

## Not done (out of scope / deferred)

- **Ollama embeddings not exercised live** — validation used a deterministic
  stub vector. Needs `ollama pull nomic-embed-text`. Orthogonal to the DB path.
- **Migration is facts-only** — `scripts/migrate_memory_to_postgres.py` does not
  backfill `sessions`/`messages`/embeddings from legacy JSON.
- **RevRec full-response capture** — only user tasks are captured (see #4).
