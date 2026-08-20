"""流式总线工厂。无 URL 用进程内 Fake；AMQP 按事件循环隔离连接。"""

from __future__ import annotations

import asyncio
import weakref

from service.events.fake import FakeStreamEventBus
from service.events.protocol import StreamEventBus
from settings.config import get_settings

_override: StreamEventBus | None = None
_fake: FakeStreamEventBus | None = None
_amqp_by_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, StreamEventBus] = (
    weakref.WeakKeyDictionary()
)


def set_stream_bus_override(bus: StreamEventBus | None) -> None:
    global _override, _fake
    _override = bus
    if bus is None:
        _fake = None
        _amqp_by_loop.clear()


def reset_stream_bus() -> None:
    """fork 后丢弃连接，下次惰性重建。"""
    global _fake
    _fake = None
    _amqp_by_loop.clear()


def _amqp_bus(url: str) -> StreamEventBus:
    from service.events.amqp import AmqpStreamEventBus

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return AmqpStreamEventBus(url)
    existing = _amqp_by_loop.get(loop)
    if existing is not None:
        return existing
    created = AmqpStreamEventBus(url)
    _amqp_by_loop[loop] = created
    return created


def get_stream_bus() -> StreamEventBus:
    if _override is not None:
        return _override
    cfg = get_settings()
    url = cfg.rabbitmq_url.strip()
    if not url:
        global _fake
        if _fake is None:
            _fake = FakeStreamEventBus()
        return _fake
    return _amqp_bus(url)
