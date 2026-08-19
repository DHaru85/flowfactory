"""会话 HTTP 序列化对象。"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ConversationCreateBody(BaseModel):
    title: str | None = Field(default=None, max_length=256)
    flow_id: UUID | None = None
    metadata: dict[str, object] | None = None


class ConversationOut(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None
    app_key: str
    flow_id: UUID | None
    status: str


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


class SendMessageOut(BaseModel):
    conversation_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    run_id: UUID
