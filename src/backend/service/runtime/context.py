"""图节点执行上下文（worker 注入；compile 纯函数不查库）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID

from service.tools.schemas import ToolCallRequest, ToolCallResult

ToolExecuteFn = Callable[[ToolCallRequest], Awaitable[ToolCallResult]]


@dataclass
class GraphExecContext:
    run_id: UUID | None = None
    user_id: UUID | None = None
    conversation_id: UUID | None = None
    flow_id: UUID | None = None
    is_first_invoke: bool = True
    tool_execute: ToolExecuteFn | None = None


_CTX: ContextVar[GraphExecContext | None] = ContextVar("graph_exec_ctx", default=None)


def attach_graph_exec_ctx(ctx: GraphExecContext) -> Token[GraphExecContext | None]:
    return _CTX.set(ctx)


def reset_graph_exec_ctx(token: Token[GraphExecContext | None]) -> None:
    _CTX.reset(token)


def get_graph_exec_ctx() -> GraphExecContext | None:
    return _CTX.get()
