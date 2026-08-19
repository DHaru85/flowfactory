"""按 agent_tool.kind 分发工具调用。"""

from __future__ import annotations

from time import perf_counter
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from service.observability.observe_tool import observe_tool_call
from service.persistence.factory import get_repositories
from service.tools.http import HttpToolTransport, get_http_transport
from service.tools.mcp.factory import get_mcp_session
from service.tools.mcp.protocol import McpClientSession
from service.tools.registry import get_builtin_handler
from service.tools.schemas import ToolCallRequest, ToolCallResult
from service.tools.validate import validate_tool_arguments


class ToolExecutor:
    """builtin / http / mcp 分发。业务失败返回 Result，不抛给规划层。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        http_transport: HttpToolTransport | None = None,
        mcp_session: McpClientSession | None = None,
    ) -> None:
        if session is None:
            raise TypeError("session 不能为空")
        self._session = session
        self._http = http_transport
        self._mcp = mcp_session

    async def execute(self, request: ToolCallRequest) -> ToolCallResult:
        started = perf_counter()
        try:
            result = await self._dispatch(request)
        except Exception as exc:
            logger.exception("工具执行异常 tool_code={}", request.tool_code)
            result = ToolCallResult(
                tool_call_id=request.tool_call_id,
                success=False,
                error=str(exc),
            )
        latency_ms = int((perf_counter() - started) * 1000)
        observe_tool_call(
            tool_code=request.tool_code,
            arguments=request.arguments,
            result_output=result.output if result.success else result.error,
            latency_ms=latency_ms,
            success=result.success,
        )
        return result

    async def _dispatch(self, request: ToolCallRequest) -> ToolCallResult:
        repos = get_repositories(self._session)
        tool = await repos.agent.get_tool_by_code(request.tool_code)
        if tool is None:
            return ToolCallResult(
                tool_call_id=request.tool_call_id,
                success=False,
                error=f"工具不存在: {request.tool_code}",
            )
        schema_error = validate_tool_arguments(tool.schema_, request.arguments)
        if schema_error:
            return ToolCallResult(
                tool_call_id=request.tool_call_id,
                success=False,
                error=schema_error,
            )
        kind = tool.kind
        if kind == "builtin":
            return await self._run_builtin(request, tool.config)
        if kind == "http":
            return await self._run_http(request, tool.config)
        if kind == "mcp":
            return await self._run_mcp(request, tool.config, tool.mcp_server_id)
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            success=False,
            error=f"未知工具 kind: {kind}",
        )

    async def _run_builtin(
        self,
        request: ToolCallRequest,
        config: dict[str, object],
    ) -> ToolCallResult:
        handler_code = str(config.get("handler") or request.tool_code)
        handler = get_builtin_handler(handler_code)
        if handler is None:
            return ToolCallResult(
                tool_call_id=request.tool_call_id,
                success=False,
                error=f"未注册的 builtin handler: {handler_code}",
            )
        output = await handler(self._session, request.arguments)
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            success=True,
            output=output,
        )

    async def _run_http(
        self,
        request: ToolCallRequest,
        config: dict[str, object],
    ) -> ToolCallResult:
        transport = self._http or get_http_transport()
        status, body = await transport.request(config, request.arguments)
        if status >= 400:
            return ToolCallResult(
                tool_call_id=request.tool_call_id,
                success=False,
                output={"status": status, "body": body},
                error=f"HTTP {status}",
            )
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            success=True,
            output=body,
        )

    async def _run_mcp(
        self,
        request: ToolCallRequest,
        config: dict[str, object],
        mcp_server_id: UUID | None,
    ) -> ToolCallResult:
        repos = get_repositories(self._session)
        server = None
        if mcp_server_id is not None:
            server = await repos.agent.get_mcp_server(mcp_server_id)
        session = self._mcp or get_mcp_session(server)
        remote_name = str(config.get("mcp_tool") or request.tool_code)
        output = await session.call_tool(remote_name, request.arguments)
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            success=True,
            output=output,
        )
