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


def tool_calling_event(
    *,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, object],
    status: str,
    result: object | None = None,
) -> StreamEvent:
    data: dict[str, object] = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "status": status,
    }
    if result is not None:
        data["result"] = result
    return StreamEvent(event="tool_calling", data=data)


def step_running_event(*, node_id: str, step_name: str, status: str) -> StreamEvent:
    return StreamEvent(
        event="step_running",
        data={"node_id": node_id, "step_name": step_name, "status": status},
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
