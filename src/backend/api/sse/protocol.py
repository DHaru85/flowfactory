"""SSE 帧：与服务层 StreamEvent 字段对齐。"""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from service.events.schemas import StreamEvent as SseEvent
from service.events.schemas import reasoning_event, run_lifecycle_event, speaking_event

ProtocolEventName = Literal[
    "connected",
    "run_submitted",
    "run_completed",
    "run_failed",
    "run_interrupted",
    "speaking",
    "reasoning",
    "tool_calling",
    "step_running",
    "subagent_running",
]

CONTROL_EVENTS = frozenset({"connected", "run_submitted", "run_completed", "run_failed"})
DELTA_EVENTS = frozenset(
    {
        "speaking",
        "reasoning",
        "tool_calling",
        "step_running",
        "subagent_running",
        "run_interrupted",
    }
)


def run_submitted_event(*, run_id: UUID, message_id: UUID) -> SseEvent:
    return run_lifecycle_event("run_submitted", run_id=run_id, message_id=message_id)


def format_sse(event: SseEvent) -> str:
    lines: list[str] = [f"event: {event.event}"]
    if event.id:
        lines.append(f"id: {event.id}")
    lines.append(f"data: {json.dumps(event.data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


__all__ = [
    "CONTROL_EVENTS",
    "DELTA_EVENTS",
    "ProtocolEventName",
    "SseEvent",
    "format_sse",
    "reasoning_event",
    "run_submitted_event",
    "speaking_event",
]
