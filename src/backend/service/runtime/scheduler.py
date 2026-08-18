"""提交 Celery 任务、写入 Run/Thread/Task 快照。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.workflow.models import CeleryTaskRecord, RunSnapshot, ThreadSnapshot
from service.database.session import session_scope
from service.persistence.factory import get_repositories
from service.runtime.constants import (
    CELERY_QUEUED,
    RUN_CANCELLED,
    RUN_PENDING,
    TASK_RESUME,
    TASK_RUN,
)
from service.runtime.hot_state import touch_run_active
from service.runtime.schemas import (
    CeleryTaskEnvelope,
    FlowDefinitionDocument,
    HitlResumeInput,
    RunStatePayload,
    StartRunRequest,
)


def _send_celery(task_name: str, envelope: CeleryTaskEnvelope, *, task_id: str, queue: str) -> None:
    from service.celery_app.dispatch import send_workflow_task

    send_workflow_task(
        task_name,
        envelope.model_dump(mode="json"),
        task_id=task_id,
        queue=queue,
    )


async def _load_definition(
    session: AsyncSession,
    request: StartRunRequest,
) -> FlowDefinitionDocument | None:
    if request.definition is not None:
        return request.definition
    repos = get_repositories(session)
    flow = await repos.agent.flow.get(request.flow_id)
    if flow is None:
        return None
    return FlowDefinitionDocument.model_validate(flow.definition)


async def start_run(request: StartRunRequest) -> UUID:
    """创建 Thread/Run 快照并投递执行任务。"""
    from settings.config import get_settings

    cfg = get_settings()
    queue = request.queue_name or cfg.celery_queue_run
    run_id = uuid4()
    celery_task_id = str(uuid4())
    langgraph_thread_id = str(run_id)
    now = datetime.now(UTC)

    async with session_scope() as session:
        definition = await _load_definition(session, request)
        context: dict[str, object] = {}
        if definition is not None:
            context["definition"] = definition.model_dump(mode="json")
        thread = ThreadSnapshot(
            queue_name=queue,
            priority=request.priority,
            context_payload=context,
        )
        repos = get_repositories(session)
        await repos.workflow.thread.add(thread)
        run = RunSnapshot(
            id=run_id,
            flow_id=request.flow_id,
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            status=RUN_PENDING,
            input_payload=request.input_payload.model_dump(mode="json"),
            thread_id=thread.id,
            langgraph_thread_id=langgraph_thread_id,
        )
        await repos.workflow.run.add(run)
        record = CeleryTaskRecord(
            celery_task_id=celery_task_id,
            run_id=run_id,
            task_name=TASK_RUN,
            status=CELERY_QUEUED,
            queued_at=now,
        )
        await repos.workflow.celery_task.add(record)
        envelope = CeleryTaskEnvelope(
            task_name=TASK_RUN,
            run_id=run_id,
            flow_id=request.flow_id,
            thread_id=thread.id,
            langgraph_thread_id=langgraph_thread_id,
            input_payload=request.input_payload,
        )

    touch_run_active(run_id, RUN_PENDING)
    _send_celery(TASK_RUN, envelope, task_id=celery_task_id, queue=queue)
    logger.info("已提交 Run start run_id={} task_id={}", run_id, celery_task_id)
    return run_id


async def enqueue_resume(
    *,
    run: RunSnapshot,
    hitl: HitlResumeInput,
    input_payload: RunStatePayload,
) -> str:
    from settings.config import get_settings

    cfg = get_settings()
    celery_task_id = str(uuid4())
    now = datetime.now(UTC)
    envelope = CeleryTaskEnvelope(
        task_name=TASK_RESUME,
        run_id=run.id,
        flow_id=run.flow_id,
        thread_id=run.thread_id,
        langgraph_thread_id=run.langgraph_thread_id,
        input_payload=input_payload,
        resume=hitl,
    )
    async with session_scope() as session:
        repos = get_repositories(session)
        record = CeleryTaskRecord(
            celery_task_id=celery_task_id,
            run_id=run.id,
            task_name=TASK_RESUME,
            status=CELERY_QUEUED,
            queued_at=now,
        )
        await repos.workflow.celery_task.add(record)
    _send_celery(TASK_RESUME, envelope, task_id=celery_task_id, queue=cfg.celery_queue_run)
    logger.info("已提交 Run resume run_id={} task_id={}", run.id, celery_task_id)
    return celery_task_id


async def cancel_run(run_id: UUID) -> None:
    async with session_scope() as session:
        repos = get_repositories(session)
        run = await repos.workflow.run.get(run_id)
        if run is None:
            raise ValueError(f"Run 不存在: {run_id}")
        run.status = RUN_CANCELLED
        run.finished_at = datetime.now(UTC)
        run.error_message = "cancelled"
    touch_run_active(run_id, RUN_CANCELLED)
    logger.info("Run 已取消 run_id={}", run_id)
