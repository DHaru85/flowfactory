"""工具分发服务层。"""

from service.tools.executor import ToolExecutor
from service.tools.http import HttpxToolTransport, get_http_transport, set_http_transport_override
from service.tools.mcp import (
    FakeMcpClientSession,
    SdkMcpClientSession,
    get_mcp_session,
    set_mcp_session_override,
)
from service.tools.registry import get_builtin_handler, register_builtin
from service.tools.schemas import ToolCallRequest, ToolCallResult

__all__ = [
    "ToolExecutor",
    "ToolCallRequest",
    "ToolCallResult",
    "FakeMcpClientSession",
    "SdkMcpClientSession",
    "HttpxToolTransport",
    "get_builtin_handler",
    "get_http_transport",
    "get_mcp_session",
    "register_builtin",
    "set_http_transport_override",
    "set_mcp_session_override",
]
