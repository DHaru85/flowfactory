"""Audit 域仓储。"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.audit.models import AssetConsume, AssetObtain, AuditActivity
from service.persistence.base import Repository


class AuditRepository:
    """审计与用量聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.obtain = Repository(session, AssetObtain)
        self.consume = Repository(session, AssetConsume)
        self.activity = Repository(session, AuditActivity)

    async def record_obtain(self, record: AssetObtain) -> AssetObtain:
        self._session.add(record)
        await self._session.flush()
        return record

    async def record_consume(self, record: AssetConsume) -> AssetConsume:
        self._session.add(record)
        await self._session.flush()
        return record

    async def record_activity(self, activity: AuditActivity) -> AuditActivity:
        self._session.add(activity)
        await self._session.flush()
        return activity

    async def sum_consume_amount(
        self,
        subject_type: str,
        subject_id: uuid.UUID,
        quota_type: str,
        *,
        since: datetime | None = None,
    ) -> int:
        stmt = select(func.coalesce(func.sum(AssetConsume.amount), 0)).where(
            AssetConsume.subject_type == subject_type,
            AssetConsume.subject_id == subject_id,
            AssetConsume.quota_type == quota_type,
        )
        if since is not None:
            stmt = stmt.where(AssetConsume.created_at >= since)
        result = await self._session.scalar(stmt)
        return int(result or 0)

    async def list_activity_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AuditActivity]:
        stmt = (
            select(AuditActivity)
            .where(AuditActivity.user_id == user_id)
            .order_by(AuditActivity.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())
