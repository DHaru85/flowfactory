"""进程内 SSE 事件总线（本轮默认，非 Redis）。"""

from __future__ import annotations

import asyncio
from uuid import UUID

from api.sse.protocol import SseEvent

_override: InMemorySseBus | None = None


class InMemorySseBus:
    def __init__(self) -> None:
        self._subs: dict[UUID, list[asyncio.Queue[SseEvent]]] = {}

    def subscribe(self, conversation_id: UUID) -> asyncio.Queue[SseEvent]:
        queue: asyncio.Queue[SseEvent] = asyncio.Queue()
        self._subs.setdefault(conversation_id, []).append(queue)
        return queue

    def unsubscribe(self, conversation_id: UUID, queue: asyncio.Queue[SseEvent]) -> None:
        holders = self._subs.get(conversation_id)
        if holders is None:
            return
        if queue in holders:
            holders.remove(queue)
        if not holders:
            self._subs.pop(conversation_id, None)

    async def publish(self, conversation_id: UUID, event: SseEvent) -> None:
        for queue in list(self._subs.get(conversation_id, [])):
            await queue.put(event)

    def subscriber_count(self, conversation_id: UUID) -> int:
        return len(self._subs.get(conversation_id, []))


def set_sse_bus_override(bus: InMemorySseBus | None) -> None:
    global _override
    _override = bus


def get_sse_bus() -> InMemorySseBus:
    if _override is not None:
        return _override
    return _default_bus


_default_bus = InMemorySseBus()
