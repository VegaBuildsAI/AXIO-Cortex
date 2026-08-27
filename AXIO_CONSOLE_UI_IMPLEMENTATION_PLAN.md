# AXIO Console UI — Local-Only Implementation Plan

**Status:** Planning baseline  
**Target:** Local Windows application  
**Repository:** `C:\Users\AXIO\AXIO Model Improvement`  
**Date:** 2026-07-26

## 1. Objective

Build a polished, Claude-inspired user interface for AXIO Console while preserving AXIO's own identity and existing IOAF runtime.

The application will expose three primary modes:

1. **Chat** — general conversation with persistent AXIO memory.
2. **Cowork** — workspace-aware assistance with local files and generated artifacts.
3. **Code** — agentic coding with file tools, command approvals, diffs, and test output.

The application is local-only. It is not intended to be a public web service, multi-user SaaS, or remotely accessible server.

## 2. Fixed Architecture Decisions

### Deployment

- Run entirely on the local Windows machine.
- Bind the application backend to `127.0.0.1`.
- Do not expose the backend to the LAN or internet.
- Keep local sessions, memory, files, logs, and credentials on the machine.
- Store API credentials only in the backend `.env`; never expose them to the frontend.

### Automatic Model Routing

| Mode | Backend | Model behavior |
|---|---|---|
| Chat | Local Ollama | Always use `qwen3:14b` |
| Cowork | Local Ollama | Always use `qwen3:14b` |
| Code | Claude API | Always use the configured Claude coding model |

```text
Chat   ──────► Ollama ──────► qwen3:14b
Cowork ──────► Ollama ──────► qwen3:14b
Code   ──────► Claude API
```

The machine will not attempt to run `qwen3-coder:30b` locally.

There will be no manual API-boost switch in the standard UI. Backend selection is determined automatically by the active mode.

If the Claude API is unavailable:

- Code mode must fail closed with a clear diagnostic.
- Code mode must not silently downgrade to a weaker local model.
- Chat and Cowork must remain available through local Ollama.

## 3. Current-State Audit

AXIO already contains a substantial Python terminal runtime:

- Unified launcher in `axio-console-v2.1/axio.py`.
- Chat, Cowork, Code, and RevRec terminal modes.
- Ollama and Anthropic clients.
- Streaming model responses.
- IOAF persistent memory.
- JSON session persistence.
- Optional PostgreSQL and pgvector memory.
- File and workspace context loading.
- Code tools for reading, writing, editing, searching, and running commands.
- Human confirmation before terminal command execution.
- JSONL audit logs.
- Model routing and fallback logic.

### Missing application layers

- No browser or desktop frontend.
- No local HTTP API.
- No SSE or WebSocket bridge between a UI and the Python runtime.
- No structured event protocol for tokens, tools, approvals, diffs, errors, and completion.
- No background run lifecycle or cancellation API.
- No browser-safe workspace boundary.
- No reusable headless services for the three modes.

### Main integration constraint

The mode implementations are coupled to terminal operations such as:

- `input()`
- `print()`
- terminal spinners
- terminal confirmation prompts
- process-global file context

The UI must not control these modes by simulating terminal input. The underlying model, memory, workspace, and agent behavior should first be extracted into headless services.

## 4. Target Architecture

```text
┌─────────────────────────────────────────────────────┐
│                AXIO React Interface                 │
│                                                     │
│  Sidebar │ Chat/Cowork/Code │ Files/Artifacts/Diff │
└──────────────────────────┬──────────────────────────┘
                           │
                     HTTP + SSE
                           │
┌──────────────────────────▼──────────────────────────┐
│              Local FastAPI Application             │
│                   127.0.0.1 only                   │
│                                                     │
│  Conversation API      Run/Event API               │
│  Workspace API         Approval API                │
└───────────────┬──────────────────────┬──────────────┘
                │                      │
┌───────────────▼──────────┐  ┌────────▼──────────────┐
│ AXIO Headless Services  │  │ Security Boundaries  │
│                         │  │                       │
│ ChatService             │  │ Workspace containment │
│ CoworkService           │  │ Command approvals     │
│ CodeService             │  │ Safe file identifiers │
│ ConversationService     │  │ Audit trail           │
│ WorkspaceService        │  │ Cancellation          │
└───────────────┬─────────┘  └───────────────────────┘
                │
┌───────────────▼─────────────────────────────────────┐
│                 Existing AXIO Core                  │
│                                                     │
│ Ollama/qwen3:14b │ Claude API │ IOAF │ Files │ Logs │
└─────────────────────────────────────────────────────┘
```

## 5. User Interface

The interface should adopt Claude's clarity and interaction patterns without copying Claude branding or proprietary visual assets.

### Shared application shell

- Collapsible left sidebar.
- New conversation button.
- Searchable conversation history.
- Chat, Cowork, and Code mode selector.
- Active workspace indicator.
- Main conversation area.
- Persistent composer.
- Streaming response display.
- Stop-generation control.
- Right-side contextual panel.
- Local/API backend status.
- Memory status.
- Settings panel.

### Mode-specific behavior

| Mode | Main area | Contextual panel |
|---|---|---|
| Chat | Conversation and attachments | Memory, sources, and artifacts |
| Cowork | Workspace-grounded conversation | File tree, previews, and generated outputs |
| Code | Agent task and tool timeline | Files, diffs, terminal output, and tests |

### Backend status labels

- Chat: `Local · qwen3:14b`
- Cowork: `Local · qwen3:14b`
- Code: `Cloud boost · Claude`
- Code failure: `Claude API unavailable`

The status is informative rather than a normal model-selection control.

## 6. Backend API

### Core resources

- Conversation
- Message
- Workspace
- File reference
- Run
- Event
- Tool call
- Approval
- Artifact

### Minimum endpoints

```text
GET    /api/health
GET    /api/capabilities

GET    /api/conversations
POST   /api/conversations
GET    /api/conversations/{conversation_id}
DELETE /api/conversations/{conversation_id}

POST   /api/conversations/{conversation_id}/messages

GET    /api/runs/{run_id}
GET    /api/runs/{run_id}/events
POST   /api/runs/{run_id}/cancel

POST   /api/approvals/{approval_id}/approve
POST   /api/approvals/{approval_id}/deny

GET    /api/workspaces
POST   /api/workspaces/open
GET    /api/workspaces/{workspace_id}/files

GET    /api/files/{file_id}
GET    /api/runs/{run_id}/diff
```

### Streaming event contract

Use Server-Sent Events for model tokens and task activity.

```json
{
  "type": "token",
  "run_id": "uuid",
  "sequence": 12,
  "timestamp": "2026-07-26T12:00:00Z",
  "data": {
    "text": "partial response"
  }
}
```

Supported event types:

- `run_started`
- `status`
- `token`
- `message`
- `tool_started`
- `tool_result`
- `approval_required`
- `diff`
- `artifact`
- `warning`
- `error`
- `run_cancelled`
- `run_completed`

SSE is sufficient for the initial application. WebSockets should only be introduced if a later version requires a fully interactive terminal session.

## 7. Safety Requirements

Even as a local-only application, the browser-facing backend must enforce explicit boundaries.

### Workspace containment

- Register a selected directory as a workspace.
- Resolve and canonicalize every requested path.
- Reject any operation outside the active workspace.
- Expose opaque file IDs to the frontend instead of arbitrary absolute paths.
- Prevent `..` traversal, symlink escapes, and ambiguous path resolution.

### Code actions

Require explicit approval for:

- Terminal commands.
- File deletion.
- Overwriting an existing file.
- Writes outside an already approved task scope.
- Package installation.
- Git commit, push, or branch operations.

The approval must be represented as backend state, not a blocking terminal `input()` call.

### Secrets

- Never return `.env` content through the API.
- Redact secrets from logs and command output.
- Do not include API keys in browser storage.
- Keep Anthropic requests in the Python backend.

## 8. Implementation Phases

### Phase 0 — Contract and baseline

Tasks:

- Freeze current CLI behavior with focused tests.
- Confirm the configured Claude API model.
- Set Chat and Cowork defaults to `qwen3:14b`.
- Set Code to require Claude automatically.
- Define typed schemas for conversations, runs, events, workspaces, and approvals.
- Define the workspace security contract.

Exit criteria:

- Model routing is deterministic and tested.
- API and event contracts are documented.
- Existing CLI behavior remains operational.

### Phase 1 — Headless runtime extraction

Create reusable services:

```text
ChatService
CoworkService
CodeService
ConversationService
WorkspaceService
ApprovalService
```

Replace direct terminal dependencies with adapters:

- `EventSink` instead of `print()`.
- `ApprovalProvider` instead of `input()`.
- `CancellationToken` for active runs.
- Request-scoped file context instead of the global `SESSION_CONTEXT`.

Keep the terminal interface working through a CLI adapter.

Exit criteria:

- Chat, Cowork, and Code can run without terminal input/output.
- The CLI and future API share the same service implementation.
- No business logic is duplicated in the frontend.

### Phase 2 — Local FastAPI layer

Tasks:

- Add FastAPI and typed request/response models.
- Bind only to `127.0.0.1`.
- Implement conversation endpoints.
- Implement SSE run streaming.
- Implement cancellation.
- Implement approval lifecycle.
- Implement workspace and file APIs.
- Connect IOAF memory and existing audit logging.
- Add structured error responses and correlation IDs.

Exit criteria:

- All three modes work through API integration tests.
- A disconnected client can reload a completed conversation.
- Code mode cannot execute a protected action without approval.

### Phase 3 — Shared frontend and Chat

Recommended stack:

- React with TypeScript.
- Next.js or Vite.
- CSS variables or Tailwind for AXIO design tokens.
- TanStack Query for server state.
- Markdown rendering with syntax highlighting.
- Accessible component primitives.

Tasks:

- Build the application shell.
- Build sidebar and conversation history.
- Build the message renderer and composer.
- Add streaming token rendering.
- Add stop and retry actions.
- Display local Ollama health.
- Connect persistent Chat conversations.

Exit criteria:

- Chat works end to end with `qwen3:14b`.
- Conversations persist and reload.
- Streaming can be stopped cleanly.
- The UI remains usable when Claude is unavailable.

### Phase 4 — Cowork

Tasks:

- Add local workspace selection.
- Add workspace file tree.
- Add file loading and context chips.
- Add text and document preview.
- Display context size and truncation warnings.
- Add artifact preview and explicit save/export actions.
- Connect Cowork to `qwen3:14b`.

Exit criteria:

- A user can select a local workspace.
- AXIO can answer using selected files.
- Generated outputs are not written without an explicit user action.
- All reads and writes remain inside the workspace boundary.

### Phase 5 — Code

Tasks:

- Route every Code task to Claude API automatically.
- Add agent activity timeline.
- Display tool calls and results.
- Add approval cards.
- Add Monaco-based file and diff views.
- Add terminal/test output panel.
- Add cancel, retry, and failure recovery.
- Record verification results in the final task summary.

Exit criteria:

- Code mode never attempts to load the local coder model.
- Missing Claude configuration produces a clear failure before the run begins.
- Commands and destructive file actions require approval.
- The user can inspect proposed and completed diffs.
- Test output is visible and associated with the run.

### Phase 6 — Packaging and hardening

Tasks:

- Add a local launcher for backend and frontend.
- Add health checks and startup diagnostics.
- Add crash recovery for incomplete runs.
- Add frontend end-to-end tests.
- Add keyboard navigation and accessibility testing.
- Package as a Windows desktop application if desired, using Tauri or a controlled local launcher.

Exit criteria:

- AXIO starts from one local command or application shortcut.
- The backend is not reachable from another machine.
- Active and completed runs recover predictably after restarting the UI.

## 9. Recommended Delivery Sequence

The safest vertical sequence is:

1. Make routing deterministic.
2. Extract Chat into a headless service.
3. Add FastAPI and SSE.
4. Build the shared AXIO interface.
5. Prove persistent Chat end to end.
6. Add Cowork with workspace containment.
7. Add Code with Claude-only routing and durable approvals.
8. Package the local application.

Do not begin with a terminal subprocess wrapper. It may produce a quick visual demo, but it would preserve terminal coupling and make approvals, cancellation, streaming, and recovery unreliable.

## 10. Initial Definition of Done

The local AXIO Console MVP is complete when:

- One command launches the local backend and frontend.
- The backend listens only on `127.0.0.1`.
- Chat and Cowork automatically use local `qwen3:14b`.
- Code automatically uses Claude API.
- Code fails clearly when Claude is unavailable.
- Conversations persist and reload.
- Model output streams into the UI.
- Runs can be cancelled.
- Cowork files remain constrained to the selected workspace.
- Code actions have visible tool activity and approval gates.
- Diffs and test results are inspectable.
- API keys never reach the frontend.
- Existing IOAF memory and audit logging remain integrated.

## 11. Deferred Scope

The following are intentionally excluded from the first local release:

- Public deployment.
- LAN access.
- User accounts.
- Multi-user tenancy.
- Cloud file storage.
- Mobile applications.
- Team collaboration.
- Billing.
- Local execution of `qwen3-coder:30b`.
- Automatic Code fallback to a weaker local model.
- Full interactive terminal emulation unless later proven necessary.

## 12. Immediate Next Step

Begin Phase 0 with a narrow implementation branch:

1. Add deterministic mode-to-backend configuration.
2. Add tests confirming Chat/Cowork use `qwen3:14b`.
3. Add tests confirming Code requires Claude.
4. Define the initial API and SSE schemas.
5. Extract the first headless `ChatService` without changing the terminal experience.
