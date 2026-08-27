# AXIO — Continuous Self-Memory (RAG) — Codex Handoff

> **Purpose.** Harden and extend AXIO's autonomous *self-memory* loop: a
> continuous process where the platform reads its own produced sessions and
> knowledge, distills durable lessons with the **local** model, and writes them
> back as memory that RAG injects into every future prompt — giving the model
> **self-accumulating context with no human in the loop**.
>
> **This is auto-memory (continuous RAG). It is NOT weight training.**
> No fine-tuning. No LoRA. No GPU. No modification of any model's parameters.
> The model self-authors *context* (Tier-2 vectors + Tier-3 facts), never weights.

---

## 0. OPERATING CONTRACT — run as "Fable 5"

You (Codex) will execute this work to the same standard the previous engineer
(Claude, this session) held. Adopt it as your operating contract:

1. **Verify, don't assume.** Read the actual code before changing it. Confirm
   table/column/function names against the source. Never invent an API.
2. **Real end-to-end validation.** Every change ships with a test or a
   reproducible run. "It compiles" is not "it works." Run the suite:
   `.venv\Scripts\python.exe -m unittest discover tests -v` — keep it green.
3. **Incremental & reviewable.** Small, self-contained commits on a feature
   branch. Describe what changed and why. One concern per change.
4. **Do no harm to what already works.** The Cortex resilience layer was just
   audited and fixed (see `CLAUDE_CODE_CORTEX_MEMORY_AUDIT_HANDOFF.md`). Do not
   regress persist-before-inference, the durable outbox, dead-lettering, or the
   Postgres-primary/local-mirror contract.
5. **Honesty in reporting.** If something fails, say so with the output. If you
   skipped a step, say so. Do not claim done without proof.
6. **Secrets discipline.** Never print, log, or commit `.env`, the
   `ANTHROPIC_API_KEY`, or the DB password. Never send memory contents to any
   external service — everything stays local.
7. **Confirm cost/irreversible actions.** Ask before deleting data, before
   changing scheduled tasks, before anything hard to undo.
8. **Communicate with Michael in Spanish**, concise and technically precise.

If a requirement here conflicts with the running system's safety, stop and
surface the conflict rather than forcing the change.

---

## 1. Scope

### In scope (build/harden)
A **continuous self-context engine** on top of the existing consolidation loop:
deduplicated self-learned lessons, periodic reflection/compaction, promotion of
stable lessons into always-loaded facts, confidence/decay, contradiction
handling, broader self-sourcing, and a resilient continuous runner — all as
**memory** the model retrieves, with full observability and bounded growth.

### Explicitly OUT of scope
- ❌ Weight fine-tuning / LoRA / QLoRA / distillation into parameters.
- ❌ Any GPU/training toolchain (IPEX-LLM, bitsandbytes, PEFT, etc.).
- ❌ Changing the embedding model. `nomic-embed-text` (768-dim) is **immutable**.
- ❌ New heavyweight infra. Reuse Ollama + Postgres/pgvector + the existing
  Chroma mirror.

---

## 2. Current system (verified this session — trust but re-confirm)

**Loop.** `core/memory_runtime.py`
- `run(interval, consolidate_every, once, do_sync, do_consolidate, log)` — the
  cycle. Calls `reconcile_pending()` first, then `sync_files()` and
  `consolidate()`.
- `sync_files()` — re-indexes changed AXIO seed docs (`SEED_DOCS`) + the Second
  Brain vault (`VAULT = C:\Users\AXIO\Documents\Second Brain`) by mtime. Skips
  cleanly if Ollama is offline (no data loss).
- `consolidate()` — **the self-memory step.** Reads recent session summaries via
  `_recent_summaries(watermark)` from Postgres `sessions`, asks the **local**
  model (`MODELS["fast"]` = `gemma4:12b`) to distill durable lessons using
  `_CONSOLIDATE_PROMPT`, and stores them with `mgr.store_chunk(...)` under
  `source_type="self_learned"`, mode `console`. Advances
  `state["consolidate_watermark"]`.
- State: `STATE_FILE = AXIO_DATA_ROOT/memory_runtime_state.json`
  (`consolidate_watermark`, `files`, `mirror_version`, `pending_full_resync`).

**Storage.** `core/memory.py` (`MemoryManager`) + `core/memory_backends/postgres_backend.py`
- `store_chunk(text, metadata)` → Postgres `memory_embeddings`
  (`mode, source_type, content, embedding(768), metadata jsonb`) + local Chroma
  mirror collection `axio_{mode}`.
- `update_facts({...})` → Postgres `memory_facts` (`mode, key, value`). The
  console fact `global_profile` is injected **deterministically** into
  chat/cowork/code (always-loaded, not similarity-gated).
- `delete_chunks(source_type, key, value)` — now **durable** (enqueues a
  `delete` event replayed by `reconcile_pending`); use it for any removal.
- `recall(query, n, allowed_modes)` — pgvector cosine top-N.
- `build_memory_prefix(query, allowed_modes)` — injects always-loaded facts +
  top-`MEMORY_RECALL_RESULTS` (=5) recalled chunks into every turn.

**source_types already in use:** `session_summary`, `self_learned`,
`memory_seed`, `second_brain`, `manual_private`, `manual_global`.

**Tables** (`postgres_backend.py`): `sessions(id, mode, title, started_at,
ended_at, summary, metadata)`, `messages(id, session_id, role, content,
created_at, model, metadata)`, `memory_facts(mode, key, value,
source_session_id, updated_at)`, `memory_embeddings(id, mode, source_type,
content, embedding, created_at, metadata)`.

**Automation (canonical — do not duplicate).** Scheduled tasks: `AXIO Cortex
Startup` (logon → `start_axio_memory.cmd`), `AXIO Memory Sync` (19:45,
`--once --sync-only`), `AXIO Memory Consolidate` (02:00, `--once
--consolidate-only`), `AXIO Cortex Backup`. A previous duplicate startup
shortcut and a duplicate consolidate task were removed — **do not reintroduce a
second writer.** Single-writer is a hard invariant.

---

## 3. Hard constraints / guardrails

- **Immutable embedder:** `nomic-embed-text` (768-dim). Never swap it; the
  backend hard-asserts `dim == 768`.
- **Postgres is primary; local files mirror.** Never make the loop write in a
  way that diverges from that contract.
- **Single writer.** Never run consolidation concurrently with itself. If you
  enable a continuous runner, the daily `AXIO Memory Consolidate` task must be
  disabled (or the continuous runner must acquire an exclusive lock and the task
  must no-op when the lock is held). Ask Michael before changing any task.
- **Never delete raw sessions/messages.** Compaction operates on *derived*
  self-learned memory only, and always via the durable `delete_chunks` path.
- **Bounded growth.** The self-learned store must not grow without limit;
  compaction + dedup keep it small and canonical.
- **Everything local.** No memory content leaves the machine.
- **Idempotent & re-runnable.** Every job can run twice with no duplication and
  no data loss (watermarks + dedup + UPSERT).

---

## 4. Objective — capabilities to add

Turn the current "distill lessons daily" step into a real self-context engine:

### 4.1 Dedup before store
Before inserting a new `self_learned` lesson, embed it and compare (cosine)
against existing `self_learned` vectors. If similarity ≥ `dedup_threshold`
(start 0.92): **do not insert a duplicate** — instead *reinforce* the existing
lesson (bump `reinforced_count`, refresh `last_seen`). Only genuinely new
lessons create new rows. Add a backend helper, e.g.
`find_similar(embedding, source_type, threshold)` that runs a scoped pgvector
query (`WHERE mode=%s AND source_type=%s ORDER BY embedding <=> %s LIMIT 1`).

### 4.2 Reflection / compaction pass
Periodically (when `self_learned` count > `compaction_trigger`, e.g. 200, or on
a weekly cadence): cluster related lessons, ask the local model to **merge them
into a smaller canonical set**, then replace the old rows with the merged ones
via `delete_chunks` + `store_chunk`. Preserve provenance in metadata
(`merged_from`, `first_seen`). Net effect: the store stays small, sharp, and
non-redundant — "consolidating the consolidations."

### 4.3 Promotion to always-loaded facts
When a lesson is stable and recurring (`reinforced_count ≥ promote_after`, e.g.
3) **and** it is an enduring fact about Michael / his preferences / the
architecture, promote it into console **facts** via `update_facts` (e.g. enrich
`global_profile`, `global_preferences`, or a new `learned_principles` key) so it
becomes **always-loaded**, not merely top-N recallable. Keep the vector too (for
semantic recall); the fact is the durable, deterministic form.

### 4.4 Confidence & decay
Track per-lesson metadata: `reinforced_count`, `first_seen`, `last_seen`,
`confidence` (0–1). Lessons reinforced often gain confidence; lessons not seen
again within `decay_days` and still low-confidence are **demoted/retired** (via
durable `delete_chunks`, or moved to a `retired` source_type). Never retire a
promoted fact automatically — surface it for review instead.

### 4.5 Contradiction handling
During reflection, if a new lesson contradicts an existing fact/lesson, do not
blindly append. Ask the local model to reconcile: keep the newer statement, mark
the older `superseded_by=<id>` (metadata), and lower its confidence. Log every
supersession so Michael can audit what the system "changed its mind" about.

### 4.6 Broader self-sourcing (still memory, not weights)
Extend beyond session summaries. Mine high-signal material from `messages`:
- Turns the **Claude tier** answered (metadata/model `claude-*`) — store as
  `source_type="exemplar"` memory (a high-quality answer worth *remembering*,
  retrievable later). This is recall, not training.
- User **corrections** ("no, en realidad…", "prefiero…") — strong preference
  signal; route into preference facts.
- Code-mode outcomes (a fix that worked / a command that failed) — durable
  operational lessons.
Keep a separate watermark per source so nothing is reprocessed.

### 4.7 Continuous, resilient runner
Make `run()` fit for long-lived operation as the "self-context subagent":
- Lower-latency incremental consolidation (smaller `consolidate_every`) so
  memory updates through the day, not once at 02:00.
- **Resource gate:** skip the heavy consolidate/reflection passes when on
  battery or under high CPU/RAM load; retry next cycle.
- **Single-instance lock** (a lockfile under `AXIO_DATA_ROOT`) so two runners
  never overlap; the scheduled task must yield if the continuous runner holds it.
- Preserve the existing crash-safety (`KeyboardInterrupt` → state saved) and
  keep calling `reconcile_pending()` each cycle.

---

## 5. Suggested module layout (additive — don't rewrite the loop)

```
core/self_memory.py            # new: dedup, reinforce, compaction, promotion,
                               #      decay, contradiction, exemplar/correction mining
core/memory_runtime.py         # extend consolidate() to call core.self_memory;
                               #      add reflection cadence + resource gate + lock
core/memory_backends/postgres_backend.py
                               # add find_similar(embedding, source_type, threshold)
                               # and any scoped count/query helpers you need
config/self_memory.yaml        # thresholds + cadences (see §6)
scripts/axio_memory_runtime.py # add flags: --reflect-only, --dry-run
tests/test_self_memory.py      # new: dedup, promotion, decay, compaction, contradiction
```

Prefer **metadata-only** changes over schema migrations. All the new per-lesson
fields (`reinforced_count`, `confidence`, `first_seen`, `last_seen`,
`superseded_by`, `merged_from`) live inside the existing `metadata jsonb`
column. If you truly need a migration, make it additive and non-destructive
(follow `scripts/migrate_ioaf_resilience.py`'s style).

---

## 6. Config (all tunable, with safe defaults)

`config/self_memory.yaml`:
```yaml
dedup_threshold: 0.92          # cosine; ≥ this = reinforce, not insert
promote_after: 3               # reinforced_count to promote a lesson to a fact
compaction_trigger: 200        # self_learned rows before a reflection pass
compaction_target: 60          # aim to compact down toward this many canonical lessons
decay_days: 45                 # unseen + low-confidence lessons retire after this
min_confidence_keep: 0.35
consolidate_every: 6           # cycles between light consolidations (continuous mode)
reflect_every_hours: 168       # weekly deep reflection/compaction
resource_gate:
  skip_on_battery: true
  max_cpu_percent: 70
```

---

## 7. Autonomy — "healthiest for the model"

- **Only work on new data.** Watermarks per source; never re-distill the same
  sessions/turns.
- **Off-hours for heavy passes.** Reflection/compaction at low-load windows.
- **Cost-aware.** Consolidation uses the local model (free); log token counts
  and durations to `logs/` (reuse the `usage` audit style) so growth is visible.
- **Never auto-corrupt facts.** Promotions and supersessions are logged; provide
  a `--dry-run` that reports what *would* change without writing.
- **Bounded & reversible.** Compaction keeps provenance; retired lessons are
  logged; nothing raw is ever lost.

---

## 8. Observability

- Structured log line per cycle: `{new_lessons, reinforced, promoted, retired,
  merged, exemplars_added, pending_events, duration_ms}`.
- A `scripts/self_memory_report.py` (read-only) that prints: total self_learned,
  promoted facts, top reinforced lessons, recent supersessions, store size — so
  Michael can see what the model has taught itself.

---

## 9. Acceptance criteria (Definition of Done)

1. `.venv\Scripts\python.exe -m unittest discover tests -v` — **all green**,
   including new `tests/test_self_memory.py` covering: dedup-reinforces (no dup
   row), promotion-to-fact at threshold, decay-retires-stale, compaction-shrinks
   store while preserving canonical content, contradiction marks `superseded_by`.
2. `scripts/verify_memory_resilience.py` still passes (per-mode Chroma↔Postgres
   parity, outbox drained) — the resilience layer is untouched.
3. A **dry-run** on real data prints a sensible plan and writes nothing.
4. A live run: second consecutive run reports "no new lessons / up to date"
   (idempotent); the self_learned store does **not** grow unbounded across runs;
   `global_profile`/facts get enriched by a stable recurring lesson.
5. Single-writer proven: continuous runner + scheduled task never both consolidate
   at once (lock respected). No reintroduced double-fire.
6. No secrets in logs; embedder untouched; all data local.

---

## 10. What NOT to do

- Do not touch `nomic-embed-text`, the outbox/reconcile/dead-letter logic, or the
  Postgres-primary contract (beyond the additive helpers named here).
- Do not add a second concurrent writer or a duplicate scheduled task.
- Do not delete raw `sessions`/`messages`.
- Do not introduce any training/fine-tuning/GPU dependency.
- Do not let the self-learned store grow without compaction.

---

## 11. Report back

When done, post: branch name, files changed, test output (all green), a
`self_memory_report.py` sample, and a short note (Spanish) on what the loop now
does autonomously and how to enable the continuous runner. Flag any task-schedule
change you propose and **wait for Michael's approval** before applying it.
