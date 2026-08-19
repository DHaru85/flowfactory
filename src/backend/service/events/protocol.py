"""流式事件总线协议。"""

from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from service.events.schemas import StreamEvent


class StreamEventBus(Protocol):
    """跨进程流式帧：publish 可丢；subscribe 写入调用方提供的 asyncio.Queue。"""

    async def publish(self, conversation_id: UUID, event: StreamEvent) -> None:
        """投递一帧。失败只记录，不向调用方抛出。"""

    async def subscribe(
        self,
        conversation_id: UUID,
        queue: asyncio.Queue[StreamEvent],
    ) -> None:
        """绑定会话；后续帧 put 进 queue（满则丢）。"""

    async def unsubscribe(
        self,
        conversation_id: UUID,
        queue: asyncio.Queue[StreamEvent],
    ) -> None:
        """取消绑定。"""
