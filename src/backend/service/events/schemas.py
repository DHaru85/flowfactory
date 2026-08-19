"""流式事件传输 DTO（服务层，不依赖 api）。"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class StreamEvent(BaseModel):
    event: str
    data: dict[str, object] = Field(default_factory=dict)
    id: str | None = None


def speaking_event(*, delta: str, message_id: UUID) -> StreamEvent:
    return StreamEvent(
        event="speaking",
        data={"delta": delta, "message_id": str(message_id)},
    )


def run_lifecycle_event(
    name: str,
    *,
    run_id: UUID,
    message_id: UUID | None = None,
) -> StreamEvent:
    payload: dict[str, object] = {"run_id": str(run_id)}
    if message_id is not None:
        payload["message_id"] = str(message_id)
    return StreamEvent(event=name, data=payload)


def routing_key(conversation_id: UUID) -> str:
    return f"conv.{conversation_id}"
