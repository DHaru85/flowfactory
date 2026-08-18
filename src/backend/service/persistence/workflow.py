"""Workflow 域仓储。"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from data_schema.workflow.models import (
    CeleryTaskRecord,
    HitlPending,
    RunSnapshot,
    ThreadSnapshot,
)
from service.persistence.base import Repository


class WorkflowRepository:
    """工作流运行态聚合仓储。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.run = Repository(session, RunSnapshot)
        self.thread = Repository(session, ThreadSnapshot)
        self.hitl = Repository(session, HitlPending)
        self.celery_task = Repository(session, CeleryTaskRecord)

    def get_run_by_conversation(self, conversation_id: uuid.UUID) -> RunSnapshot | None:
        stmt = (
            select(RunSnapshot)
            .where(RunSnapshot.conversation_id == conversation_id)
            .order_by(RunSnapshot.created_at.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def list_pending_hitl(self, user_id: uuid.UUID | None = None) -> list[HitlPending]:
        stmt = select(HitlPending).where(HitlPending.status == "pending")
        if user_id is not None:
            stmt = stmt.join(
                RunSnapshot,
                RunSnapshot.id == HitlPending.run_id,
            ).where(RunSnapshot.user_id == user_id)
        return list(self._session.scalars(stmt).all())

    def get_celery_task_by_run(self, run_id: uuid.UUID) -> CeleryTaskRecord | None:
        stmt = (
            select(CeleryTaskRecord)
            .where(CeleryTaskRecord.run_id == run_id)
            .order_by(CeleryTaskRecord.queued_at.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def list_active_runs(self, user_id: uuid.UUID) -> list[RunSnapshot]:
        stmt = select(RunSnapshot).where(
            RunSnapshot.user_id == user_id,
            RunSnapshot.status.in_(("pending", "running", "interrupted")),
        )
        return list(self._session.scalars(stmt).all())
