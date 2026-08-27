# AXIO Cortex — Memory Seed

> Foundational memory for AXIO Cortex. Seeds the living-memory store so every
> mode (chat, cowork, code) recalls who the user is, what AXIO is, and how it
> works. Ingested into the `console` master namespace as embedded chunks +
> structured facts.

## User Profile — Michael

The user is **Michael** (email: msvv11@gmail.com). He is the creator and
architect of AXIO. He works on **Windows** at
`C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1`. He communicates
primarily in **Spanish** and prefers concise, direct, technically precise
answers. Michael builds and owns the AXIO platform end to end and is driving its
evolution into AXIO Cortex. His GitHub project is `VegaBuildsAI/AXIO-Cortex`. He
keeps an Obsidian "Second Brain" vault at `C:\Users\AXIO\Documents\Second Brain`
(PARA structure: Projects, Areas, Resources, People, Daily) that is indexed into
the Cortex for recall.

## What Is AXIO

**AXIO** is a local-first, multi-model AI orchestration platform — a personal
implementation of **IOAF (Intelligent Orchestrated Agent Framework)**, a
three-tier memory architecture that makes AI sessions stateful and cumulative
across time. It is Michael's **local mirror of Claude's Chat / Cowork / Code**,
running **half local, half API**: local Ollama models handle everyday work and
the Anthropic Claude API is the frontier "boost" tier for hard agentic tasks.
The vision is a growing, longitudinal knowledge base where every interaction
across all modes accumulates into shared memory.

## Current Model Configuration (HYBRID)

The platform runs a **hybrid** scheme (as of the current build):

- **Local base — `gemma4:12b`** (Ollama): powers Chat, Cowork, and every local
  role. Multimodal (text/vision), supports tools + thinking. It is also the
  local fallback for the agentic tier.
- **Agentic tier — Claude API**: Code / reasoning / revenue / premium prompts
  boost to Claude. Two switchable models: **`claude-sonnet-4-6`** (default,
  cheaper: $3/$15 per MTok) and **`claude-opus-4-8`** (frontier: $5/$25).
- **Effort** is configurable (`low|medium|high|xhigh|max`); default **`high`**.
  Adaptive thinking is always on for Claude. Switch in-app:
  `model opus` / `model sonnet` / `model opus max` / `effort xhigh`.
- **`qwen3.6:latest` was dropped** — the machine (no dedicated GPU, ~31.6 GB
  RAM) cannot load a 24 GB model; that is why the heavy tier is Claude API, not
  a big local model.
- **Prompt caching** is on (`PROMPT_CACHE=1`): repeated system + tools + agent
  history bill at ~0.1x. A per-turn **token + cost counter** prints and logs to
  `logs/*_audit.jsonl` (type `usage`). Set `LOCAL_ONLY=1` to run 100% offline on
  gemma4 (no cloud).

## Operational Modes

- **Chat** — general conversation. Local `gemma4:12b`. Free (no API cost).
- **Cowork** — file-aware workspace assistant with smart routing. Local
  `gemma4:12b`; prompts that hit coding/revenue/premium keywords auto-boost to
  the Claude tier.
- **Code** — autonomous tool-calling coding agent (file tools + PowerShell).
  Runs on the Claude API (default `claude-sonnet-4-6`, effort high); local
  `gemma4:12b` fallback under `LOCAL_ONLY`.
- **RevRec** — ASC 606 / IFRS 15 revenue-recognition specialist with Excel/PDF
  tooling. Local `gemma4:12b`; auto-upgrades to Claude on PDF/complex tasks.
  Memory is **isolated** from the shared namespace.

## Memory Architecture (IOAF)

Three tiers: **Tier 1** raw session history; **Tier 2** a vector store of
embedded chunks (session summaries + seeded knowledge + the Second Brain) for
semantic recall; **Tier 3** structured key-value facts per mode plus a
cross-mode `console` master memory. Embeddings use **`nomic-embed-text`**
(768-dim) — the fixed background tokenizer, never changed. Session summaries use
`gemma4:12b`. Each turn, `build_memory_prefix()` injects always-loaded facts +
the top-N recalled chunks (RAG) into the prompt, so the local model answers with
Claude-like context without holding everything in the window.

## AXIO Cortex — Living Memory (Postgres)

AXIO Cortex is the evolution into a system with **live, persistent memory**
backed by a Docker **Postgres + pgvector** database — container
**`axio-cortex-postgres`** (compose project `axiomodelimprovement`), db
`axio_cortex`, published on the standard **127.0.0.1:5432**. Selected with `AXIO_MEMORY_BACKEND=postgres`; JSON is the fallback.
Postgres is the system of record: sessions, messages, facts, and embeddings
persist with foreign-key links. chat/cowork/code share memory and recall from
each other and from `console`; RevRec stays isolated. Loading knowledge is a
**data seed (INSERT of embedded chunks + facts)**, not a schema change.

The resilient local mirror is canonicalized at `C:\Users\AXIO\.axio` for CLI,
UI, and background runtime alike. Completed user/assistant events are written
immediately to crash-safe journals; facts are mirrored atomically to JSON; all
vectors are mirrored to `chroma-resilient`; and an idempotent outbox replays
offline writes when Postgres returns. Postgres is always the primary read/write
backend while healthy. `console.global_profile` is injected deterministically
into Chat, Cowork, and Code, while each mode retains its private facts/sessions.

## Continuous Self-Memory (local RAG, not training)

`core/self_memory.py` extends the memory runtime into a bounded autonomous context
loop. New session summaries are distilled by local `gemma4:12b` into individual
lessons, embedded with the immutable `nomic-embed-text` model, and deduplicated
against existing `self_learned` vectors. Repeated lessons increase confidence and
can be promoted into the always-loaded `console.learned_principles` fact. Explicit
user corrections also enrich `global_preferences`; Claude-tier answers and useful
Code outcomes are mined through separate incremental watermarks.

Weekly reflection detects contradictions, marks older derived lessons as
`superseded_by`, decays stale low-confidence lessons, and compacts related derived
memory while preserving provenance. Raw sessions and messages are never removed.
All derived deletes and metadata changes use the durable outbox path, and Postgres
remains primary with Chroma as its local mirror. A single OS lock prevents the
continuous runner and scheduled jobs from writing concurrently. Thresholds live in
`config/self_memory.yaml`; `--dry-run` previews without advancing state or writing
Postgres/Chroma/outbox/audit logs; `scripts/self_memory_report.py` is read-only.

Chat, Cowork, and Code clean exits persist their session synchronously and then start a
hidden one-shot consolidation in the background. This makes the saved session available
for immediate recall on the next launch while the deeper derived-memory pass completes.
The UI's per-turn persistence deliberately skips the exit trigger. If a process is killed
before cleanup can execute, completed events are still retained by the immediate journal
and Postgres writes; no exit hook can run after a forced termination.

## Working Preferences

Michael prefers: real end-to-end validation over assumptions ("don't leave
anything undone"); incremental work reviewed one item at a time; clean git
hygiene (feature branches, descriptive commits, PRs); local-first and
privacy-conscious design; honest correction of mistakes; cost-awareness (cheaper
model + effort + caching by default, boost only when needed); and communication
in Spanish.

## Technical Environment

Windows + Python (`py`). Local models via Ollama at 127.0.0.1:11434:
**gemma4:12b** (base) and **nomic-embed-text:latest** (embedder). Cloud:
Anthropic Claude API — `claude-sonnet-4-6` (default) and `claude-opus-4-8`
(frontier), switchable in-app. Database: pgvector/pgvector:pg16 via Docker
Compose on 127.0.0.1:5432. Repo: VegaBuildsAI/AXIO-Cortex.
