"""Temporal 长 saga 骨架：Activity 内驱动 Celery，等待 HITL 信号。"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from service.orchestration.temporal.activities import (
        cancel_run_activity,
        resume_run_activity,
        start_run_activity,
    )


@workflow.defn(name="OuterSagaWorkflow")
class OuterSagaWorkflow:
    def __init__(self) -> None:
        self._hitl_payload: dict[str, object] | None = None
        self._cancel = False

    @workflow.signal
    def hitl_resume(self, payload: dict[str, object]) -> None:
        self._hitl_payload = payload

    @workflow.signal
    def cancel(self) -> None:
        self._cancel = True

    @workflow.run
    async def run(self, payload: dict[str, object]) -> dict[str, object]:
        run_id = await workflow.execute_activity(
            start_run_activity,
            payload,
            start_to_close_timeout=timedelta(hours=2),
        )
        await workflow.wait_condition(lambda: self._hitl_payload is not None or self._cancel)
        if self._cancel:
            await workflow.execute_activity(
                cancel_run_activity,
                run_id,
                start_to_close_timeout=timedelta(minutes=5),
            )
            return {"run_id": run_id, "status": "cancelled"}
        if self._hitl_payload is not None:
            await workflow.execute_activity(
                resume_run_activity,
                self._hitl_payload,
                start_to_close_timeout=timedelta(hours=2),
            )
        return {"run_id": run_id, "status": "signaled"}
