"""Beat：按 agent_beat_task.cron 触发 Run。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from croniter import croniter
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.agent.models import AgentBeatTask
from service.cache import AgentCacheStore, get_redis_client
from service.persistence.factory import get_repositories
from service.runtime.schemas import (
    BeatTaskTriggerPayload,
    FlowDefinitionDocument,
    RunStatePayload,
    StartRunRequest,
)
from settings.config import get_settings

StartRunFn = Callable[[StartRunRequest], Awaitable[UUID]]


def cron_interval_seconds(cron: str) -> int:
    now = datetime.now(UTC)
    itr = croniter(cron, now)
    first = itr.get_next(datetime)
    second = itr.get_next(datetime)
    delta = int((second - first).total_seconds())
    return max(delta, 60)


def is_cron_due(
    cron: str,
    *,
    now: datetime,
    last_triggered_at: datetime | None,
    tick_seconds: int,
) -> bool:
    window_start = now - timedelta(seconds=tick_seconds)
    itr = croniter(cron, window_start)
    nxt = itr.get_next(datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=UTC)
    if not (window_start < nxt <= now):
        return False
    if last_triggered_at is None:
        return True
    last = last_triggered_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return last < nxt


def _try_acquire_lock(beat_task_id: UUID, ttl: int) -> bool:
    try:
        return AgentCacheStore(get_redis_client()).acquire_beat_lock(beat_task_id, ttl)
    except Exception:
        logger.exception("Beat 分布式锁获取失败 beat_task_id={}", beat_task_id)
        return False


async def dispatch_due_tasks(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    start_run: StartRunFn,
) -> list[BeatTaskTriggerPayload]:
    cfg = get_settings()
    user_id = cfg.beat_system_user_uuid
    if user_id is None:
        logger.error("未配置 FLOWFACTORY_BEAT_SYSTEM_USER_ID，跳过 Beat 触发")
        return []

    current = now or datetime.now(UTC)
    repos = get_repositories(session)
    tasks = await repos.agent.list_enabled_beat_tasks()
    triggered: list[BeatTaskTriggerPayload] = []
    for task in tasks:
        if not is_cron_due(
            task.cron,
            now=current,
            last_triggered_at=task.last_triggered_at,
            tick_seconds=cfg.beat_tick_seconds,
        ):
            continue
        ttl = cron_interval_seconds(task.cron)
        if not _try_acquire_lock(task.id, ttl):
            logger.info("Beat 锁未获取，跳过 code={}", task.code)
            continue
        payload = BeatTaskTriggerPayload(
            beat_task_id=task.id,
            flow_id=task.flow_id,
            profile_id=task.profile_id,
            input_payload=dict(task.input_payload),
            scheduled_at=current,
        )
        if task.profile_id is not None:
            await start_run(_planner_start_request(user_id, task))
            logger.info("Beat 已触发规划 code={} profile_id={}", task.code, task.profile_id)
        elif task.flow_id is not None:
            definition = None
            flow = await repos.agent.flow.get(task.flow_id)
            if flow is not None:
                definition = FlowDefinitionDocument.model_validate(flow.definition)
            await start_run(
                StartRunRequest(
                    user_id=user_id,
                    flow_id=task.flow_id,
                    input_payload=_run_payload(task.input_payload),
                    definition=definition,
                )
            )
            logger.info("Beat 已触发工作流 code={} flow_id={}", task.code, task.flow_id)
        else:
            logger.error("Beat 目标缺失，跳过 code={}", task.code)
            continue
        task.last_triggered_at = current
        triggered.append(payload)
    return triggered


def _run_payload(raw: dict[str, object]) -> RunStatePayload:
    if _looks_like_state(raw):
        return RunStatePayload.model_validate(raw)
    return RunStatePayload(variables=dict(raw))


def _looks_like_state(payload: dict[str, object]) -> bool:
    return "messages" in payload or "variables" in payload


def _planner_start_request(user_id: UUID, task: AgentBeatTask) -> StartRunRequest:
    profile_id = task.profile_id
    if profile_id is None:
        raise ValueError("规划 Beat 缺少 profile_id")
    payload = _run_payload(task.input_payload)
    metadata = dict(payload.metadata)
    metadata["app_key"] = "planner"
    metadata["beat_task_id"] = str(task.id)
    if not payload.messages:
        text = str(task.input_payload.get("input") or task.input_payload.get("content") or "")
        messages: list[dict[str, object]] = (
            [{"role": "user", "content": text}] if text else []
        )
        variables = dict(payload.variables)
        if text and "input" not in variables:
            variables["input"] = text
        payload = RunStatePayload(messages=messages, variables=variables, metadata=metadata)
    else:
        payload = payload.model_copy(update={"metadata": metadata})
    return StartRunRequest(
        user_id=user_id,
        flow_id=profile_id,
        profile_id=profile_id,
        kind="planner",
        input_payload=payload,
    )


async def mark_triggered(session: AsyncSession, task: AgentBeatTask, when: datetime) -> None:
    task.last_triggered_at = when
    await session.flush()
