"""ToolExecutor 分发单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.knowledge.schemas import SearchHit, SearchHitList  # noqa: E402
from service.observability.collector import (  # noqa: E402
    TraceCollector,
    attach_collector,
    reset_collector,
)
from service.observability.schemas import TraceContext  # noqa: E402
from service.tools.executor import ToolExecutor  # noqa: E402
from service.tools.http import HttpxToolTransport  # noqa: E402
from service.tools.mcp.fake import FakeMcpClientSession  # noqa: E402
from service.tools.mcp.sdk import SdkMcpClientSession  # noqa: E402
from service.tools.schemas import ToolCallRequest  # noqa: E402


def _tool(
    *,
    kind: str,
    schema: dict[str, object] | None = None,
    config: dict[str, object] | None = None,
    mcp_server_id: object = None,
) -> MagicMock:
    tool = MagicMock()
    tool.schema_ = schema or {}
    tool.kind = kind
    tool.config = config or {}
    tool.mcp_server_id = mcp_server_id
    return tool


def _repos(tool: MagicMock | None) -> MagicMock:
    repos = MagicMock()
    repos.agent.get_tool_by_code = AsyncMock(return_value=tool)
    repos.agent.get_mcp_server = AsyncMock(return_value=None)
    return repos


def test_session_required() -> None:
    with pytest.raises(TypeError):
        ToolExecutor(None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_unknown_tool_returns_failure() -> None:
    repos = _repos(None)
    with patch("service.tools.executor.get_repositories", return_value=repos):
        result = await ToolExecutor(MagicMock()).execute(
            ToolCallRequest(tool_call_id="c1", tool_code="missing")
        )
    assert result.success is False
    assert result.error is not None
    assert "不存在" in result.error


@pytest.mark.asyncio
async def test_schema_validation_failure() -> None:
    tool = _tool(
        kind="builtin",
        schema={
            "type": "object",
            "required": ["query_text"],
            "properties": {"query_text": {"type": "string"}},
        },
    )
    repos = _repos(tool)
    with patch("service.tools.executor.get_repositories", return_value=repos):
        result = await ToolExecutor(MagicMock()).execute(
            ToolCallRequest(tool_call_id="c1", tool_code="kb_retrieve", arguments={})
        )
    assert result.success is False
    assert result.error is not None
    assert "校验" in result.error


@pytest.mark.asyncio
async def test_unknown_kind() -> None:
    repos = _repos(_tool(kind="rpc"))
    with patch("service.tools.executor.get_repositories", return_value=repos):
        result = await ToolExecutor(MagicMock()).execute(
            ToolCallRequest(tool_call_id="c1", tool_code="x")
        )
    assert result.success is False
    assert result.error is not None
    assert "kind" in result.error


@pytest.mark.asyncio
async def test_kb_retrieve_builtin() -> None:
    tool = _tool(kind="builtin", config={"handler": "kb_retrieve"})
    repos = _repos(tool)
    hits = SearchHitList(
        hits=[
            SearchHit(
                chunk_id=uuid4(),
                doc_id=uuid4(),
                score=0.9,
                source="vector",
                snippet="片段",
            )
        ]
    )
    with (
        patch("service.tools.executor.get_repositories", return_value=repos),
        patch(
            "service.tools.builtin.RetrievalService.search",
            new=AsyncMock(return_value=hits),
        ),
    ):
        result = await ToolExecutor(MagicMock()).execute(
            ToolCallRequest(
                tool_call_id="c1",
                tool_code="kb_retrieve",
                arguments={
                    "query_text": "你好",
                    "collection_ids": [str(uuid4())],
                },
            )
        )
    assert result.success is True
    assert isinstance(result.output, list)
    assert result.output[0]["snippet"] == "片段"
    assert "content" not in result.output[0]


@pytest.mark.asyncio
async def test_http_url_from_config_only() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = _tool(
        kind="http",
        config={"url": "https://example.test/hook", "method": "POST", "param_in": "body"},
    )
    repos = _repos(tool)
    try:
        with patch("service.tools.executor.get_repositories", return_value=repos):
            result = await ToolExecutor(
                MagicMock(),
                http_transport=HttpxToolTransport(client),
            ).execute(
                ToolCallRequest(
                    tool_call_id="c1",
                    tool_code="webhook",
                    arguments={"url": "https://evil.test/steal", "q": "1"},
                )
            )
    finally:
        await client.aclose()
    assert result.success is True
    assert seen == ["https://example.test/hook"]
    assert result.output == {"ok": True}


@pytest.mark.asyncio
async def test_mcp_fake_session() -> None:
    fake = FakeMcpClientSession()
    fake.register("echo", lambda args: {"echo": args.get("text")})
    tool = _tool(kind="mcp", config={"mcp_tool": "echo"})
    repos = _repos(tool)
    with patch("service.tools.executor.get_repositories", return_value=repos):
        result = await ToolExecutor(MagicMock(), mcp_session=fake).execute(
            ToolCallRequest(
                tool_call_id="c1",
                tool_code="echo",
                arguments={"text": "hi"},
            )
        )
    assert result.success is True
    assert result.output == {"echo": "hi"}
    assert fake.calls[0][0] == "echo"


@pytest.mark.asyncio
async def test_sdk_mcp_constructs_without_connecting() -> None:
    session = SdkMcpClientSession(transport="stdio", config={})
    with pytest.raises(RuntimeError, match="command"):
        await session.call_tool("x", {})


@pytest.mark.asyncio
async def test_execute_records_tool_when_collector_active() -> None:
    repos = _repos(_tool(kind="builtin", config={"handler": "missing"}))
    collector = TraceCollector()
    token = attach_collector(collector)
    collector.start_trace("langgraph.run", TraceContext())
    try:
        with patch("service.tools.executor.get_repositories", return_value=repos):
            await ToolExecutor(MagicMock()).execute(
                ToolCallRequest(tool_call_id="c1", tool_code="no-handler")
            )
        collector.end_trace("ok")
        assert collector.pending_tool_count() == 1
    finally:
        reset_collector(token)
