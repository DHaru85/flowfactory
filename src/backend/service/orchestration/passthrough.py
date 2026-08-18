"""默认外层编排：直连 Celery / Run 服务。"""

from __future__ import annotations

from uuid import UUID

from service.database.session import session_scope
from service.orchestration.protocol import OuterOrchestrator
from service.runtime.hitl import apply_resume_decision
from service.runtime.scheduler import cancel_run, enqueue_resume, start_run
from service.runtime.schemas import (
    HitlResumeInput,
    HitlResumeOutput,
    RunStatePayload,
    StartRunRequest,
)


class PassthroughOrchestrator(OuterOrchestrator):
    async def start_run(self, request: StartRunRequest) -> UUID:
        return await start_run(request)

    async def resume_run(self, hitl: HitlResumeInput) -> HitlResumeOutput:
        async with session_scope() as session:
            _pending, run, output = await apply_resume_decision(session, hitl)
            input_payload = RunStatePayload.model_validate(run.input_payload)
            should_enqueue = output.resumed
        if should_enqueue:
            await enqueue_resume(run=run, hitl=hitl, input_payload=input_payload)
        return output

    async def cancel_run(self, run_id: UUID) -> None:
        await cancel_run(run_id)

    async def signal_hitl(self, hitl: HitlResumeInput) -> None:
        await self.resume_run(hitl)
