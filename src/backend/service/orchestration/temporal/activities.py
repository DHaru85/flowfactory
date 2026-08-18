"""Temporal Activity：只调用服务层，不写图内 checkpoint。"""

from __future__ import annotations

from uuid import UUID

from temporalio import activity

from service.runtime.schemas import HitlResumeInput, StartRunRequest


@activity.defn(name="start_run_activity")
async def start_run_activity(payload: dict[str, object]) -> str:
    from service.orchestration.passthrough import PassthroughOrchestrator

    request = StartRunRequest.model_validate(payload)
    run_id = await PassthroughOrchestrator().start_run(request)
    return str(run_id)


@activity.defn(name="resume_run_activity")
async def resume_run_activity(payload: dict[str, object]) -> dict[str, object]:
    from service.orchestration.passthrough import PassthroughOrchestrator

    hitl = HitlResumeInput.model_validate(payload)
    output = await PassthroughOrchestrator().resume_run(hitl)
    return output.model_dump(mode="json")


@activity.defn(name="cancel_run_activity")
async def cancel_run_activity(run_id: str) -> None:
    from service.orchestration.passthrough import PassthroughOrchestrator

    await PassthroughOrchestrator().cancel_run(UUID(run_id))
