"""基于 Temporal 的外层编排（可选）。"""

from __future__ import annotations

from uuid import UUID, uuid4

from service.orchestration.protocol import OuterOrchestrator
from service.orchestration.temporal.client import get_temporal_client
from service.orchestration.temporal.workflows import OuterSagaWorkflow
from service.runtime.schemas import HitlResumeInput, HitlResumeOutput, StartRunRequest
from settings.config import get_settings


class TemporalOrchestrator(OuterOrchestrator):
    async def start_run(self, request: StartRunRequest) -> UUID:
        cfg = get_settings()
        client = await get_temporal_client()
        workflow_id = f"saga-{uuid4()}"
        await client.start_workflow(
            OuterSagaWorkflow.run,
            request.model_dump(mode="json"),
            id=workflow_id,
            task_queue=cfg.temporal_task_queue,
        )
        return UUID(workflow_id.removeprefix("saga-"))

    async def resume_run(self, hitl: HitlResumeInput) -> HitlResumeOutput:
        await self.signal_hitl(hitl)
        return HitlResumeOutput(run_id=UUID(int=0), resumed=True)

    async def cancel_run(self, run_id: UUID) -> None:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(f"saga-{run_id}")
        await handle.signal(OuterSagaWorkflow.cancel)

    async def signal_hitl(self, hitl: HitlResumeInput) -> None:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(f"saga-{hitl.hitl_id}")
        await handle.signal(OuterSagaWorkflow.hitl_resume, hitl.model_dump(mode="json"))
