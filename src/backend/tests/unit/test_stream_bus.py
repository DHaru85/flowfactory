"""流式总线 Fake 与 llm 节点 speaking 投递。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.events.context import (  # noqa: E402
    StreamPublishContext,
    attach_stream_ctx,
    reset_stream_ctx,
)
from service.events.factory import set_stream_bus_override  # noqa: E402
from service.events.fake import FakeStreamEventBus  # noqa: E402
from service.runtime.flow import FlowRuntime  # noqa: E402
from service.runtime.llm import FakeChatCompletionClient  # noqa: E402
from service.runtime.schemas import FlowDefinitionDocument, RunStatePayload  # noqa: E402


def test_openai_client_rejects_non_http_base_url() -> None:
    from service.runtime.llm import OpenAICompatClient

    with pytest.raises(ValueError, match="http"):
        OpenAICompatClient(base_url="htttp://example.invalid/v1")


@pytest.mark.asyncio
async def test_fake_bus_drops_when_queue_full() -> None:
    bus = FakeStreamEventBus()
    cid = uuid4()
    queue: object
    import asyncio

    queue = asyncio.Queue(maxsize=1)
    await bus.subscribe(cid, queue)  # type: ignore[arg-type]
    from service.events.schemas import StreamEvent

    await bus.publish(cid, StreamEvent(event="a", data={}))
    await bus.publish(cid, StreamEvent(event="b", data={}))
    assert queue.qsize() == 1  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_llm_node_publishes_speaking_chunks() -> None:
    bus = FakeStreamEventBus()
    set_stream_bus_override(bus)
    cid = uuid4()
    mid = uuid4()
    run_id = uuid4()
    token = attach_stream_ctx(
        StreamPublishContext(conversation_id=cid, run_id=run_id, message_id=mid)
    )
    fake = FakeChatCompletionClient(chunks=["你", "好"])
    runtime = FlowRuntime.compile(
        FlowDefinitionDocument(
            nodes=[{"id": "chat", "kind": "llm"}],
            edges=[{"source": "chat", "target": "END"}],
            entry_point="chat",
        ),
        flow_id=uuid4(),
        checkpointer=InMemorySaver(),
        chat_client=fake,
    )
    try:
        result = await runtime.graph.ainvoke(
            RunStatePayload(variables={"input": "hi"}).to_graph_state(),
            {"configurable": {"thread_id": "t-stream"}},
        )
        assert result["variables"]["last_output"] == "你好"
        events = [item[1].event for item in bus.published]
        assert events.count("speaking") == 2
        speaking = [item[1] for item in bus.published if item[1].event == "speaking"]
        deltas = [item.data.get("delta") for item in speaking]
        assert deltas == ["你", "好"]
    finally:
        reset_stream_ctx(token)
        set_stream_bus_override(None)


@pytest.mark.asyncio
async def test_llm_node_publishes_reasoning_chunks() -> None:
    bus = FakeStreamEventBus()
    set_stream_bus_override(bus)
    cid = uuid4()
    mid = uuid4()
    token = attach_stream_ctx(
        StreamPublishContext(conversation_id=cid, run_id=uuid4(), message_id=mid)
    )
    fake = FakeChatCompletionClient(chunks=["答案"], reasoning_chunks=["先", "想"])
    runtime = FlowRuntime.compile(
        FlowDefinitionDocument(
            nodes=[{"id": "chat", "kind": "llm"}],
            edges=[{"source": "chat", "target": "END"}],
            entry_point="chat",
        ),
        flow_id=uuid4(),
        checkpointer=InMemorySaver(),
        chat_client=fake,
    )
    try:
        result = await runtime.graph.ainvoke(
            RunStatePayload(variables={"input": "hi"}).to_graph_state(),
            {"configurable": {"thread_id": "t-reason"}},
        )
        assert result["variables"]["last_output"] == "答案"
        assert result["variables"]["last_reasoning"] == "先想"
        reasoning = [item[1] for item in bus.published if item[1].event == "reasoning"]
        speaking = [item[1] for item in bus.published if item[1].event == "speaking"]
        assert [item.data.get("delta") for item in reasoning] == ["先", "想"]
        assert [item.data.get("delta") for item in speaking] == ["答案"]
        assert all(item.data.get("message_id") == str(mid) for item in reasoning)
    finally:
        reset_stream_ctx(token)
        set_stream_bus_override(None)


def test_think_tag_splitter_incremental() -> None:
    from service.runtime.llm import ThinkTagSplitter

    splitter = ThinkTagSplitter()
    kinds: list[tuple[str, str]] = []
    for piece in ["<", "think>", "先想", "</th", "ink>", "答案"]:
        for part in splitter.feed(piece):
            kinds.append((part.kind, part.text))
    for part in splitter.flush():
        kinds.append((part.kind, part.text))
    reasoning = "".join(text for kind, text in kinds if kind == "reasoning")
    speaking = "".join(text for kind, text in kinds if kind == "speaking")
    assert reasoning == "先想"
    assert speaking == "答案"
