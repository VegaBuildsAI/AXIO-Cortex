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
evolution into AXIO Cortex. His GitHub project is
`VegaBuildsAI/AXIO-Cortex`.

## What Is AXIO

**AXIO** is a local-first, multi-model AI orchestration platform. It is a
personal implementation of the **IOAF (Intelligent Orchestrated Agent
Framework)** — a three-tier memory architecture that makes AI sessions stateful
and cumulative across time, ending the stateless nature of typical AI tools.
AXIO runs local Ollama-hosted open-source LLMs as the default backend and uses
the Anthropic Claude API as a premium cloud tier. The long-term vision is a
growing, longitudinal knowledge base where every interaction across all modes
accumulates into shared memory.

## How AXIO Works

AXIO launches from `py axio.py` and routes each prompt through keyword/smart
routing to either a local Ollama model or Claude. Every mode follows the same
pattern: build a memory prefix from prior context before each model call, record
the turn afterward, and store a session summary on exit. Local models handle
most work; Claude is reserved for premium/complex tasks. A math tool intercepts
arithmetic for exact results. Audit logs are written per mode as JSONL.

## Operational Modes

- **Chat** — general conversation. Claude: haiku; local: mistral.
- **Code** — autonomous tool-calling coding agent (file tools + PowerShell).
  Claude: sonnet; local: qwen3-coder:30b.
- **Cowork** — file-aware workspace assistant with smart routing. Claude:
  sonnet; local: auto-routed (qwen3:8b / qwen3:14b).
- **RevRec** — ASC 606 / IFRS 15 revenue-recognition specialist with Excel
  tooling. Local: qwen3:14b. Memory is **isolated** from the shared namespace.

## Memory Architecture (IOAF)

Three tiers: **Tier 1** raw session history; **Tier 2** a vector store of
embedded session summaries for semantic recall; **Tier 3** structured key-value
facts per mode (user name, projects, preferences) plus a cross-mode `console`
master memory. Embeddings use `nomic-embed-text` (768-dim); summaries use
`qwen3:14b` with thinking disabled.

## AXIO Cortex — Living Memory

AXIO Cortex is the evolution of AXIO Console into a local-first system with
**live, persistent memory** backed by a Docker **Postgres + pgvector** database
(container `axio-cortex-postgres`, db `axio_cortex`, bound to 127.0.0.1:5432).
The backend is selected with `AXIO_MEMORY_BACKEND=postgres`; JSON remains the
default fallback. Postgres is the Tier-1 system of record: sessions, messages,
facts, and embeddings persist with foreign-key links. chat/cowork/code share
memory and recall from each other and from `console`; RevRec stays isolated.

## Working Preferences

Michael prefers: real end-to-end validation over assumptions ("don't leave
anything undone"); incremental work reviewed one item at a time; clean git
hygiene (feature branches, descriptive commits, PRs); local-first and
privacy-conscious design; honest correction of mistakes; and communication in
Spanish.

## Technical Environment

Windows + Python (`py`). Local models via Ollama at 127.0.0.1:11434:
mistral:latest, qwen3:8b, qwen3:14b, qwen3-coder:30b, llama3.1:8b, and
nomic-embed-text:latest. Cloud: Anthropic Claude (sonnet + haiku). Database:
pgvector/pgvector:pg16 via Docker Compose. Repo: VegaBuildsAI/AXIO-Cortex.
