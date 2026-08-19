"""官方 MCP SDK 适配。缺配置不在 import 期崩溃。"""

from __future__ import annotations

from loguru import logger


class SdkMcpClientSession:
    """stdio / sse 真实接入预留；本轮默认不 connect。"""

    def __init__(
        self,
        *,
        transport: str = "stdio",
        config: dict[str, object] | None = None,
    ) -> None:
        self._transport = transport
        self._config = config or {}
        self._connected = False

    async def connect(self) -> None:
        try:
            import mcp  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("未安装 mcp") from exc
        if self._transport not in {"stdio", "sse"}:
            raise RuntimeError(f"不支持的 MCP transport: {self._transport}")
        command = self._config.get("command")
        url = self._config.get("url")
        if self._transport == "stdio" and not command:
            raise RuntimeError("stdio MCP 未配置 command")
        if self._transport == "sse" and not url:
            raise RuntimeError("sse MCP 未配置 url")
        logger.info("MCP SDK 会话骨架 connect transport={}", self._transport)
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        if not self._connected:
            await self.connect()
        raise RuntimeError(
            f"MCP SDK 本轮仅预留接入，未执行真实 call_tool name={name}"
        )
