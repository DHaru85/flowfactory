"""观测 flush 集成测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from data_schema.observability.models import ObsPromptSnapshot  # noqa: E402
from service.database.session import session_scope  # noqa: E402
from service.observability.collector import (  # noqa: E402
    TraceCollector,
    attach_collector,
    reset_collector,
)
from service.observability.redact import hash_content, redact_text  # noqa: E402
from service.observability.schemas import (  # noqa: E402
    PromptMessage,
    SpanAttributesPayload,
    ToolTraceRecord,
    TraceContext,
)
from service.persistence.factory import get_repositories  # noqa: E402


@pytest.mark.integration
@pytest.mark.asyncio
async def test_flush_writes_obs_tables() -> None:
    collector = TraceCollector()
    token = attach_collector(collector)
    run_id = uuid4()
    raw_prompt = "账号 user@example.com"
    try:
        collector.start_trace("langgraph.run", TraceContext(run_id=run_id))
        with collector.record_span("chat", SpanAttributesPayload(node_id="chat")):
            collector.record_llm_call(
                model="qwen",
                prompt_tokens=2,
                completion_tokens=3,
                latency_ms=8,
                messages=[PromptMessage(role="user", content=raw_prompt)],
            )
        collector.record_tool(
            ToolTraceRecord(
                trace_id=collector.trace_id,
                tool_code="echo",
                input_summary="in",
                output_summary="out",
                latency_ms=1,
                success=True,
            )
        )
        collector.end_trace("ok")
        otel_id = collector.trace_id
        async with session_scope() as session:
            await collector.flush(session)
        async with session_scope() as session:
            repos = get_repositories(session)
            trace = await repos.observability.get_trace_by_otel_id(otel_id)
            assert trace is not None
            assert trace.run_id == run_id
            spans = await repos.observability.list_spans_by_trace(otel_id)
            names = {item.name for item in spans}
            assert "langgraph.run" in names
            assert "chat" in names
            calls = await repos.observability.list_llm_calls_by_run(run_id)
            assert len(calls) == 1
            assert calls[0].prompt_tokens == 2
            result = await session.scalars(
                select(ObsPromptSnapshot).where(ObsPromptSnapshot.llm_call_id == calls[0].id)
            )
            snapshots = list(result.all())
            assert snapshots
            assert snapshots[0].content_redacted == redact_text(raw_prompt)
            assert snapshots[0].content_hash == hash_content(raw_prompt)
            assert "user@example.com" not in snapshots[0].content_redacted
    finally:
        reset_collector(token)
