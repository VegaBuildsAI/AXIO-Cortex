# AXIO Platform — IOAF Architecture

> Current architecture diagram for AXIO v2.1 "Continuous Resilient Cortex Memory". For the memory subsystem in depth see [`docs/CORTEX.md`](CORTEX.md); for the live platform state see [`docs/STATE.md`](STATE.md).

![AXIO IOAF Architecture](./AXIO-Architecture.svg)

The canonical export lives at [`diagrams/AXIO-Architecture.svg`](../diagrams/AXIO-Architecture.svg) (vector SVG, 1680×2240). Regenerate it after any change with:

```
py tools/gen_arch.py
```

## Band 1 — Four-Mode Platform Workflow

`py axio.py` launcher → `--claude` gate (sets `FORCE_CLAUDE=1`) → one of four modes. Local base is **`gemma4:12b`** (Ollama); the agentic tier boosts to the **Anthropic Claude API**.

| Mode | File(s) | Model | Notes |
|---|---|---|---|
| Chat | `modes/chat.py` | `gemma4:12b` local (Claude Haiku path) | Session memory + web-augmentation |
| Code | `modes/code.py` | Claude Sonnet 4.6 (Opus available) | 42-tool agentic harness |
| Cowork | `modes/cowork.py` | `gemma4:12b` local (premium → Claude) | Workspace assistant + web-augmentation |
| RevRec | `modes/revrec.py`, `rev_agent.py` | `gemma4:12b` / Claude | ASC 606 + Excel; **isolated** memory |

Chat, Cowork, and Code share the **AXIO Cortex** `MemoryManager` (`core/memory.py`) and a cross-mode `console.global_profile`; RevRec is isolated.

## Band 2 — Cortex Memory (session lifecycle)

**Read path:** `User Message` → `MemoryManager` reads Tier 3 (facts: Postgres + JSON mirror, `console.global_profile` injected) + Tier 2 (pgvector cosine Top-N, with Chroma / keyword fallback) → injects a memory prefix into the System Prompt → Model Call (`gemma4:12b` / Claude API) → Response.

**Write path (persist *before* inference and on exit — crash-safe):**
- **Tier 1** — session journals (`~/.axio/journals/`) + Postgres `sessions`/`messages`.
- **Tier 3** — `auto_update_facts()` → Postgres `memory_facts` + atomic JSON mirror.
- **Tier 2** — `gemma4:12b` summarizes the session → `nomic-embed-text` embeds it (768-dim) → written to **Postgres/pgvector** with a **Chroma mirror**, via a **durable outbox** with idempotent replay.

| Tier | Store | Role |
|---|---|---|
| Tier 1 | Sessions + crash-safe journals | Short-term source material |
| Tier 2 | pgvector (primary) + Chroma (mirror) | Semantic recall across sessions |
| Tier 3 | Structured facts + `global_profile` | Always loaded (JSON fallback if Postgres is down) |

Backend is selected by `AXIO_MEMORY_BACKEND` (`json` fallback by default; `postgres` for the live Cortex). Resilience, self-memory, and the background runtime are detailed in [`docs/CORTEX.md`](CORTEX.md).

## Band 3 — Model Routing & Fallback

`User Prompt` → `core/router.py` (keyword + regex detection) → one route:

| Route | Target | Detail |
|---|---|---|
| `exact_math` | `engine/math_tool.py` | Python exact arithmetic (instant, score 100) |
| `coding_agent` | Claude Sonnet 4.6 / Opus | Code mode — 42-tool agent |
| `revenue_analysis` | Claude Opus 4.8 | ASC 606 / revenue |
| `quick_chat` | `gemma4:12b` | Chat / Cowork / quick |
| `premium` / `FORCE_CLAUDE=1` | Claude Opus 4.8 | Premium reasoning |

**Fallback / escalation:**
- `LOCAL_ONLY=1` or no API key → all routes fall back to `gemma4:12b` on-device.
- Claude Sonnet ⇄ Opus + effort switchable in-app (`model opus max`, `effort xhigh`).
- Local fallback to `gemma4:12b` on any Claude error / timeout.

---

*Diagram source: `tools/gen_arch.py` (originally reconstructed from three FigJam `*.jam` files, now maintained directly in code).*
