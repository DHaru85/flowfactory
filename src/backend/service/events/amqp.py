"""RabbitMQ topic 流式总线（独立 connection，与 Celery broker 隔离）。"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from loguru import logger

from service.events.schemas import StreamEvent, routing_key
from settings.config import get_settings


def _enqueue(queue: asyncio.Queue[StreamEvent], event: StreamEvent, conversation_id: UUID) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("流式本地 Queue 已满，丢弃 conversation_id={}", conversation_id)


class AmqpStreamEventBus:
    def __init__(self, amqp_url: str) -> None:
        self._url = amqp_url
        self._connection: AbstractRobustConnection | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._queue: aio_pika.abc.AbstractQueue | None = None
        self._lock = asyncio.Lock()
        self._subs: dict[UUID, list[asyncio.Queue[StreamEvent]]] = {}

    async def _ensure(self) -> aio_pika.abc.AbstractExchange | None:
        if self._exchange is not None:
            return self._exchange
        async with self._lock:
            if self._exchange is not None:
                return self._exchange
            cfg = get_settings()
            try:
                self._connection = await aio_pika.connect_robust(
                    self._url,
                    client_properties={"connection_name": "flowfactory-stream"},
                    timeout=cfg.stream_publish_timeout_seconds,
                )
                channel = await self._connection.channel()
                await channel.set_qos(prefetch_count=max(1, cfg.stream_prefetch))
                self._exchange = await channel.declare_exchange(
                    cfg.stream_exchange,
                    ExchangeType.TOPIC,
                    durable=True,
                )
                self._queue = await channel.declare_queue(
                    f"ff.stream.api.{uuid4().hex[:12]}",
                    exclusive=True,
                    auto_delete=True,
                )
                await self._queue.consume(self._on_message, no_ack=False)
            except Exception:
                logger.exception("流式 AMQP 连接失败，后续 publish/subscribe 将降级丢弃")
                self._connection = None
                self._exchange = None
                self._queue = None
                return None
            return self._exchange

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False, ignore_processed=True):
            try:
                event = StreamEvent.model_validate_json(message.body)
            except Exception:
                logger.warning("流式帧无法解析，丢弃")
                return
            key = message.routing_key or ""
            prefix = "conv."
            if not key.startswith(prefix):
                return
            try:
                conversation_id = UUID(key[len(prefix) :])
            except ValueError:
                return
            for queue in list(self._subs.get(conversation_id, [])):
                _enqueue(queue, event, conversation_id)

    async def publish(self, conversation_id: UUID, event: StreamEvent) -> None:
        cfg = get_settings()
        try:
            exchange = await asyncio.wait_for(
                self._ensure(),
                timeout=cfg.stream_publish_timeout_seconds,
            )
            if exchange is None:
                return
            await asyncio.wait_for(
                exchange.publish(
                    Message(
                        body=event.model_dump_json().encode("utf-8"),
                        delivery_mode=DeliveryMode.NOT_PERSISTENT,
                        content_type="application/json",
                    ),
                    routing_key=routing_key(conversation_id),
                ),
                timeout=cfg.stream_publish_timeout_seconds,
            )
        except Exception:
            logger.warning("流式 publish 失败 conversation_id={}", conversation_id)

    async def subscribe(
        self,
        conversation_id: UUID,
        queue: asyncio.Queue[StreamEvent],
    ) -> None:
        holders = self._subs.setdefault(conversation_id, [])
        if queue not in holders:
            holders.append(queue)
        amqp_queue = None
        exchange = await self._ensure()
        if exchange is None:
            return
        amqp_queue = self._queue
        if amqp_queue is None:
            return
        if len(holders) == 1:
            await amqp_queue.bind(exchange, routing_key=routing_key(conversation_id))

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
        if holders:
            return
        self._subs.pop(conversation_id, None)
        if self._queue is not None and self._exchange is not None:
            try:
                await self._queue.unbind(
                    self._exchange, routing_key=routing_key(conversation_id)
                )
            except Exception:
                logger.warning("流式 unbind 失败 conversation_id={}", conversation_id)

    async def close(self) -> None:
        conn = self._connection
        self._connection = None
        self._exchange = None
        self._queue = None
        if conn is not None:
            await conn.close()
