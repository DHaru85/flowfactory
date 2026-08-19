"""SSE 帧（对齐 data_schema_server.md Conversation 域）。"""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ProtocolEventName = Literal[
    "connected",
    "run_submitted",
    "run_completed",
    "run_failed",
    "speaking",
    "reasoning",
    "tool_calling",
    "step_running",
    "subagent_running",
]

CONTROL_EVENTS = frozenset({"connected", "run_submitted", "run_completed", "run_failed"})
DELTA_EVENTS = frozenset(
    {"speaking", "reasoning", "tool_calling", "step_running", "subagent_running"}
)


class SseEvent(BaseModel):
    event: str
    data: dict[str, object] = Field(default_factory=dict)
    id: str | None = None


def speaking_event(*, delta: str, message_id: UUID, event_id: str | None = None) -> SseEvent:
    return SseEvent(
        event="speaking",
        data={"delta": delta, "message_id": str(message_id)},
        id=event_id,
    )


def run_submitted_event(*, run_id: UUID, message_id: UUID) -> SseEvent:
    return SseEvent(
        event="run_submitted",
        data={"run_id": str(run_id), "message_id": str(message_id)},
    )


def format_sse(event: SseEvent) -> str:
    lines: list[str] = [f"event: {event.event}"]
    if event.id:
        lines.append(f"id: {event.id}")
    lines.append(f"data: {json.dumps(event.data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"
