"""Celery 任务入口。"""

from __future__ import annotations

from celery import Task
from loguru import logger

from service.celery_app.app import celery_app
from service.runtime.async_utils import run_coro_factory
from service.runtime.constants import (
    TASK_BEAT,
    TASK_EXPIRE_HITL,
    TASK_INGEST,
    TASK_LDAP_SYNC,
    TASK_RESUME,
    TASK_RUN,
)
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


@celery_app.task(name=TASK_INGEST)
def ingest_knowledge_doc(payload: dict[str, object]) -> dict[str, object]:
    from service.database.session import session_scope
    from service.knowledge.ingestion import IngestionPipeline
    from service.knowledge.schemas import IngestDocumentRequest

    request = IngestDocumentRequest.model_validate(payload)

    async def _run() -> dict[str, object]:
        async with session_scope() as session:
            pipeline = IngestionPipeline(session, request)
            stats = await pipeline.run()
            return stats.model_dump(mode="json")

    result = run_coro_factory(_run)
    logger.info(
        "知识入库 job={} skipped={} chunks={}",
        request.job_id,
        result.get("skipped"),
        result.get("chunks"),
    )
    return result


@celery_app.task(name=TASK_LDAP_SYNC)
def sync_ldap_directory(payload: dict[str, object] | None = None) -> dict[str, object]:
    from datetime import UTC, datetime

    from data_schema.permission.models import LdapSyncJob
    from service.auth.ldap.sync import execute_user_sync
    from service.auth.schemas import LdapSyncPayload
    from service.database.session import session_scope
    from settings.config import get_settings

    cfg = get_settings()
    if not cfg.ldap_enabled:
        logger.warning("ldap_enabled=false，跳过目录同步")
        return {"skipped": True, "reason": "ldap_disabled"}

    async def _run() -> dict[str, object]:
        async with session_scope() as session:
            job = LdapSyncJob(trigger="scheduled", status="running", stats={})
            if payload and payload.get("job_id"):
                from uuid import UUID

                existing = await session.get(LdapSyncJob, UUID(str(payload["job_id"])))
                if existing is not None:
                    job = existing
                    job.status = "running"
            else:
                session.add(job)
                await session.flush()
            job.started_at = datetime.now(UTC)
            request = LdapSyncPayload.model_validate(
                {"job_id": job.id, **(payload or {})}
            )
            try:
                stats = await execute_user_sync(session, request)
                job.status = "success"
                job.stats = stats.model_dump()
                job.finished_at = datetime.now(UTC)
                return stats.model_dump()
            except Exception as exc:
                job.status = "failed"
                job.error_message = str(exc)[:4000]
                job.finished_at = datetime.now(UTC)
                logger.exception("LDAP 同步失败 job={}", job.id)
                return {"errors": [str(exc)]}

    return run_coro_factory(_run)

