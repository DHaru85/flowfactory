"""内存总线：单测与无 RabbitMQ 时使用。"""

from __future__ import annotations

import asyncio
from uuid import UUID

from loguru import logger

from service.events.schemas import StreamEvent


class FakeStreamEventBus:
    def __init__(self) -> None:
        self._subs: dict[UUID, list[asyncio.Queue[StreamEvent]]] = {}
        self.published: list[tuple[UUID, StreamEvent]] = []

    async def publish(self, conversation_id: UUID, event: StreamEvent) -> None:
        self.published.append((conversation_id, event))
        for queue in list(self._subs.get(conversation_id, [])):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("流式本地 Queue 已满，丢弃 conversation_id={}", conversation_id)

    async def subscribe(
        self,
        conversation_id: UUID,
        queue: asyncio.Queue[StreamEvent],
    ) -> None:
        holders = self._subs.setdefault(conversation_id, [])
        if queue not in holders:
            holders.append(queue)

    async def unsubscribe(
        self,
        conversation_id: UUID,
        queue: asyncio.Queue[StreamEvent],
    ) -> None:
        holders = self._subs.get(conversation_id)
        if holders is None:
            return
        if queue in holders:
            holders.remove(queue)
        if not holders:
            self._subs.pop(conversation_id, None)
