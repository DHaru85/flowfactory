"""会话 HTTP 序列化对象。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationCreateBody(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    flow_id: UUID | None = None
    metadata: dict[str, object] | None = None


class PlannerConversationCreateBody(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    profile_id: UUID
    metadata: dict[str, object] | None = None


class ConversationOut(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None
    app_key: str
    flow_id: UUID | None
    status: str


class ConversationDetailOut(ConversationOut):
    metadata: dict[str, object]


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content_blocks: list[dict[str, object]]
    status: str


class SendMessageBody(BaseModel):
    conversation_id: UUID | None = None
    app_key: str = "conversation"
    flow_id: UUID | None = None
    content: str = Field(min_length=1)
    metadata: dict[str, object] | None = None


class PlannerSendMessageBody(BaseModel):
    conversation_id: UUID | None = None
    profile_id: UUID | None = None
    content: str = Field(min_length=1)
    metadata: dict[str, object] | None = None


class SendMessageOut(BaseModel):
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    run_id: UUID


class HitlPendingOut(BaseModel):
    id: UUID
    run_id: UUID
    conversation_id: UUID | None
    node_id: str
    prompt: str
    form_schema: dict[str, object] | None
    status: str
    expires_at: datetime | None


class HitlResumeBody(BaseModel):
    decision: Literal["approve", "reject"]
    user_input: str | None = None


class HitlResumeOut(BaseModel):
    run_id: UUID
    resumed: bool
