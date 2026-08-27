from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from core.config import (
    AXIO_DATA_ROOT,
    BASE,
    CLAUDE_API_KEY,
    CLAUDE_MODEL,
    LOCAL_ONLY,
    MODELS,
    OLLAMA_HOST,
)
from core.models import OllamaClient

from .runs import RunManager
from .schemas import (
    ApprovalDecision,
    ConversationCreate,
    ConversationUpdate,
    MessageCreate,
    WorkspaceOpen,
)
from .services import AxioServices
from .store import ConversationStore
from .workspaces import WorkspaceRegistry


DATA_ROOT = Path(
    os.getenv("AXIO_UI_DATA_DIR", str(AXIO_DATA_ROOT / "ui"))
).resolve()

store = ConversationStore(DATA_ROOT / "conversations")
workspaces = WorkspaceRegistry(DATA_ROOT / "workspaces.json")
runs = RunManager()
services = AxioServices(store, workspaces, runs)

app = FastAPI(
    title="AXIO Console Local API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    ollama = OllamaClient()
    return {
        "status": "ok",
        "local_only": LOCAL_ONLY,
        "bind_host": "127.0.0.1",
        "data_root": str(AXIO_DATA_ROOT),
        "ollama": {
            "available": ollama.is_running(),
            "host": OLLAMA_HOST,
            "model": MODELS["chat"],
        },
        "claude": {
            "configured": bool(CLAUDE_API_KEY),
            "model": CLAUDE_MODEL,
        },
    }


@app.get("/api/capabilities")
def capabilities():
    ollama = OllamaClient()
    if LOCAL_ONLY:
        code_capability = {
            "backend": "ollama",
            "model": MODELS["coding"],
            "available": ollama.is_running(),
            "local_fallback": True,
        }
    else:
        code_capability = {
            "backend": "claude",
            "model": CLAUDE_MODEL,
            "available": bool(CLAUDE_API_KEY),
            "local_fallback": False,
        }
    return {
        "modes": {
            "chat": {"backend": "ollama", "model": MODELS["chat"]},
            "cowork": {"backend": "ollama", "model": MODELS["reasoning"]},
            "code": code_capability,
        },
        "streaming": "sse",
        "local_only": LOCAL_ONLY,
    }


@app.get("/api/conversations")
def list_conversations():
    return store.list()


@app.post("/api/conversations", status_code=201)
def create_conversation(body: ConversationCreate):
    if body.workspace_id:
        try:
            workspaces.get(body.workspace_id)
        except KeyError:
            raise HTTPException(404, "Workspace not found.")
    return store.create(body.mode, body.title, body.workspace_id)


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    conversation = store.get(conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found.")
    return conversation


@app.patch("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: str, body: ConversationUpdate):
    conversation = store.get(conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found.")
    if body.title is not None:
        conversation["title"] = body.title.strip() or "New conversation"
    if body.workspace_id is not None:
        try:
            workspaces.get(body.workspace_id)
        except KeyError:
            raise HTTPException(404, "Workspace not found.")
        conversation["workspace_id"] = body.workspace_id
    store.save(conversation)
    return conversation


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str):
    if not store.delete(conversation_id):
        raise HTTPException(404, "Conversation not found.")


@app.post("/api/conversations/{conversation_id}/messages", status_code=202)
def send_message(conversation_id: str, body: MessageCreate):
    conversation = store.get(conversation_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found.")
    if conversation["mode"] == "code":
        if not LOCAL_ONLY and not CLAUDE_API_KEY:
            raise HTTPException(
                503,
                "Code mode requires ANTHROPIC_API_KEY. No local fallback is enabled.",
            )
        if not conversation.get("workspace_id"):
            raise HTTPException(422, "Code mode requires an active workspace.")
    try:
        run = services.start(conversation, body.content.strip(), body.file_ids)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    return runs.summary(run.id)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        return runs.summary(run_id)
    except KeyError:
        raise HTTPException(404, "Run not found.")


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str, after: int = Query(default=0, ge=0)):
    try:
        runs.get(run_id)
    except KeyError:
        raise HTTPException(404, "Run not found.")
    return StreamingResponse(
        runs.stream(run_id, after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    try:
        return runs.cancel(run_id)
    except KeyError:
        raise HTTPException(404, "Run not found.")


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: str, body: ApprovalDecision):
    try:
        return runs.resolve_approval(approval_id, "approved", body.note)
    except KeyError:
        raise HTTPException(404, "Approval not found.")


@app.post("/api/approvals/{approval_id}/deny")
def deny(approval_id: str, body: ApprovalDecision):
    try:
        return runs.resolve_approval(approval_id, "denied", body.note)
    except KeyError:
        raise HTTPException(404, "Approval not found.")


@app.get("/api/workspaces")
def list_workspaces():
    return workspaces.list()


@app.post("/api/workspaces/open", status_code=201)
def open_workspace(body: WorkspaceOpen):
    try:
        return workspaces.open(body.path)
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/workspaces/{workspace_id}/files")
def list_workspace_files(workspace_id: str):
    try:
        return workspaces.files(workspace_id)
    except KeyError:
        raise HTTPException(404, "Workspace not found.")
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc))


@app.get("/api/workspaces/{workspace_id}/files/{file_id}")
def get_workspace_file(workspace_id: str, file_id: str):
    try:
        return workspaces.read_file(workspace_id, file_id)
    except KeyError:
        raise HTTPException(404, "File not found.")
    except (OSError, ValueError) as exc:
        raise HTTPException(422, str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_api.main:app", host="127.0.0.1", port=8765, reload=False)
