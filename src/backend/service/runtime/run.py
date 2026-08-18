"""Run 可运行对象。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.workflow.models import RunSnapshot
from service.runtime.checkpoint import CheckpointInstance
from service.runtime.flow import FlowRuntime
from service.runtime.schemas import HitlResumeInput, StartRunRequest
from service.runtime.thread import Thread


class Run:
    def __init__(
        self,
        snapshot: RunSnapshot,
        thread: Thread,
        flow_runtime: FlowRuntime | None = None,
        checkpoint_instance: CheckpointInstance | None = None,
    ) -> None:
        self.id: UUID = snapshot.id
        self.flow_runtime = flow_runtime
        self.thread = thread
        self.checkpoint_instance = checkpoint_instance
        self._snapshot = snapshot

    async def start(self) -> UUID:
        from service.runtime.scheduler import start_run
        from service.runtime.schemas import RunStatePayload

        payload = RunStatePayload.model_validate(self._snapshot.input_payload)
        return await start_run(
            StartRunRequest(
                user_id=self._snapshot.user_id,
                flow_id=self._snapshot.flow_id,
                input_payload=payload,
                conversation_id=self._snapshot.conversation_id,
            )
        )

    async def resume(self, hitl: HitlResumeInput) -> None:
        from service.orchestration.factory import get_orchestrator

        await get_orchestrator().resume_run(hitl)

    async def cancel(self) -> None:
        from service.runtime.scheduler import cancel_run

        await cancel_run(self.id)

    async def persist(self, session: AsyncSession) -> None:
        await session.flush()
