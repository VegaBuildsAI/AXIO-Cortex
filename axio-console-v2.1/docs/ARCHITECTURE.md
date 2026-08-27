# AXIO Platform — IOAF Architecture

> ⚠️ **STALE (superseded).** This describes the May/June ChromaDB-era memory design (mistral/qwen3 models, ChromaDB as Tier-2 primary). The current architecture is Postgres-primary "Cortex" — see **`docs/CORTEX.md`** and **`CLAUDE.md`** for accurate current state. Kept for the diagram only.

> Unified architecture diagram for AXIO v2.1 (Final Debugged Release 1).
> Reconstructed faithfully from the three FigJam source files (`*.jam`).

![AXIO IOAF Architecture](./AXIO-Architecture.svg)

The canonical export lives at [`diagrams/AXIO-Architecture.svg`](../diagrams/AXIO-Architecture.svg).
It is a vector SVG (1680×2240) — open in any browser or re-import into Figma.
Regenerate it with:

```
py tools/gen_arch.py
```

## Sources

| FigJam file | Band in the diagram |
|---|---|
| `AXIO v2.1 — Four-Mode Platform Workflow.jam` | 1 · Four-Mode Platform Workflow |
| `AXIO IOAF — Three-Tier Memory System.jam` | 2 · IOAF Three-Tier Memory System |
| `AXIO IOAF — Model Routing & Fallback Architecture.jam` | 3 · Model Routing & Fallback |

> FigJam `.jam` files are ZIP archives containing `canvas.fig` (fig-kiwi format:
> a deflate-compressed kiwi schema block followed by a **zstd**-compressed node
> data block). The diagram text was decoded from the zstd block — see
> `tools/gen_arch.py`.

## Band 1 — Four-Mode Platform Workflow

`py axio.py` launcher → `--claude` gate (sets `FORCE_CLAUDE=1`, routing every
prompt to Claude) → one of four modes, each backed by a Claude tier and a local
Ollama model:

| Mode | File(s) | Claude / Local | Notes |
|---|---|---|---|
| Chat | `modes/chat.py` | Haiku 4.5 / `mistral:latest` | Fast general chat |
| Code | `modes/code.py` | Sonnet 4.6 / `qwen3-coder:30b` | File tools + PowerShell |
| Cowork | `modes/cowork.py` | Sonnet 4.6 / auto-routed local | Workspace assistant |
| RevRec | `modes/revrec.py`, `rev_agent.py` | Sonnet 4.6 / `qwen3:14b` | ASC 606 + Excel |

All four modes share the `IOAF MemoryManager` (`core/memory.py`) — Tier 3 Facts
JSON, Tier 2 ChromaDB RAG, Tier 1 Session JSON — which feeds the cross-mode
**Console Master Memory** (`~/.axio/memory/console_memory.json`).

## Band 2 — IOAF Three-Tier Memory System (session lifecycle)

**Read path:** `User Message` → `MemoryManager` reads Tier 3 (Structured Facts
JSON) + Tier 2 (ChromaDB semantic recall, Top-N) → injects a memory prefix into
the System Prompt → Model Call (Ollama / Claude API) → Response.

**Write path (on `/exit`):**
- Tier 1 Write — raw JSON to `~/.axio/sessions/*.json`
- Tier 3 Write — `auto_update_facts()` → `chat/code/console_memory.json`
- Tier 2 Write — `qwen3:14b` summarizes the session → `nomic-embed-text` embeds
  it (768-dim) → ChromaDB `PersistentClient` writes the vector collection at
  `~/.axio/chroma/`

| Tier | Store | Role |
|---|---|---|
| Tier 1 | Raw session JSON | Short-term source material |
| Tier 2 | ChromaDB vectors | Semantic recall across sessions |
| Tier 3 | Structured key-value facts | Always loaded, even without Ollama/ChromaDB |

## Band 3 — Model Routing & Fallback Architecture

`User Prompt` → `core/router.py` (keyword + regex detection) → one route:

| Route | Target | Detail |
|---|---|---|
| `math` | `engine/math_tool.py` | `python_exact`, score = 100 (instant exact answer) |
| `coding_agent` | `qwen3-coder:30b` | Coding / agentic (score ≥ 80) |
| `revenue_analysis` | `qwen3:14b` | ASC 606 / revenue |
| `quick_chat` | `qwen3:8b` | Fast reasoning |
| `premium_reasoning` / `FORCE_CLAUDE=1` | Claude Sonnet 4.6 | Anthropic API |

**Fallback / escalation chain:**
- Fallback → `qwen3:8b` on API error / timeout
- Fallback → Claude Sonnet 4.6 on timeout in MATH / ARCH
- Escalate → Claude Haiku 4.5 on low confidence
