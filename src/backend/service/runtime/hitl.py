"""HITL 待办创建、恢复决策与过期。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.workflow.models import HitlPending, RunSnapshot
from service.persistence.factory import get_repositories
from service.runtime.constants import (
    HITL_APPROVED,
    HITL_EXPIRED,
    HITL_PENDING,
    HITL_REJECTED,
    RUN_CANCELLED,
    RUN_INTERRUPTED,
)
from service.runtime.hot_state import mark_hitl_notify, touch_run_active
from service.runtime.schemas import HitlResumeInput, HitlResumeOutput
from settings.config import get_settings


async def create_pending(
    session: AsyncSession,
    *,
    run: RunSnapshot,
    node_id: str,
    prompt: str,
    on_reject: str = "fail",
) -> HitlPending:
    cfg = get_settings()
    now = datetime.now(UTC)
    pending = HitlPending(
        run_id=run.id,
        node_id=node_id,
        prompt=prompt,
        resume_payload={"on_reject": on_reject},
        status=HITL_PENDING,
        expires_at=now + timedelta(seconds=cfg.hitl_default_ttl_seconds),
    )
    repos = get_repositories(session)
    await repos.workflow.hitl.add(pending)
    run.status = RUN_INTERRUPTED
    ttl = cfg.hitl_default_ttl_seconds
    mark_hitl_notify(pending.id, ttl)
    touch_run_active(run.id, RUN_INTERRUPTED)
    logger.info("创建 HITL 待办 hitl_id={} run_id={} node={}", pending.id, run.id, node_id)
    return pending


async def apply_resume_decision(
    session: AsyncSession,
    hitl: HitlResumeInput,
) -> tuple[HitlPending, RunSnapshot, HitlResumeOutput]:
    repos = get_repositories(session)
    pending = await repos.workflow.hitl.get(hitl.hitl_id)
    if pending is None:
        raise ValueError(f"HITL 待办不存在: {hitl.hitl_id}")
    if pending.status != HITL_PENDING:
        raise ValueError(f"HITL 待办不可恢复 status={pending.status}")
    run = await repos.workflow.run.get(pending.run_id)
    if run is None:
        raise ValueError(f"Run 不存在: {pending.run_id}")

    now = datetime.now(UTC)
    stored = pending.resume_payload if isinstance(pending.resume_payload, dict) else {}
    on_reject = str(stored.get("on_reject") or "fail")
    pending.resume_payload = {**hitl.model_dump(mode="json"), "on_reject": on_reject}
    pending.resolved_at = now
    if hitl.decision == "reject" and on_reject != "route":
        pending.status = HITL_REJECTED
        run.status = RUN_CANCELLED
        run.finished_at = now
        touch_run_active(run.id, RUN_CANCELLED)
        logger.info("HITL 拒绝 hitl_id={} run_id={}", pending.id, run.id)
        return pending, run, HitlResumeOutput(run_id=run.id, resumed=False)

    pending.status = HITL_APPROVED if hitl.decision == "approve" else HITL_REJECTED
    logger.info("HITL 恢复 hitl_id={} run_id={} decision={}", pending.id, run.id, hitl.decision)
    return pending, run, HitlResumeOutput(run_id=run.id, resumed=True)


async def expire_due_pending(session: AsyncSession) -> int:
    repos = get_repositories(session)
    now = datetime.now(UTC)
    rows = await repos.workflow.list_expired_hitl(now)
    count = 0
    for pending in rows:
        pending.status = HITL_EXPIRED
        pending.resolved_at = now
        run = await repos.workflow.run.get(pending.run_id)
        if run is not None and run.status == RUN_INTERRUPTED:
            run.status = RUN_CANCELLED
            run.finished_at = now
            touch_run_active(run.id, RUN_CANCELLED)
        count += 1
    if count:
        logger.info("过期 HITL 待办 {} 条", count)
    return count


async def get_pending(session: AsyncSession, hitl_id: UUID) -> HitlPending | None:
    return await get_repositories(session).workflow.hitl.get(hitl_id)
