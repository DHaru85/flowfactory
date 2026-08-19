"""应用层对服务层 StreamEventBus 的薄封装。"""

from __future__ import annotations

import asyncio
from uuid import UUID

from service.events.factory import get_stream_bus
from service.events.schemas import StreamEvent
from settings.config import get_settings


async def subscribe_sse(
    conversation_id: UUID,
) -> asyncio.Queue[StreamEvent]:
    cfg = get_settings()
    queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=max(8, cfg.stream_queue_maxsize))
    await get_stream_bus().subscribe(conversation_id, queue)
    return queue


async def unsubscribe_sse(
    conversation_id: UUID,
    queue: asyncio.Queue[StreamEvent],
) -> None:
    await get_stream_bus().unsubscribe(conversation_id, queue)


async def publish_sse(conversation_id: UUID, event: StreamEvent) -> None:
    await get_stream_bus().publish(conversation_id, event)
