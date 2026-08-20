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
from service.events.context import StreamPublishContext, attach_stream_ctx, reset_stream_ctx
from service.events.factory import get_stream_bus
from service.events.schemas import run_lifecycle_event
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
from service.runtime.compile_v1 import apply_start_inject
from service.runtime.constants import (
    CELERY_FAILURE,
    CELERY_STARTED,
    CELERY_SUCCESS,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_RUNNING,
    RUN_WAITING_CHILD,
)
from service.runtime.context import GraphExecContext, attach_graph_exec_ctx, reset_graph_exec_ctx
from service.runtime.definition_v1 import FlowDefinitionV1
from service.runtime.flow import FlowRuntime, parse_compile_document
from service.runtime.hitl import create_pending
from service.runtime.hot_state import touch_run_active
from service.runtime.llm import get_chat_client
from service.runtime.scheduler import notify_parent_of_child, spawn_subgraph_child
from service.runtime.schemas import CeleryTaskEnvelope, RunStatePayload, SubgraphNodeResult
from settings.config import get_settings


def _run_config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _strip_interrupt(result: dict[str, object]) -> dict[str, object]:
    cleaned = dict(result)
    cleaned.pop("__interrupt__", None)
    return cleaned


def _interrupt_info(snapshot: object) -> tuple[bool, str, str, dict[str, object]]:
    nxt = getattr(snapshot, "next", ()) or ()
    tasks = getattr(snapshot, "tasks", ()) or ()
    interrupted = bool(nxt)
    node_id = str(nxt[0]) if nxt else "unknown"
    prompt = "需要人工确认"
    payload: dict[str, object] = {}
    for task in tasks:
        interrupts = getattr(task, "interrupts", ()) or ()
        if interrupts:
            interrupted = True
            name = getattr(task, "name", None)
            if name:
                node_id = str(name)
        for item in interrupts:
            value = getattr(item, "value", None)
            if isinstance(value, dict):
                payload = dict(value)
                if value.get("prompt"):
                    prompt = str(value["prompt"])
            elif isinstance(value, str) and value:
                prompt = value
    return interrupted, node_id, prompt, payload


async def _load_definition(
    thread: ThreadSnapshot,
    flow_id: UUID,
    session: AsyncSession,
) -> dict[str, object]:
    raw = thread.context_payload.get("definition")
    if isinstance(raw, dict):
        return dict(raw)
    repos = get_repositories(session)
    flow = await repos.agent.flow.get(flow_id)
    if flow is None:
        raise ValueError(f"Flow 定义不存在: {flow_id}")
    definition = flow.definition
    if not isinstance(definition, dict):
        raise ValueError(f"Flow 定义非法: {flow_id}")
    return dict(definition)


def _as_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _last_assistant_text(result: dict[str, object]) -> str:
    variables = result.get("variables")
    if isinstance(variables, dict) and variables.get("last_output"):
        return str(variables["last_output"])
    messages = result.get("messages")
    if isinstance(messages, list):
        for item in reversed(messages):
            if isinstance(item, dict) and str(item.get("role") or "") == "assistant":
                content = item.get("content")
                if content:
                    return str(content)
    return ""


def _last_assistant_reasoning(result: dict[str, object]) -> str:
    variables = result.get("variables")
    if isinstance(variables, dict) and variables.get("last_reasoning"):
        return str(variables["last_reasoning"])
    return ""


async def _finalize_assistant_message(
    message_id: UUID | None, *, status: str, text: str, reasoning: str = ""
) -> None:
    if message_id is None:
        return
    async with session_scope() as session:
        repos = get_repositories(session)
        row = await repos.conversation.message.get(message_id)
        if row is None:
            return
        row.status = status
        blocks: list[dict[str, object]] = []
        if reasoning:
            blocks.append({"type": "reasoning", "text": reasoning})
        if text:
            blocks.append({"type": "text", "text": text})
        if blocks:
            row.content_blocks = blocks


async def _publish_lifecycle(
    name: str,
    ctx: StreamPublishContext,
    extra: dict[str, object] | None = None,
) -> None:
    if ctx.conversation_id is None:
        return
    try:
        await get_stream_bus().publish(
            ctx.conversation_id,
            run_lifecycle_event(
                name, run_id=ctx.run_id, message_id=ctx.message_id, extra=extra
            ),
        )
    except Exception:
        logger.warning("生命周期事件投递失败 event={} run_id={}", name, ctx.run_id)


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
    failed_run = None
    stream_ctx = StreamPublishContext(
        conversation_id=trace_ctx.conversation_id,
        run_id=run_row_id,
        message_id=_as_uuid(input_payload.metadata.get("assistant_message_id")),
    )
    stream_token = attach_stream_ctx(stream_ctx)
    graph_token = attach_graph_exec_ctx(
        GraphExecContext(
            run_id=run_row_id,
            user_id=trace_ctx.user_id,
            conversation_id=trace_ctx.conversation_id,
            flow_id=flow_id,
            is_first_invoke=envelope.resume is None and envelope.child_resume is None,
        )
    )
    try:
        async with session_scope() as session:
            repos = get_repositories(session)
            thread = await repos.workflow.thread.get(envelope.thread_id)
            if thread is None:
                raise ValueError("Thread 丢失")
            definition: dict[str, object] | None = None
            if envelope.kind != "planner":
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
        config = _run_config(langgraph_thread_id)
        if envelope.kind == "planner":
            from service.runtime.planner import PlannerRuntime

            profile_id = envelope.profile_id or flow_id
            async with session_scope() as session:
                planner = await PlannerRuntime.compile_for_profile(
                    session, profile_id, checkpointer
                )
            graph = planner.graph
            graph_input = input_payload.to_graph_state()
        else:
            if definition is None:
                raise ValueError(f"Flow 定义不存在: {flow_id}")
            parsed = parse_compile_document(definition)
            graph_input = input_payload.to_graph_state()
            if (
                envelope.resume is None
                and envelope.child_resume is None
                and isinstance(parsed, FlowDefinitionV1)
            ):
                graph_input = apply_start_inject(graph_input, parsed)
            runtime = FlowRuntime.compile(
                parsed,
                flow_id=flow_id,
                checkpointer=checkpointer,
                chat_client=get_chat_client(),
            )
            graph = runtime.graph
        if envelope.child_resume is not None:
            result = await graph.ainvoke(
                Command(resume=envelope.child_resume.model_dump(mode="json")),
                config,
            )
        elif envelope.resume is not None:
            resume_value: object = envelope.resume.user_input or envelope.resume.decision
            result = await graph.ainvoke(Command(resume=resume_value), config)
        else:
            result = await graph.ainvoke(graph_input, config)
        snapshot = await graph.aget_state(config)
        interrupted, node_id, prompt, payload = _interrupt_info(snapshot)
        result_dict = dict(result) if isinstance(result, dict) else {"result": result}

        if interrupted and payload.get("kind") == "subgraph_request":
            async with session_scope() as session:
                repos = get_repositories(session)
                parent = await repos.workflow.run.get(run_row_id)
                if parent is None:
                    raise ValueError("Run 丢失")
            spawned = await spawn_subgraph_child(parent=parent, interrupt_value=payload)
            if isinstance(spawned, SubgraphNodeResult):
                result = await graph.ainvoke(
                    Command(resume=spawned.model_dump(mode="json")),
                    config,
                )
                snapshot = await graph.aget_state(config)
                interrupted, node_id, prompt, payload = _interrupt_info(snapshot)
                result_dict = dict(result) if isinstance(result, dict) else {"result": result}
            else:
                async with session_scope() as session:
                    repos = get_repositories(session)
                    run = await repos.workflow.run.get(run_row_id)
                    if run is None:
                        raise ValueError("Run 丢失")
                    if run.status not in {RUN_COMPLETED, RUN_FAILED, "cancelled"}:
                        run.status = RUN_WAITING_CHILD
                        touch_run_active(run.id, RUN_WAITING_CHILD)
                    final_status = run.status
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
                return {"run_id": str(run_row_id), "status": final_status}

        hitl_id: UUID | None = None
        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_row_id)
            if run is None:
                raise ValueError("Run 丢失")
            if interrupted:
                on_reject = str(payload.get("on_reject") or "fail")
                raw_schema = payload.get("form_schema")
                form_schema = raw_schema if isinstance(raw_schema, dict) else None
                pending = await create_pending(
                    session,
                    run=run,
                    node_id=node_id,
                    prompt=prompt,
                    on_reject=on_reject,
                    form_schema=form_schema,
                )
                hitl_id = pending.id
            else:
                run.status = RUN_COMPLETED
                run.output_payload = _strip_interrupt(result_dict)
                run.finished_at = datetime.now(UTC)
                touch_run_active(run.id, RUN_COMPLETED)
            completed_run = run
            if celery_task_id:
                rec = await session.scalar(
                    select(CeleryTaskRecord).where(
                        CeleryTaskRecord.celery_task_id == celery_task_id
                    )
                )
                if rec is not None:
                    rec.status = CELERY_SUCCESS
                    rec.finished_at = datetime.now(UTC)

        if interrupted and hitl_id is not None:
            await _publish_lifecycle(
                "run_interrupted",
                stream_ctx,
                extra={
                    "hitl_id": str(hitl_id),
                    "node_id": node_id,
                    "prompt": prompt,
                },
            )
        if not interrupted:
            await notify_parent_of_child(completed_run, status="completed")
        collector.end_trace("ok")
        async with session_scope() as session:
            await collector.flush(session)
            if evaluator is not None:
                await evaluator.flush(session)
        if not interrupted:
            await _finalize_assistant_message(
                stream_ctx.message_id,
                status="completed",
                text=_last_assistant_text(result_dict),
                reasoning=_last_assistant_reasoning(result_dict),
            )
            await _publish_lifecycle("run_completed", stream_ctx)
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
            failed_run = run
            if celery_task_id:
                rec = await session.scalar(
                    select(CeleryTaskRecord).where(
                        CeleryTaskRecord.celery_task_id == celery_task_id
                    )
                )
                if rec is not None:
                    rec.status = CELERY_FAILURE
                    rec.finished_at = datetime.now(UTC)
        if failed_run is not None:
            await notify_parent_of_child(failed_run, status="failed", error=str(exc))
        touch_run_active(run_row_id, RUN_FAILED)
        collector.end_trace("error")
        try:
            async with session_scope() as session:
                await collector.flush(session)
                if evaluator is not None:
                    await evaluator.flush(session)
        except Exception:
            logger.exception("观测/护栏 flush 失败 run_id={}", envelope.run_id)
        await _finalize_assistant_message(stream_ctx.message_id, status="failed", text="")
        await _publish_lifecycle("run_failed", stream_ctx)
        raise
    finally:
        if evaluator_token is not None:
            reset_evaluator(evaluator_token)
        reset_collector(collector_token)
        reset_stream_ctx(stream_token)
        reset_graph_exec_ctx(graph_token)
