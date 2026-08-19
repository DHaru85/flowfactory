"""内存 MCP 替身。"""

from __future__ import annotations

from collections.abc import Callable


class FakeMcpClientSession:
    def __init__(self) -> None:
        self.connected = False
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._handlers: dict[str, Callable[[dict[str, object]], object]] = {}

    def register(self, name: str, handler: Callable[[dict[str, object]], object]) -> None:
        self._handlers[name] = handler

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append((name, dict(arguments)))
        handler = self._handlers.get(name)
        if handler is None:
            raise LookupError(f"MCP 工具不存在: {name}")
        return handler(arguments)
