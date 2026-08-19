"""会话 SSE 流协议状态机。"""

from __future__ import annotations

from enum import StrEnum

from api.sse.protocol import CONTROL_EVENTS, DELTA_EVENTS, SseEvent


class StreamState(StrEnum):
    IDLE = "idle"
    SUBSCRIBED = "subscribed"
    RUN_ACTIVE = "run_active"
    COMPLETED = "completed"
    FAILED = "failed"


class StreamProtocolError(Exception):
    """非法事件或不合法状态转移。"""

    def __init__(self, message: str, *, state: StreamState, event: str) -> None:
        super().__init__(message)
        self.state = state
        self.event = event


_SUBSCRIBE = "subscribe"
_UNSUBSCRIBE = "unsubscribe"


class StreamStateMachine:
    """空闲 → 已订阅 → Run 进行中 → 完成/失败；完成后再提交进入下一轮。"""

    def __init__(self) -> None:
        self.state = StreamState.IDLE
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return str(self._seq)

    def apply_command(self, command: str) -> list[SseEvent]:
        if command == _SUBSCRIBE:
            return self._subscribe()
        if command == _UNSUBSCRIBE:
            return self._unsubscribe()
        raise StreamProtocolError(
            f"未知命令: {command}",
            state=self.state,
            event=command,
        )

    def apply_event(self, event: SseEvent) -> list[SseEvent]:
        name = event.event
        if name == "run_submitted":
            return self._to_run_active(event)
        if name == "run_completed":
            return self._finish(event, StreamState.COMPLETED)
        if name == "run_failed":
            return self._finish(event, StreamState.FAILED)
        if name in DELTA_EVENTS:
            return self._delta(event)
        if name in CONTROL_EVENTS and name == "connected":
            raise StreamProtocolError(
                "connected 只能由 subscribe 产生",
                state=self.state,
                event=name,
            )
        raise StreamProtocolError(f"未知事件: {name}", state=self.state, event=name)

    def _emit(self, event: SseEvent) -> SseEvent:
        if event.id is None:
            return event.model_copy(update={"id": self._next_id()})
        return event

    def _subscribe(self) -> list[SseEvent]:
        if self.state != StreamState.IDLE:
            raise StreamProtocolError("仅 idle 可 subscribe", state=self.state, event=_SUBSCRIBE)
        self.state = StreamState.SUBSCRIBED
        return [self._emit(SseEvent(event="connected", data={"state": self.state.value}))]

    def _unsubscribe(self) -> list[SseEvent]:
        self.state = StreamState.IDLE
        return []

    def _to_run_active(self, event: SseEvent) -> list[SseEvent]:
        if self.state not in {StreamState.SUBSCRIBED, StreamState.COMPLETED, StreamState.FAILED}:
            raise StreamProtocolError(
                "run_submitted 仅允许在 subscribed/completed/failed",
                state=self.state,
                event=event.event,
            )
        self.state = StreamState.RUN_ACTIVE
        return [self._emit(event)]

    def _finish(self, event: SseEvent, target: StreamState) -> list[SseEvent]:
        if self.state != StreamState.RUN_ACTIVE:
            raise StreamProtocolError(
                f"{event.event} 仅允许在 run_active",
                state=self.state,
                event=event.event,
            )
        self.state = target
        return [self._emit(event)]

    def _delta(self, event: SseEvent) -> list[SseEvent]:
        if self.state != StreamState.RUN_ACTIVE:
            raise StreamProtocolError(
                f"{event.event} 仅允许在 run_active",
                state=self.state,
                event=event.event,
            )
        return [self._emit(event)]
