"""Temporal Worker 入口（独立进程启动）。"""

from __future__ import annotations

from temporalio.worker import Worker

from service.orchestration.temporal.activities import (
    cancel_run_activity,
    resume_run_activity,
    start_run_activity,
)
from service.orchestration.temporal.client import get_temporal_client
from service.orchestration.temporal.workflows import OuterSagaWorkflow
from settings.config import get_settings


async def run_temporal_worker() -> None:
    cfg = get_settings()
    client = await get_temporal_client()
    worker = Worker(
        client,
        task_queue=cfg.temporal_task_queue,
        workflows=[OuterSagaWorkflow],
        activities=[start_run_activity, resume_run_activity, cancel_run_activity],
    )
    await worker.run()
