"""会话 SSE 异步帧迭代：只消费有界 asyncio.Queue。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from loguru import logger

from api.sse.bus import subscribe_sse, unsubscribe_sse
from api.sse.machine import StreamProtocolError, StreamStateMachine
from api.sse.protocol import format_sse


async def conversation_sse_iter(conversation_id: UUID) -> AsyncIterator[str]:
    queue = await subscribe_sse(conversation_id)
    machine = StreamStateMachine()
    try:
        for frame in machine.apply_command("subscribe"):
            yield format_sse(frame)
        while True:
            try:
                incoming = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            try:
                emitted = machine.apply_event(incoming)
            except StreamProtocolError as exc:
                logger.warning(
                    "SSE 非法转移 conversation_id={} state={} event={}",
                    conversation_id,
                    exc.state,
                    exc.event,
                )
                continue
            for frame in emitted:
                yield format_sse(frame)
    finally:
        machine.apply_command("unsubscribe")
        await unsubscribe_sse(conversation_id, queue)
