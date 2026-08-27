from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Mode = Literal["chat", "cowork", "code"]


class ConversationCreate(BaseModel):
    mode: Mode = "chat"
    title: str = Field(default="New conversation", max_length=120)
    workspace_id: str | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    file_ids: list[str] = Field(default_factory=list, max_length=50)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    workspace_id: str | None = None


class WorkspaceOpen(BaseModel):
    path: str = Field(min_length=1, max_length=1_000)


class ApprovalDecision(BaseModel):
    note: str = Field(default="", max_length=500)
