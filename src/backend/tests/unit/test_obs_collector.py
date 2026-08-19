"""TraceCollector 与节点包装。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.observability.collector import (  # noqa: E402
    TraceCollector,
    attach_collector,
    reset_collector,
)
from service.observability.langfuse.factory import set_langfuse_reporter_override  # noqa: E402
from service.observability.langfuse.fake import FakeLangfuseReporter  # noqa: E402
from service.observability.redact import hash_content  # noqa: E402
from service.observability.schemas import (  # noqa: E402
    PromptMessage,
    SpanAttributesPayload,
    ToolTraceRecord,
    TraceContext,
)
from service.runtime.flow import FlowRuntime  # noqa: E402
from service.runtime.llm import FakeChatCompletionClient  # noqa: E402
from service.runtime.schemas import FlowDefinitionDocument, RunStatePayload  # noqa: E402


def test_collector_buffers_without_otlp() -> None:
    fake = FakeLangfuseReporter()
    set_langfuse_reporter_override(fake)
    collector = TraceCollector()
    token = attach_collector(collector)
    try:
        collector.start_trace("langgraph.run", TraceContext(run_id=uuid4()))
        attrs = SpanAttributesPayload(node_id="chat", extra={"kind": "llm"})
        with collector.record_span("chat", attrs):
            collector.record_llm_call(
                model="qwen",
                prompt_tokens=3,
                completion_tokens=5,
                latency_ms=9,
                messages=[PromptMessage(role="user", content="mail a@b.com")],
            )
        collector.record_tool(
            ToolTraceRecord(
                trace_id=collector.trace_id,
                tool_code="noop",
                input_summary="in",
                output_summary="out",
                latency_ms=1,
                success=True,
            )
        )
        collector.end_trace("ok")
        names = collector.ended_span_names()
        assert "langgraph.run" in names
        assert "chat" in names
        assert collector.pending_llm_count() == 1
        assert collector.pending_tool_count() == 1
        assert fake.generations
        assert fake.tools
        assert hash_content("mail a@b.com")
    finally:
        reset_collector(token)
        set_langfuse_reporter_override(None)


@pytest.mark.asyncio
async def test_compile_wrap_records_node_and_usage() -> None:
    fake_llm = FakeChatCompletionClient("模型回复")
    collector = TraceCollector()
    token = attach_collector(collector)
    collector.start_trace("langgraph.run", TraceContext())
    try:
        runtime = FlowRuntime.compile(
            FlowDefinitionDocument(
                nodes=[{"id": "chat", "kind": "llm"}],
                edges=[{"source": "chat", "target": "END"}],
                entry_point="chat",
            ),
            flow_id=uuid4(),
            checkpointer=InMemorySaver(),
            chat_client=fake_llm,
        )
        result = await runtime.graph.ainvoke(
            RunStatePayload(variables={"input": "你好"}).to_graph_state(),
            {"configurable": {"thread_id": "t-obs-llm"}},
        )
        collector.end_trace("ok")
        assert result["variables"]["last_output"] == "模型回复"
        assert "chat" in collector.ended_span_names()
        assert collector.pending_llm_count() == 1
    finally:
        reset_collector(token)


@pytest.mark.asyncio
async def test_hitl_interrupt_ends_span_this_turn() -> None:
    collector = TraceCollector()
    token = attach_collector(collector)
    collector.start_trace("langgraph.run", TraceContext())
    try:
        runtime = FlowRuntime.compile(
            FlowDefinitionDocument(
                nodes=[{"id": "ask", "kind": "interrupt", "prompt": "确认?"}],
                edges=[{"source": "ask", "target": "END"}],
                entry_point="ask",
            ),
            flow_id=uuid4(),
            checkpointer=InMemorySaver(),
        )
        first = await runtime.graph.ainvoke(
            RunStatePayload(variables={"input": "x"}).to_graph_state(),
            {"configurable": {"thread_id": "t-obs-hitl"}},
        )
        collector.end_trace("ok")
        assert "__interrupt__" in first
        assert "ask" in collector.ended_span_names()
    finally:
        reset_collector(token)
