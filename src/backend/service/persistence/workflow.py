"""Workflow 域仓储。"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.workflow.models import (
    CeleryTaskRecord,
    ChildRunPending,
    HitlPending,
    RunSnapshot,
    ThreadSnapshot,
)
from service.persistence.base import Repository


class WorkflowRepository:
    """工作流运行态聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.run = Repository(session, RunSnapshot)
        self.thread = Repository(session, ThreadSnapshot)
        self.hitl = Repository(session, HitlPending)
        self.child_pending = Repository(session, ChildRunPending)
        self.celery_task = Repository(session, CeleryTaskRecord)

    async def get_run_by_conversation(self, conversation_id: uuid.UUID) -> RunSnapshot | None:
        stmt = (
            select(RunSnapshot)
            .where(RunSnapshot.conversation_id == conversation_id)
            .order_by(RunSnapshot.created_at.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def list_pending_hitl(self, user_id: uuid.UUID | None = None) -> list[HitlPending]:
        stmt = select(HitlPending).where(HitlPending.status == "pending")
        if user_id is not None:
            stmt = stmt.join(
                RunSnapshot,
                RunSnapshot.id == HitlPending.run_id,
            ).where(RunSnapshot.user_id == user_id)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_expired_hitl(self, now: datetime) -> list[HitlPending]:
        stmt = select(HitlPending).where(
            HitlPending.status == "pending",
            HitlPending.expires_at.is_not(None),
            HitlPending.expires_at <= now,
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_celery_task_by_run(self, run_id: uuid.UUID) -> CeleryTaskRecord | None:
        stmt = (
            select(CeleryTaskRecord)
            .where(CeleryTaskRecord.run_id == run_id)
            .order_by(CeleryTaskRecord.queued_at.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)

    async def list_active_runs(self, user_id: uuid.UUID) -> list[RunSnapshot]:
        stmt = select(RunSnapshot).where(
            RunSnapshot.user_id == user_id,
            RunSnapshot.status.in_(
                ("pending", "running", "interrupted", "waiting_child")
            ),
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_child_pending_by_child(
        self, child_run_id: uuid.UUID
    ) -> ChildRunPending | None:
        stmt = select(ChildRunPending).where(ChildRunPending.child_run_id == child_run_id)
        return await self._session.scalar(stmt)

    async def list_pending_children(self, parent_run_id: uuid.UUID) -> list[ChildRunPending]:
        stmt = select(ChildRunPending).where(
            ChildRunPending.parent_run_id == parent_run_id,
            ChildRunPending.status == "pending",
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_expired_child_pending(self, now: datetime) -> list[ChildRunPending]:
        stmt = select(ChildRunPending).where(
            ChildRunPending.status == "pending",
            ChildRunPending.timeout_at.is_not(None),
            ChildRunPending.timeout_at <= now,
        )
        result = await self._session.scalars(stmt)
        return list(result.all())
