"""SSE 协议状态机单元测试。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.sse.machine import StreamProtocolError, StreamState, StreamStateMachine  # noqa: E402
from api.sse.protocol import SseEvent, format_sse, speaking_event  # noqa: E402


def test_happy_path_and_next_turn() -> None:
    sm = StreamStateMachine()
    connected = sm.apply_command("subscribe")
    assert sm.state == StreamState.SUBSCRIBED
    assert connected[0].event == "connected"
    assert connected[0].id == "1"

    submitted = sm.apply_event(SseEvent(event="run_submitted", data={"run_id": "r"}))
    assert sm.state == StreamState.RUN_ACTIVE
    assert submitted[0].id == "2"

    mid = uuid4()
    spoken = sm.apply_event(speaking_event(delta="你", message_id=mid))
    assert spoken[0].event == "speaking"
    assert sm.state == StreamState.RUN_ACTIVE

    sm.apply_event(SseEvent(event="run_completed", data={}))
    assert sm.state == StreamState.COMPLETED

    sm.apply_event(SseEvent(event="run_submitted", data={"run_id": "r2"}))
    assert sm.state == StreamState.RUN_ACTIVE

    sm.apply_command("unsubscribe")
    assert sm.state == StreamState.IDLE


def test_illegal_delta_before_run() -> None:
    sm = StreamStateMachine()
    sm.apply_command("subscribe")
    with pytest.raises(StreamProtocolError) as exc:
        sm.apply_event(SseEvent(event="speaking", data={"delta": "x"}))
    assert exc.value.state == StreamState.SUBSCRIBED


def test_format_sse_frame() -> None:
    frame = format_sse(SseEvent(event="speaking", data={"delta": "hi"}, id="3"))
    assert "event: speaking\n" in frame
    assert "id: 3\n" in frame
    assert 'data: {"delta": "hi"}' in frame
    assert frame.endswith("\n\n")


@pytest.mark.asyncio
async def test_conversation_sse_iter_bus_inject() -> None:
    from api.sse.bus import InMemorySseBus, set_sse_bus_override
    from api.sse.stream import conversation_sse_iter

    bus = InMemorySseBus()
    set_sse_bus_override(bus)
    cid = uuid4()
    agen = conversation_sse_iter(cid)
    try:
        first = await asyncio.wait_for(anext(agen), timeout=2)
        assert "event: connected" in first
        await bus.publish(cid, SseEvent(event="run_submitted", data={"run_id": "r"}))
        second = await asyncio.wait_for(anext(agen), timeout=2)
        assert "event: run_submitted" in second
    finally:
        await agen.aclose()
        set_sse_bus_override(None)
