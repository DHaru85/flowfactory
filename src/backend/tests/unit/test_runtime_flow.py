"""FlowRuntime 编译与 HITL / LLM 节点（内存 checkpointer）。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.runtime.flow import FlowRuntime  # noqa: E402
from service.runtime.llm import FakeChatCompletionClient  # noqa: E402
from service.runtime.schemas import FlowDefinitionDocument, RunStatePayload  # noqa: E402


def _passthrough_doc() -> FlowDefinitionDocument:
    return FlowDefinitionDocument(
        nodes=[{"id": "a", "kind": "passthrough"}],
        edges=[{"source": "a", "target": "END"}],
        entry_point="a",
    )


def _interrupt_doc() -> FlowDefinitionDocument:
    return FlowDefinitionDocument(
        nodes=[{"id": "ask", "kind": "interrupt", "prompt": "确认执行?"}],
        edges=[{"source": "ask", "target": "END"}],
        entry_point="ask",
    )


def _llm_doc() -> FlowDefinitionDocument:
    return FlowDefinitionDocument(
        nodes=[{"id": "chat", "kind": "llm"}],
        edges=[{"source": "chat", "target": "END"}],
        entry_point="chat",
    )


@pytest.mark.asyncio
async def test_passthrough_graph_completes() -> None:
    runtime = FlowRuntime.compile(
        _passthrough_doc(),
        flow_id=uuid4(),
        checkpointer=InMemorySaver(),
    )
    result = await runtime.graph.ainvoke(
        RunStatePayload(variables={"input": "hi"}).to_graph_state(),
        {"configurable": {"thread_id": "t-pass"}},
    )
    assert result["variables"]["input"] == "hi"
    snap = await runtime.graph.aget_state({"configurable": {"thread_id": "t-pass"}})
    assert snap.next == ()


@pytest.mark.asyncio
async def test_interrupt_then_resume() -> None:
    runtime = FlowRuntime.compile(
        _interrupt_doc(),
        flow_id=uuid4(),
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "t-hitl"}}
    first = await runtime.graph.ainvoke(
        RunStatePayload(variables={"input": "need-hitl"}).to_graph_state(),
        config,
    )
    assert "__interrupt__" in first
    snap = await runtime.graph.aget_state(config)
    assert snap.next == ("ask",)
    second = await runtime.graph.ainvoke(Command(resume="approve"), config)
    assert second["variables"]["hitl_resume"] == "approve"
    snap2 = await runtime.graph.aget_state(config)
    assert snap2.next == ()


@pytest.mark.asyncio
async def test_llm_node_uses_injected_client() -> None:
    fake = FakeChatCompletionClient("模型回复")
    runtime = FlowRuntime.compile(
        _llm_doc(),
        flow_id=uuid4(),
        checkpointer=InMemorySaver(),
        chat_client=fake,
    )
    result = await runtime.graph.ainvoke(
        RunStatePayload(variables={"input": "你好"}).to_graph_state(),
        {"configurable": {"thread_id": "t-llm"}},
    )
    assert fake.calls
    assert result["variables"]["last_output"] == "模型回复"
