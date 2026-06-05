# The AXIO Manifesto
## Intelligent Orchestrated Agent Framework — IOAF v2.1

> *"The measure of intelligence is the ability to change."*
> — attributed to Albert Einstein

**Author:** Michael Vega
**Date:** May 9, 2026
**Version:** 2.1 — Final Debugged Release 1

---

## I. The Problem with AI Today

Every session with an AI tool begins the same way: from nothing.

You open a chat window. You explain who you are. You describe what you are working on. You provide context the tool should already know. You ask your question. You get an answer. You close the window.

Tomorrow, you open a new window. You start from nothing again.

This is the fundamental flaw of the current generation of AI tools. They are **stateless**. They are **amnesiac**. They treat every session as if it is the first time you have ever spoken. They consume your time not just answering questions, but re-learning what they should already know about you.

This is not intelligence. This is an expensive autocomplete that forgets you the moment you leave.

---

## II. The AXIO Thesis

AI should get smarter the longer you use it — not reset to zero every session.

Every conversation you have contains signal. Signal about your projects, your preferences, your domain vocabulary, your open questions, your decision history. Today that signal evaporates. AXIO captures it.

**AXIO** is a local-first, multi-model AI orchestration platform built on a single architectural conviction: **AI sessions should be stateful, cumulative, and sovereign.**

Stateful: the system remembers. Not just the last conversation — all of them, semantically indexed and retrievable.

Cumulative: every session adds to a growing knowledge base. The longer you use AXIO, the better it understands your work.

Sovereign: your data never leaves your machine unless you choose. No cloud dependency for memory. No vendor lock-in. No subscription required to keep your own history.

---

## III. IOAF — The Memory Architecture

The intellectual core of AXIO is the **Intelligent Orchestrated Agent Framework (IOAF)** — a three-tier memory system that transforms stateless model calls into a continuously learning personal AI workspace.

### Tier 1 — The Record

*What was said.*

Every session is saved verbatim as timestamped JSON at `~/.axio/sessions/`. This is the ground truth — a permanent, human-readable archive of every exchange. It requires no external dependencies. It is always written. It is the foundation on which the higher tiers are built.

### Tier 2 — The Understanding

*What it meant.*

At the end of every session, a language model reads the full conversation and writes a summary — not a transcript, but an interpretation. What were you working on? What decisions were made? What remained open? That summary is converted into a 768-dimensional vector by a local embedding model and stored in a ChromaDB vector database at `~/.axio/chroma/`.

When you begin your next session, AXIO embeds your first prompt and searches that vector store. The five most semantically similar past sessions surface automatically. Their summaries are injected into the system prompt before the first model call. The model already knows your context before you say a word.

This is not keyword search. It is semantic memory — recall by meaning, not by string match.

### Tier 3 — The Facts

*What you need it to know.*

Running in parallel to both tiers above is a lightweight structured facts store at `~/.axio/memory/`. Every user message is scanned for extractable facts: your name, your active projects, your clients, your preferred frameworks, your workspace paths. These facts are stored as simple key-value JSON and loaded at the start of every session — instantly, with no Ollama dependency.

Tier 3 is the fastest path to personalization. It is also the most resilient — it works even when the embedding model is unavailable.

### The Master Record

All four operational modes feed a single cross-mode knowledge base: `console_memory.json`. A conversation in RevRec about a SaaS contract can inform a follow-up session in Code about implementing the billing logic. The modes are separate workspaces. The memory is one.

---

## IV. Intelligent Routing — The Right Model for the Right Task

Not every question deserves the same model. Not every model deserves every question.

Large cloud models are powerful but expensive and latency-bound. Small local models are fast and free but have limits. The right architecture matches the task to the tool.

AXIO's router — `core/router.py` — inspects every prompt before any model call and assigns it to the optimal execution path:

| Task Type | Route | Model | Reason |
|-----------|-------|-------|--------|
| Arithmetic | `math` | Python interpreter | Exact, instant, deterministic. 100/100 every time. |
| Code generation | `coding_agent` | qwen3-coder:30b | Scored 92/100 on coding benchmarks. |
| Revenue analysis | `revenue_analysis` | qwen3:14b | Scored 85/100 on ASC 606 tasks. |
| General conversation | `quick_chat` | qwen3:8b | Fast, low cost, 92/100 on coding. |
| Complex reasoning | `premium_reasoning` | Claude Sonnet 4.6 | When only the best will do. |

Every route has a fallback chain. If the primary model fails, times out, or is unavailable, the next model in the chain takes over — automatically, without user intervention.

This is cost-aware orchestration. You pay for Claude when you need Claude. You use local compute when local compute is sufficient. The router decides.

### The Math Principle

Math deserves special mention. Every language model in AXIO's fleet — including the strongest — timed out or failed when asked to compute eight-digit multiplication in-context. Not because they are weak. Because computing arithmetic token-by-token in a 8192-token window is the wrong tool for the job.

AXIO routes all arithmetic to a Python interpreter before any model call. Zero latency. Zero tokens consumed. Score: 100.

This is the broader principle: **use the right instrument, not the most impressive one.**

---

## V. Four Modes — One Platform

AXIO presents four specialist operational modes, each with its own model assignment, toolset, and memory namespace. They share one runtime, one memory system, and one routing engine.

### Chat

*For thinking out loud.*

Fast general-purpose conversation powered by Claude Haiku or Mistral locally. The cheapest compute tier — appropriate for the most common task type. Full session memory. Math intercepted before model. Designed for speed.

### Code

*For building things.*

An autonomous agentic coding loop. The model does not just answer — it reads files, writes files, edits code, searches directories, and executes PowerShell. Claude Sonnet is the primary model; qwen3-coder:30b handles local sessions. Once Claude is selected within a session, the session stays on Claude — the sticky flag prevents mid-conversation model drift that degrades coherence.

### Cowork

*For working alongside your files.*

A workspace-aware assistant that indexes your project tree and routes each prompt to the best available model. Reference any file in context with `@filename`. The router decides on every turn whether the task warrants a fast local model or escalation to Claude.

### RevRec

*For revenue recognition.*

A specialist ASC 606 / IFRS 15 domain agent with 17 tools: contract analysis, performance obligation identification, transaction price determination, allocation schedules, deferred revenue models, variable consideration analysis, contract modification analysis, and written memo generation — all output to Excel. The same Claude call structure as Code mode. The same file tools. The same memory system. The domain is narrow; the capability is deep.

---

## VI. Sovereignty by Design

AXIO is built on an explicit stance: **your AI memory belongs to you.**

Every piece of data AXIO generates — sessions, embeddings, facts, summaries, audit logs — lives in `~/.axio/` on your local machine. No API call persists your history to a third-party server. No subscription controls access to your own past sessions. No vendor can revoke your memory.

The Anthropic Claude API is an optional escalation tier, used only when you request it or when the router determines the task requires it. It is not the backbone of the system. It is a capability tier within a larger architecture that runs without it.

This is not an anti-cloud position. It is a pro-sovereignty position. Cloud compute is valuable. Cloud data custody is a risk.

AXIO separates the two.

---

## VII. The Assessment Engine — Knowing What You Have

You cannot optimize what you cannot measure.

AXIO includes a first-class benchmark and assessment system. Run `py axio.py benchmark` and the platform executes four standardized tasks against every configured model: exact arithmetic (MATH-001), Flask API code generation (CODING-001), ASC 606 performance obligation analysis (REVREC-001), and microservices architecture design (ARCH-001).

Results are scored by a rubric-based LLM-as-judge against domain-specific criteria — not vibes, not impressions, but structured rubrics with defined point allocations. Scores are logged to JSONL. Assessment snapshots are appended to `engine/assessments.jsonl` with full model-by-model breakdowns, latency data, and health flags for timeout errors.

This means routing decisions are not opinions. They are data.

When qwen3:14b scored 85/100 on revenue analysis and qwen3-coder:30b scored 72/100, the routing table was updated to match. When qwen3:8b and qwen3:14b both timed out on MATH-001, arithmetic was routed to the Python interpreter and the health flags cleared.

The system learns from its own performance data. That is not a feature. That is the point.

---

## VIII. What This Is Building Toward

AXIO v2.1 is a working, debugged, locally deployed platform. It is also a proof of concept for a larger idea.

The Console Master Memory (`~/.axio/memory/console_memory.json`) is a longitudinal record of every interaction across all modes. Every session adds to it. Over months, it becomes something more valuable than any individual conversation: a structured history of how a person thinks, what they build, what problems they return to, what they have already solved.

That record has uses beyond session recall. It is the raw material for fine-tuning a model on your specific domain vocabulary and decision patterns. It is the foundation for a personal AI that is genuinely personal — not just prompted to act like it knows you, but trained on evidence that it does.

The architecture is already in place. The data accumulation has already begun.

---

## IX. Architecture Diagrams

Three FigJam diagrams document the live system as built:

- **IOAF Model Routing & Fallback Architecture** — how every prompt flows through the router to its model, with fallback chains at every branch
  https://www.figma.com/board/NM2PhZHkCeRrhDF3cqnR0Y

- **IOAF Three-Tier Memory System** — how session data moves from raw conversation through summarization, embedding, and ChromaDB into semantic recall at the next session start
  https://www.figma.com/board/iNJUG5sGf7YYCEJRV99IOv

- **Four-Mode Platform Workflow** — how Chat, Code, Cowork, and RevRec share the routing engine, memory system, and Claude escalation tier
  https://www.figma.com/board/GTXZvCwuku1cf6UdBXDXvD

These are not aspirational diagrams. They reflect the deployed codebase as of May 9, 2026.

---

## X. Principles

**Local-first.** Run without the cloud. Escalate to it when it earns its cost.

**Memory compounds.** Every session should make the next one better. Statefulness is not a feature — it is the purpose.

**Route to the right instrument.** Cheap and fast is correct when it is sufficient. Expensive and powerful is correct when it is necessary. The router decides — on data, not assumption.

**Measure everything.** Routing decisions, benchmark scores, health flags, latency, and model drift — all logged, all queryable. Optimization follows observation.

**Sovereignty is not optional.** Your memory, your data, your machine. Cloud is a capability tier. It is not a dependency.

**Build for the long run.** The value of AXIO is not in any single session. It is in the accumulation — the growing knowledge base that makes every session richer than the one before.

---

*AXIO v2.1 — Final Debugged Release 1*
*Built by Michael Vega | msvv11@gmail.com*
*May 9, 2026*
