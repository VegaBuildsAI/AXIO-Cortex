# Brain tools (`brain_search`, `brain_read`, `brain_list`)

The Postgres Cortex is AXIO's one brain. It holds Michael's Second Brain notes (imported from the
Obsidian vault by `scripts/ingest_second_brain.py` and the scheduled `AXIO Memory Sync`) beside what
AXIO learned on its own: `self_learned` lessons, `memory_seed` docs, `exemplar`s and session
summaries. All three tools query **Postgres only**. They never read vault files and never write.
revrec's isolated namespace is never searched.

| Tool | Use it for |
|---|---|
| `brain_search(query, top_k=8, source="")` | Topical questions: a project, a person, a past decision. Exact pgvector search plus keyword match. `source` narrows to `second_brain`, `self_learned`, `memory_seed`, `exemplar` or `session_summary`. If Ollama is down it falls back to keyword-only and says so. |
| `brain_read(path)` | The full text of one imported note, rebuilt from its ordered chunks, e.g. `01-Projects/minios.md`. Use the exact path from a search or list result. |
| `brain_list(folder="")` | Which notes are imported under a folder (e.g. `01-Projects/`), their headings, and chunk counts per source. |

Workflow: `brain_search` → if the snippet is partial, `brain_read` the note path → answer and name the
note. Every turn already carries a `=== SECOND BRAIN ===` prompt section with the top few matching
chunks; use the tools when that section does not settle the question.

Memory is historical context, not live state. When a note conflicts with the repository or a
command result, trust the live evidence and say so.
