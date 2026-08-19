"""MCP 客户端协议。实现不得依赖 ORM。"""

from __future__ import annotations

from typing import Protocol


class McpClientSession(Protocol):
    async def connect(self) -> None:
        """建立会话。"""

    async def close(self) -> None:
        """关闭会话。"""

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """远程工具调用。"""
