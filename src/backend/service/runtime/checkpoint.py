"""CheckpointInstance：从 checkpointer hydrate 的图状态内存对象。"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from loguru import logger

from service.runtime.schemas import RunStatePayload


class CheckpointInstance:
    def __init__(
        self,
        thread_id: str,
        state: dict[str, object],
        checkpoint_id: str,
    ) -> None:
        self.thread_id = thread_id
        self.state = state
        self.checkpoint_id = checkpoint_id

    @classmethod
    async def load(
        cls,
        checkpointer: BaseCheckpointSaver,
        thread_id: str,
    ) -> CheckpointInstance | None:
        config = {"configurable": {"thread_id": thread_id}}
        tup = await checkpointer.aget_tuple(config)
        if tup is None:
            return None
        channel_values = dict(tup.checkpoint.get("channel_values") or {})
        checkpoint_id = str(tup.checkpoint.get("id") or "")
        return cls(thread_id=thread_id, state=channel_values, checkpoint_id=checkpoint_id)

    def apply_delta(self, delta: dict[str, object]) -> None:
        self.state.update(delta)

    async def save(self, checkpointer: BaseCheckpointSaver) -> None:
        logger.debug(
            "CheckpointInstance.save 委托 LangGraph thread_id={} id={}",
            self.thread_id,
            self.checkpoint_id,
        )
        _ = checkpointer

    def as_payload(self) -> RunStatePayload:
        return RunStatePayload.from_graph_state(self.state)
