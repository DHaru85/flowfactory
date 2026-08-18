"""Celery 任务入口。"""

from __future__ import annotations

from celery import Task
from loguru import logger

from service.celery_app.app import celery_app
from service.runtime.async_utils import run_coro_factory
from service.runtime.constants import TASK_BEAT, TASK_EXPIRE_HITL, TASK_RESUME, TASK_RUN
from service.runtime.schemas import CeleryTaskEnvelope


def _execute_bound(self: Task, envelope: dict[str, object]) -> dict[str, object]:
    from service.runtime.worker_loop import execute_envelope

    parsed = CeleryTaskEnvelope.model_validate(envelope)
    worker_id = getattr(self.request, "hostname", None)

    def _run() -> dict[str, object]:
        return execute_envelope(parsed, worker_id=worker_id)

    return run_coro_factory(_run)


@celery_app.task(name=TASK_RUN, bind=True)
def run_langgraph_flow(self: Task, envelope: dict[str, object]) -> dict[str, object]:
    return _execute_bound(self, envelope)


@celery_app.task(name=TASK_RESUME, bind=True)
def resume_langgraph_flow(self: Task, envelope: dict[str, object]) -> dict[str, object]:
    return _execute_bound(self, envelope)


@celery_app.task(name=TASK_BEAT)
def dispatch_beat_tasks() -> int:
    from service.database.session import session_scope
    from service.runtime.beat import dispatch_due_tasks
    from service.runtime.scheduler import start_run

    async def _run() -> int:
        async with session_scope() as session:
            triggered = await dispatch_due_tasks(session, start_run=start_run)
            return len(triggered)

    count = run_coro_factory(_run)
    logger.info("Beat tick 触发 {} 条", count)
    return count


@celery_app.task(name=TASK_EXPIRE_HITL)
def expire_hitl_pending() -> int:
    from service.database.session import session_scope
    from service.runtime.hitl import expire_due_pending

    async def _run() -> int:
        async with session_scope() as session:
            return await expire_due_pending(session)

    return run_coro_factory(_run)
