"""Celery 任务投递（避免与 worker_loop 循环导入）。"""

from __future__ import annotations

from celery.result import AsyncResult

from service.runtime.constants import TASK_RESUME


def send_workflow_task(
    task_name: str,
    payload: dict[str, object],
    *,
    task_id: str,
    queue: str,
) -> AsyncResult:
    from service.celery_app.tasks import resume_langgraph_flow, run_langgraph_flow

    task = resume_langgraph_flow if task_name == TASK_RESUME else run_langgraph_flow
    return task.apply_async(args=[payload], task_id=task_id, queue=queue)
