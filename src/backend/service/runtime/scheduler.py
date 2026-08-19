"""提交 Celery 任务、写入 Run/Thread/Task 快照。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.workflow.models import (
    CeleryTaskRecord,
    ChildRunPending,
    RunSnapshot,
    ThreadSnapshot,
)
from service.database.session import session_scope
from service.persistence.factory import get_repositories
from service.runtime.child_run import (
    detect_subgraph_cycle,
    result_from_child_run,
    timeout_at_from_seconds,
)
from service.runtime.constants import (
    CELERY_QUEUED,
    CHILD_PARENT_CANCELLED,
    CHILD_PENDING,
    CHILD_RESUMED,
    RUN_CANCELLED,
    RUN_PENDING,
    RUN_WAITING_CHILD,
    TASK_RESUME,
    TASK_RUN,
)
from service.runtime.hot_state import touch_run_active
from service.runtime.schemas import (
    CeleryTaskEnvelope,
    HitlResumeInput,
    RunStatePayload,
    StartRunRequest,
    SubgraphNodeResult,
)


def _send_celery(task_name: str, envelope: CeleryTaskEnvelope, *, task_id: str, queue: str) -> None:
    from service.celery_app.dispatch import send_workflow_task

    send_workflow_task(
        task_name,
        envelope.model_dump(mode="json"),
        task_id=task_id,
        queue=queue,
    )


async def _load_definition_dict(
    session: AsyncSession,
    request: StartRunRequest,
) -> dict[str, object] | None:
    if request.definition is not None:
        return dict(request.definition)
    repos = get_repositories(session)
    flow = await repos.agent.flow.get(request.flow_id)
    if flow is None:
        return None
    raw = flow.definition
    return dict(raw) if isinstance(raw, dict) else None


async def _create_run_records(
    session: AsyncSession,
    request: StartRunRequest,
    *,
    run_id: UUID,
    celery_task_id: str,
    langgraph_thread_id: str,
    queue: str,
) -> tuple[RunSnapshot, CeleryTaskEnvelope]:
    definition = await _load_definition_dict(session, request)
    context: dict[str, object] = {}
    if definition is not None:
        context["definition"] = definition
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
        queued_at=datetime.now(UTC),
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
    return run, envelope


async def start_run(request: StartRunRequest) -> UUID:
    """创建 Thread/Run 快照并投递执行任务。"""
    from settings.config import get_settings

    cfg = get_settings()
    queue = request.queue_name or cfg.celery_queue_run
    run_id = uuid4()
    celery_task_id = str(uuid4())
    langgraph_thread_id = str(run_id)

    async with session_scope() as session:
        _run, envelope = await _create_run_records(
            session,
            request,
            run_id=run_id,
            celery_task_id=celery_task_id,
            langgraph_thread_id=langgraph_thread_id,
            queue=queue,
        )

    touch_run_active(run_id, RUN_PENDING)
    _send_celery(TASK_RUN, envelope, task_id=celery_task_id, queue=queue)
    logger.info("已提交 Run start run_id={} task_id={}", run_id, celery_task_id)
    return run_id


async def spawn_subgraph_child(
    *,
    parent: RunSnapshot,
    interrupt_value: dict[str, object],
) -> UUID | SubgraphNodeResult:
    """先落 pending 再入队子 Run，避免 eager 重入。失败则返回立刻回传父的结果。"""
    from service.runtime.child_run import child_input_from_interrupt
    from settings.config import get_settings

    cfg = get_settings()
    queue = cfg.celery_queue_run
    child_run_id = uuid4()
    celery_task_id = str(uuid4())
    flow_code = str(interrupt_value.get("flow_code") or "")
    version_raw = interrupt_value.get("version")
    version = int(version_raw) if isinstance(version_raw, int) else None
    node_id = str(interrupt_value.get("node_id") or "subgraph")
    child_input = child_input_from_interrupt(interrupt_value)
    ancestors_raw = child_input.metadata.get("__flow_ancestors__")
    ancestors = (
        [str(item) for item in ancestors_raw] if isinstance(ancestors_raw, list) else []
    )

    async with session_scope() as session:
        repos = get_repositories(session)
        cycle = await detect_subgraph_cycle(
            session,
            parent_flow_id=parent.flow_id,
            child_flow_code=flow_code,
            child_version=version,
            ancestors=ancestors,
        )
        if cycle is not None:
            return SubgraphNodeResult(status="failed", error=cycle)
        if version is None:
            child_flow = await repos.agent.get_latest_published_flow(flow_code)
        else:
            child_flow = await repos.agent.get_flow_by_code_version(flow_code, version)
        if child_flow is None:
            return SubgraphNodeResult(status="failed", error=f"子图不存在: {flow_code}")
        parent_flow = await repos.agent.flow.get(parent.flow_id)
        parent_code = parent_flow.code if parent_flow is not None else ""
        meta = dict(child_input.metadata)
        meta["parent_run_id"] = str(parent.id)
        meta["parent_node_id"] = node_id
        meta["__flow_ancestors__"] = [*ancestors, parent_code]
        child_input = RunStatePayload(
            messages=child_input.messages,
            variables=child_input.variables,
            metadata=meta,
        )
        request = StartRunRequest(
            user_id=parent.user_id,
            flow_id=child_flow.id,
            input_payload=child_input,
            conversation_id=parent.conversation_id,
            queue_name=queue,
        )
        _child, envelope = await _create_run_records(
            session,
            request,
            run_id=child_run_id,
            celery_task_id=celery_task_id,
            langgraph_thread_id=str(child_run_id),
            queue=queue,
        )
        pending = ChildRunPending(
            parent_run_id=parent.id,
            child_run_id=child_run_id,
            node_id=node_id,
            status=CHILD_PENDING,
            timeout_at=timeout_at_from_seconds(interrupt_value.get("timeout_seconds")),
        )
        await repos.workflow.child_pending.add(pending)
        live_parent = await repos.workflow.run.get(parent.id)
        if live_parent is None:
            return SubgraphNodeResult(status="failed", error="父 Run 丢失")
        live_parent.status = RUN_WAITING_CHILD
        touch_run_active(parent.id, RUN_WAITING_CHILD)

    _send_celery(TASK_RUN, envelope, task_id=celery_task_id, queue=queue)
    logger.info(
        "已提交子图 Run parent={} child={} node={}",
        parent.id,
        child_run_id,
        node_id,
    )
    return child_run_id


async def enqueue_resume(
    *,
    run: RunSnapshot,
    hitl: HitlResumeInput | None,
    input_payload: RunStatePayload,
    child_resume: SubgraphNodeResult | None = None,
) -> str:
    from settings.config import get_settings

    cfg = get_settings()
    celery_task_id = str(uuid4())
    now = datetime.now(UTC)
    resume_kind = "child" if child_resume is not None else "hitl"
    envelope = CeleryTaskEnvelope(
        task_name=TASK_RESUME,
        run_id=run.id,
        flow_id=run.flow_id,
        thread_id=run.thread_id,
        langgraph_thread_id=run.langgraph_thread_id,
        input_payload=input_payload,
        resume_kind=resume_kind,
        resume=hitl,
        child_resume=child_resume,
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
    logger.info("已提交 Run resume run_id={} kind={}", run.id, resume_kind)
    return celery_task_id


async def notify_parent_of_child(
    child: RunSnapshot,
    *,
    status: str,
    error: str | None = None,
) -> None:
    async with session_scope() as session:
        repos = get_repositories(session)
        pending = await repos.workflow.get_child_pending_by_child(child.id)
        if pending is None or pending.status != CHILD_PENDING:
            return
        parent = await repos.workflow.run.get(pending.parent_run_id)
        if parent is None or parent.status == RUN_CANCELLED:
            pending.status = CHILD_PARENT_CANCELLED
            pending.resolved_at = datetime.now(UTC)
            return
        result = result_from_child_run(child, status=status, error=error)
        pending.status = CHILD_RESUMED
        pending.resolved_at = datetime.now(UTC)
        pending.resume_payload = result.model_dump(mode="json")
        input_payload = RunStatePayload.model_validate(parent.input_payload)
        parent_id = parent.id
    await enqueue_resume(
        run=parent,
        hitl=None,
        input_payload=input_payload,
        child_resume=result,
    )
    logger.info("子图回传父 Run parent={} child={} status={}", parent_id, child.id, status)


async def cancel_run(
    run_id: UUID,
    *,
    notify_parent: bool = True,
    cascade: bool = True,
    child_status: str = "cancelled",
) -> None:
    now = datetime.now(UTC)
    child_ids: list[UUID] = []
    child_snapshot: RunSnapshot | None = None
    async with session_scope() as session:
        repos = get_repositories(session)
        run = await repos.workflow.run.get(run_id)
        if run is None:
            raise ValueError(f"Run 不存在: {run_id}")
        already_done = run.status in {
            "completed",
            "failed",
            "cancelled",
        }
        if not already_done:
            run.status = RUN_CANCELLED
            run.finished_at = now
            run.error_message = "cancelled"
        if cascade:
            pending_rows = await repos.workflow.list_pending_children(run_id)
            for pending in pending_rows:
                pending.status = CHILD_PARENT_CANCELLED
                pending.resolved_at = now
                child_ids.append(pending.child_run_id)
        if notify_parent:
            parent_pending = await repos.workflow.get_child_pending_by_child(run_id)
            if parent_pending is not None and parent_pending.status == CHILD_PENDING:
                parent_notify = await repos.workflow.run.get(parent_pending.parent_run_id)
                child_snapshot = run
    touch_run_active(run_id, RUN_CANCELLED)
    logger.info("Run 已取消 run_id={}", run_id)
    for child_id in child_ids:
        await cancel_run(child_id, notify_parent=False, cascade=True)
    if notify_parent and parent_notify is not None and child_snapshot is not None:
        await notify_parent_of_child(child_snapshot, status=child_status)


async def expire_due_child_pending() -> int:
    async with session_scope() as session:
        repos = get_repositories(session)
        rows = await repos.workflow.list_expired_child_pending(datetime.now(UTC))
        targets = [pending.child_run_id for pending in rows]
    if targets:
        logger.info("过期子图等待 {} 条", len(targets))
    for child_id in targets:
        await cancel_run(
            child_id, notify_parent=True, cascade=True, child_status="timeout"
        )
    return len(targets)
