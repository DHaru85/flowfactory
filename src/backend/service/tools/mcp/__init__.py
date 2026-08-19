"""MCP 接入预留。"""

from service.tools.mcp.factory import get_mcp_session, set_mcp_session_override
from service.tools.mcp.fake import FakeMcpClientSession
from service.tools.mcp.sdk import SdkMcpClientSession

__all__ = [
    "FakeMcpClientSession",
    "SdkMcpClientSession",
    "get_mcp_session",
    "set_mcp_session_override",
]
