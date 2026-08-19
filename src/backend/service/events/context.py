"""流式发布现场（worker 内 ContextVar）。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID

_ctx: ContextVar[StreamPublishContext | None] = ContextVar("stream_publish_ctx", default=None)


@dataclass(frozen=True)
class StreamPublishContext:
    conversation_id: UUID | None
    run_id: UUID
    message_id: UUID | None


def attach_stream_ctx(ctx: StreamPublishContext) -> Token[StreamPublishContext | None]:
    return _ctx.set(ctx)


def reset_stream_ctx(token: Token[StreamPublishContext | None]) -> None:
    _ctx.reset(token)


def get_stream_ctx() -> StreamPublishContext | None:
    return _ctx.get()


def reset_stream_context() -> None:
    _ctx.set(None)
