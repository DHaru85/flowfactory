"""Run 热状态写入（Redis 失败不影响主路径）。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from loguru import logger

from service.cache import WorkflowCacheStore, get_redis_client


def touch_run_active(run_id: UUID, status: str) -> None:
    try:
        store = WorkflowCacheStore(get_redis_client())
        store.set_run_active(
            run_id,
            status,
            datetime.now(UTC).isoformat(),
        )
    except Exception:
        logger.warning("写入 Run 热状态失败 run_id={}", run_id)


def mark_hitl_notify(hitl_id: UUID, ttl: int) -> None:
    try:
        store = WorkflowCacheStore(get_redis_client())
        store.mark_hitl_notify(hitl_id, ttl)
    except Exception:
        logger.warning("写入 HITL 提醒去重失败 hitl_id={}", hitl_id)


def clear_run_active(run_id: UUID) -> None:
    try:
        WorkflowCacheStore(get_redis_client()).clear_run_active(run_id)
    except Exception:
        logger.warning("清理 Run 热状态失败 run_id={}", run_id)
