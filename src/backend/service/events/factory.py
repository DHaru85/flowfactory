"""流式总线工厂。rabbitmq_url 非空用独立 AMQP 连接；空则 Fake。不占用 Celery 任务连接。"""

from __future__ import annotations

from service.events.fake import FakeStreamEventBus
from service.events.protocol import StreamEventBus
from settings.config import get_settings

_override: StreamEventBus | None = None
_instance: StreamEventBus | None = None


def set_stream_bus_override(bus: StreamEventBus | None) -> None:
    global _override, _instance
    _override = bus
    if bus is None:
        _instance = None


def reset_stream_bus() -> None:
    """fork 后丢弃连接，下次惰性重建。"""
    global _instance
    _instance = None


def get_stream_bus() -> StreamEventBus:
    if _override is not None:
        return _override
    global _instance
    if _instance is None:
        cfg = get_settings()
        url = cfg.rabbitmq_url.strip()
        if not url:
            _instance = FakeStreamEventBus()
        else:
            from service.events.amqp import AmqpStreamEventBus

            _instance = AmqpStreamEventBus(url)
    return _instance
