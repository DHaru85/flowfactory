"""运行时门面：应用层调用入口。"""

from uuid import UUID

from service.orchestration.factory import get_orchestrator
from service.runtime.schemas import HitlResumeInput, HitlResumeOutput, StartRunRequest


class WorkflowRuntimeService:
    async def start(self, request: StartRunRequest) -> UUID:
        return await get_orchestrator().start_run(request)

    async def resume(self, hitl: HitlResumeInput) -> HitlResumeOutput:
        return await get_orchestrator().resume_run(hitl)

    async def cancel(self, run_id: UUID) -> None:
        await get_orchestrator().cancel_run(run_id)
