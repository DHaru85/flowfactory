"""Permission 域仓储。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.permission.models import (
    Asset,
    Organization,
    Quota,
    RefreshToken,
    Role,
    User,
    UserRole,
)
from service.persistence.base import Repository


class PermissionRepository:
    """权限与身份聚合仓储。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.user = Repository(session, User)
        self.organization = Repository(session, Organization)
        self.role = Repository(session, Role)
        self.asset = Repository(session, Asset)
        self.quota = Repository(session, Quota)
        self.refresh_token = Repository(session, RefreshToken)

    async def get_user_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username, User.deleted_at.is_(None))
        return await self._session.scalar(stmt)

    async def get_asset_by_key(self, asset_type: str, asset_key: str) -> Asset | None:
        stmt = select(Asset).where(Asset.asset_type == asset_type, Asset.asset_key == asset_key)
        return await self._session.scalar(stmt)

    async def get_quota(
        self,
        subject_type: str,
        subject_id: uuid.UUID,
        quota_type: str,
        period: str,
    ) -> Quota | None:
        stmt = select(Quota).where(
            Quota.subject_type == subject_type,
            Quota.subject_id == subject_id,
            Quota.quota_type == quota_type,
            Quota.period == period,
        )
        return await self._session.scalar(stmt)

    async def list_user_roles(self, user_id: uuid.UUID) -> list[Role]:
        stmt = (
            select(Role)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())
