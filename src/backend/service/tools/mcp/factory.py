"""MCP 会话工厂。"""

from __future__ import annotations

from data_schema.agent.models import AgentMcpServer
from service.tools.mcp.fake import FakeMcpClientSession
from service.tools.mcp.protocol import McpClientSession
from service.tools.mcp.sdk import SdkMcpClientSession

_override: McpClientSession | None = None


def set_mcp_session_override(session: McpClientSession | None) -> None:
    global _override
    _override = session


def get_mcp_session(server: AgentMcpServer | None = None) -> McpClientSession:
    if _override is not None:
        return _override
    if server is None:
        return FakeMcpClientSession()
    return SdkMcpClientSession(transport=server.transport, config=server.config)
