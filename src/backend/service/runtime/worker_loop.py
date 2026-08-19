"""Worker 内执行 / 恢复 LangGraph。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from langgraph.types import Command
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.workflow.models import CeleryTaskRecord, ThreadSnapshot
from service.database.session import session_scope
from service.guardrail.context import attach_evaluator, reset_evaluator
from service.guardrail.evaluator import GuardrailEvaluator
from service.guardrail.load import load_rule_specs
from service.observability.collector import (
    TraceCollector,
    attach_collector,
    reset_collector,
)
from service.observability.schemas import TraceContext
from service.persistence.factory import get_repositories
from service.runtime.checkpointer import get_checkpointer
from service.runtime.constants import (
    CELERY_FAILURE,
    CELERY_STARTED,
    CELERY_SUCCESS,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_RUNNING,
)
from service.runtime.flow import FlowRuntime
from service.runtime.hitl import create_pending
from service.runtime.hot_state import touch_run_active
from service.runtime.llm import get_chat_client
from service.runtime.schemas import CeleryTaskEnvelope, FlowDefinitionDocument, RunStatePayload
from settings.config import get_settings


def _run_config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _strip_interrupt(result: dict[str, object]) -> dict[str, object]:
    cleaned = dict(result)
    cleaned.pop("__interrupt__", None)
    return cleaned


def _interrupt_info(snapshot: object) -> tuple[bool, str, str]:
    nxt = getattr(snapshot, "next", ()) or ()
    tasks = getattr(snapshot, "tasks", ()) or ()
    interrupted = bool(nxt)
    node_id = str(nxt[0]) if nxt else "unknown"
    prompt = "需要人工确认"
    for task in tasks:
        interrupts = getattr(task, "interrupts", ()) or ()
        if interrupts:
            interrupted = True
            name = getattr(task, "name", None)
            if name:
                node_id = str(name)
        for item in interrupts:
            value = getattr(item, "value", None)
            if isinstance(value, dict) and value.get("prompt"):
                prompt = str(value["prompt"])
            elif isinstance(value, str) and value:
                prompt = value
    return interrupted, node_id, prompt


async def _load_definition(
    thread: ThreadSnapshot,
    flow_id: UUID,
    session: AsyncSession,
) -> FlowDefinitionDocument:
    raw = thread.context_payload.get("definition")
    if isinstance(raw, dict):
        return FlowDefinitionDocument.model_validate(raw)
    repos = get_repositories(session)
    flow = await repos.agent.flow.get(flow_id)
    if flow is None:
        raise ValueError(f"Flow 定义不存在: {flow_id}")
    return FlowDefinitionDocument.model_validate(flow.definition)


async def execute_envelope(
    envelope: CeleryTaskEnvelope,
    *,
    worker_id: str | None = None,
) -> dict[str, object]:
    async with session_scope() as session:
        repos = get_repositories(session)
        record = await repos.workflow.get_celery_task_by_run(envelope.run_id)
        celery_task_id = record.celery_task_id if record else ""
        run = await repos.workflow.run.get(envelope.run_id)
        thread = await repos.workflow.thread.get(envelope.thread_id)
        if run is None or thread is None:
            raise ValueError(f"Run/Thread 不存在 run={envelope.run_id}")
        if worker_id:
            thread.worker_id = worker_id
        run.status = RUN_RUNNING
        if run.started_at is None:
            run.started_at = datetime.now(UTC)
        if record is not None:
            record.status = CELERY_STARTED
            record.started_at = datetime.now(UTC)
            if worker_id:
                record.worker_id = worker_id
        run_row_id = run.id
        flow_id = run.flow_id
        langgraph_thread_id = run.langgraph_thread_id
        input_payload = RunStatePayload.model_validate(run.input_payload)
        trace_ctx = TraceContext(
            run_id=run.id,
            conversation_id=run.conversation_id,
            user_id=run.user_id,
            flow_id=run.flow_id,
            name="langgraph.run",
        )

    touch_run_active(run_row_id, RUN_RUNNING)

    collector = TraceCollector()
    collector_token = attach_collector(collector)
    collector.start_trace("langgraph.run", trace_ctx)
    evaluator: GuardrailEvaluator | None = None
    evaluator_token = None
    try:
        async with session_scope() as session:
            repos = get_repositories(session)
            thread = await repos.workflow.thread.get(envelope.thread_id)
            if thread is None:
                raise ValueError("Thread 丢失")
            definition = await _load_definition(thread, flow_id, session)
            if get_settings().guardrail_enabled:
                specs = await load_rule_specs(session)
                evaluator = GuardrailEvaluator(
                    specs,
                    context={
                        "run_id": run_row_id,
                        "user_id": trace_ctx.user_id,
                        "conversation_id": trace_ctx.conversation_id,
                    },
                )
                evaluator_token = attach_evaluator(evaluator)

        checkpointer = await get_checkpointer()
        runtime = FlowRuntime.compile(
            definition,
            flow_id=flow_id,
            checkpointer=checkpointer,
            chat_client=get_chat_client(),
        )
        config = _run_config(langgraph_thread_id)
        graph = runtime.graph
        if envelope.resume is not None:
            resume_value: object = envelope.resume.user_input or envelope.resume.decision
            result = await graph.ainvoke(Command(resume=resume_value), config)
        else:
            result = await graph.ainvoke(input_payload.to_graph_state(), config)
        snapshot = await graph.aget_state(config)
        interrupted, node_id, prompt = _interrupt_info(snapshot)
        result_dict = dict(result) if isinstance(result, dict) else {"result": result}

        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_row_id)
            if run is None:
                raise ValueError("Run 丢失")
            if interrupted:
                await create_pending(session, run=run, node_id=node_id, prompt=prompt)
            else:
                run.status = RUN_COMPLETED
                run.output_payload = _strip_interrupt(result_dict)
                run.finished_at = datetime.now(UTC)
                touch_run_active(run.id, RUN_COMPLETED)
            if celery_task_id:
                rec = await session.scalar(
                    select(CeleryTaskRecord).where(
                        CeleryTaskRecord.celery_task_id == celery_task_id
                    )
                )
                if rec is not None:
                    rec.status = CELERY_SUCCESS
                    rec.finished_at = datetime.now(UTC)

        collector.end_trace("ok")
        async with session_scope() as session:
            await collector.flush(session)
            if evaluator is not None:
                await evaluator.flush(session)
        return {
            "run_id": str(run_row_id),
            "status": "interrupted" if interrupted else "completed",
        }
    except Exception as exc:
        logger.exception("Run 执行失败 run_id={}", envelope.run_id)
        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_row_id)
            if run is not None:
                run.status = RUN_FAILED
                run.error_message = str(exc)
                run.finished_at = datetime.now(UTC)
            if celery_task_id:
                rec = await session.scalar(
                    select(CeleryTaskRecord).where(
                        CeleryTaskRecord.celery_task_id == celery_task_id
                    )
                )
                if rec is not None:
                    rec.status = CELERY_FAILURE
                    rec.finished_at = datetime.now(UTC)
        touch_run_active(run_row_id, RUN_FAILED)
        collector.end_trace("error")
        try:
            async with session_scope() as session:
                await collector.flush(session)
                if evaluator is not None:
                    await evaluator.flush(session)
        except Exception:
            logger.exception("观测/护栏 flush 失败 run_id={}", envelope.run_id)
        raise
    finally:
        if evaluator_token is not None:
            reset_evaluator(evaluator_token)
        reset_collector(collector_token)
