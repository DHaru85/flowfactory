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
