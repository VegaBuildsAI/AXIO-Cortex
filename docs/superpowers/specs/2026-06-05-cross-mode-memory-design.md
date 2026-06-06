# AXIO Cross-Mode Memory Design

Date: 2026-06-05
Status: Approved design, pending implementation plan

## Goal

Connect AXIO `chat`, `cowork`, and `code` through one live Postgres-backed memory layer while keeping each mode's own memory namespace. The system should let AXIO reuse useful context across modes without flooding prompts with unrelated history.

`RevRec` remains a separate specialized agent memory. It can keep writing to its own `revrec` namespace, but it is excluded from automatic cross-mode recall for `chat`, `cowork`, and `code`.

## Current State

- `chat` already reads and writes Postgres memory through `MemoryManager`.
- `cowork` uses shared file context through `SESSION_CONTEXT`, but it does not persist memory.
- `code` uses shared file context and audit logs, but it does not persist memory.
- `revrec` already initializes `MemoryManager("revrec")` and injects a RevRec memory prefix into `rev_agent`.
- `console` is already used as a global summary namespace when `MemoryManager.store_session()` updates the console master facts.

## Recommended Architecture

Add a shared helper module:

```text
axio-console-v2.1/core/mode_memory.py
```

The helper provides a small common API for interactive modes:

```text
ModeMemorySession(mode, allowed_recall_modes=None)
prefix(query) -> str
record_turn(user_text, assistant_text, model="", metadata=None)
record_private(text, metadata=None)
record_global(text, metadata=None)
store(ollama_client=None)
handle_command(command) -> bool
```

The helper should wrap `MemoryManager` instead of replacing it. `MemoryManager` remains the low-level memory API. `ModeMemorySession` becomes the mode-facing workflow API.

## Mode Boundaries

Cross-mode automatic recall is enabled only for:

```text
chat
cowork
code
console
```

Default recall modes:

```text
current mode + console + other shared operational modes
```

For example:

- `code` can recall from `code`, `cowork`, `chat`, and `console`.
- `cowork` can recall from `cowork`, `code`, `chat`, and `console`.
- `chat` can recall from `chat`, `cowork`, `code`, and `console`.
- `revrec` only recalls from `revrec` unless explicitly extended later.

`RevRec` must not be included in the default cross-mode recall set. This keeps revenue recognition analysis isolated from general coding and coworking context.

## Read Flow

Before each model call in `chat`, `cowork`, or `code`:

1. Load structured facts from the current mode.
2. Load relevant global facts from `console`.
3. Embed the user query.
4. Recall relevant summaries from allowed modes.
5. Build a compact memory prefix.
6. Inject that prefix before the user prompt or task.

Memory injection should be compact and factual. It should not quote old conversations verbatim unless the stored summary itself is short and directly relevant.

## Write Flow

Each mode writes first to its own namespace:

```text
chat    -> mode = chat
cowork  -> mode = cowork
code    -> mode = code
revrec  -> mode = revrec
```

Only durable, reusable facts should be promoted to `console`. Examples:

- active project name;
- active repo path;
- user preferences;
- completed implementation tasks;
- architectural decisions;
- recurring toolchain problems and resolutions;
- important workspace paths;
- selected models or memory backend choices.

Do not promote:

- full raw conversations;
- full file contents;
- full tool outputs;
- temporary errors with no lasting value;
- detailed RevRec contract analysis;
- sensitive data.

## Commands

Add consistent memory commands to `chat`, `cowork`, and `code`:

```text
memory
memory global
memory recall <query>
memory share <text>
memory private <text>
```

Behavior:

- `memory`: show current mode memory stats and facts.
- `memory global`: show `console` memory stats and useful global facts.
- `memory recall <query>`: show cross-mode recall results for debugging.
- `memory share <text>`: save a user-approved global note to `console`.
- `memory private <text>`: save a note only to the current mode.

`RevRec` keeps its current memory command behavior unless a future RevRec-specific spec changes it.

## Cowork Integration

`cowork` should initialize:

```text
ModeMemorySession("cowork")
```

On each user prompt:

1. Build workspace context from loaded files.
2. Build memory prefix from the user prompt and workspace path.
3. Send memory prefix + workspace context + user prompt to the selected model.
4. Record the turn after a successful response.
5. Update facts such as workspace paths, active projects, loaded files, and preferred output style.
6. Store the session summary on `exit`, Ctrl+C, or EOF.

## Code Integration

`code` should initialize:

```text
ModeMemorySession("code")
```

Before each coding task:

1. Inject selected file context from `SESSION_CONTEXT`.
2. Build memory prefix from the task.
3. Pass memory prefix + task to the selected tool-calling backend.

After task completion:

1. Record user task and final agent answer.
2. Record a compact summary of tools used.
3. Update facts such as repo paths, tech stack, completed tasks, and known bugs.
4. Store the session summary on `exit`, Ctrl+C, or EOF.

The coding agent should not store raw tool logs as long-term memory. It should store a compact summary only.

## Chat Normalization

`chat` already works with Postgres memory. After `cowork` and `code` are connected, `chat` should be refactored to use `ModeMemorySession("chat")` so all shared modes use the same memory workflow.

This refactor should preserve current behavior:

- existing `/memory` or `memory` behavior remains available;
- session summaries continue to write embeddings;
- facts continue to update after each turn;
- Postgres remains selected through `AXIO_MEMORY_BACKEND=postgres`.

## RevRec Isolation

`revrec` remains specialized:

- keep `MemoryManager("revrec")`;
- keep RevRec-specific memory prefixing;
- keep RevRec session archive behavior;
- do not include `revrec` in default recall for `chat`, `cowork`, or `code`.

Optional future improvement: allow an explicit command such as `memory share revrec <summary>` if the user wants a high-level RevRec insight saved globally. This is out of scope for the first implementation.

## Backend Changes

Extend Postgres recall to support allowed modes:

```text
PostgresMemoryBackend.recall(embedding, n_results, modes=None)
```

Rules:

- `modes=None` keeps existing same-mode behavior.
- `modes=[...]` searches only the provided mode list.
- results include metadata with the originating mode.

Extend `MemoryManager.recall()` and `MemoryManager.build_memory_prefix()` to accept allowed modes without breaking existing callers.

## Testing Strategy

Add focused tests:

- `MemoryManager` same-mode recall still works.
- Postgres backend cross-mode recall filters by allowed modes.
- `revrec` is excluded from default operational cross-mode recall.
- `ModeMemorySession` records turns and stores session summaries.
- `cowork` injects memory into model prompts.
- `code` injects memory into agent tasks.
- `memory share` writes to `console`.
- `memory private` writes only to the current mode.

Existing tests must continue passing.

## Implementation Phases

Phase 1:

- Add cross-mode recall support to the Postgres backend.
- Add `core/mode_memory.py`.
- Add unit tests for recall filtering and command behavior.

Phase 2:

- Integrate `cowork` with `ModeMemorySession`.
- Add tests around prompt construction and session storage.

Phase 3:

- Integrate `code` with `ModeMemorySession`.
- Return final agent text from the local and Claude agent loops so memory can record successful tasks.
- Add tests around task prefixing and completion summaries.

Phase 4:

- Refactor `chat` to use the shared helper while preserving current behavior.

Phase 5:

- Verify `revrec` remains isolated and does not appear in default cross-mode recall.

## Risks And Controls

Risk: unrelated memories contaminate prompts.
Control: allowed mode filters, compact summaries, and exclusion of `revrec`.

Risk: prompts become too large.
Control: limit recall count and keep memory prefix concise.

Risk: sensitive content gets promoted globally.
Control: only explicit `memory share` and selected durable facts write to `console`.

Risk: code tool logs become noisy memory.
Control: store compact task summaries instead of raw tool logs.

## Acceptance Criteria

- `chat`, `cowork`, and `code` share relevant operational memory through Postgres.
- `RevRec` stays isolated by default.
- `memory share` stores global notes.
- `memory private` stores mode-only notes.
- Cross-mode recall can be inspected with `memory recall <query>`.
- Existing memory migration and Chat behavior continue to work.
- Unit tests pass with `py -m unittest discover tests -v`.
