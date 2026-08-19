"""内置工具注册表。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from service.tools.builtin import kb_retrieve

BuiltinHandler = Callable[[AsyncSession, dict[str, object]], Awaitable[object]]

_HANDLERS: dict[str, BuiltinHandler] = {
    "kb_retrieve": kb_retrieve,
}


def register_builtin(code: str, handler: BuiltinHandler) -> None:
    _HANDLERS[code] = handler


def get_builtin_handler(code: str) -> BuiltinHandler | None:
    return _HANDLERS.get(code)
