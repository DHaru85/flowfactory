"""Permission 域仓储。"""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.permission.models import (
    Asset,
    ExternalIdentity,
    Organization,
    Quota,
    RefreshToken,
    Role,
    RoleAssetGrant,
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
        self.external_identity = Repository(session, ExternalIdentity)

    async def get_user_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username, User.deleted_at.is_(None))
        return await self._session.scalar(stmt)

    async def count_active_users(self) -> int:
        stmt = select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        value = await self._session.scalar(stmt)
        return int(value or 0)

    async def get_organization_by_code(self, code: str) -> Organization | None:
        stmt = select(Organization).where(Organization.code == code)
        return await self._session.scalar(stmt)

    async def get_asset_by_key(self, asset_type: str, asset_key: str) -> Asset | None:
        stmt = select(Asset).where(Asset.asset_type == asset_type, Asset.asset_key == asset_key)
        return await self._session.scalar(stmt)

    async def list_assets_by_type(self, asset_type: str) -> list[Asset]:
        stmt = select(Asset).where(Asset.asset_type == asset_type)
        result = await self._session.scalars(stmt)
        return list(result.all())

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

    async def list_user_role_codes(self, user_id: uuid.UUID) -> list[str]:
        roles = await self.list_user_roles(user_id)
        return [role.code for role in roles]

    async def list_role_grants(self, role_id: uuid.UUID) -> list[tuple[RoleAssetGrant, Asset]]:
        stmt = (
            select(RoleAssetGrant, Asset)
            .join(Asset, Asset.id == RoleAssetGrant.asset_id)
            .where(RoleAssetGrant.role_id == role_id)
        )
        result = await self._session.execute(stmt)
        return list(result.all())

    async def get_refresh_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return await self._session.scalar(stmt)

    async def revoke_refresh_family(self, family_id: uuid.UUID, revoked_at: datetime) -> int:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)

    async def revoke_user_refresh_tokens(self, user_id: uuid.UUID, revoked_at: datetime) -> int:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)

    async def list_users_in_scope(
        self,
        *,
        organization_id: uuid.UUID | None,
        department_id: uuid.UUID | None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[User]:
        stmt = select(User).where(User.deleted_at.is_(None))
        if organization_id is not None:
            stmt = stmt.where(User.organization_id == organization_id)
        if department_id is not None:
            stmt = stmt.where(User.department_id == department_id)
        stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_external_identity(
        self,
        provider: str,
        external_id: str,
    ) -> ExternalIdentity | None:
        stmt = select(ExternalIdentity).where(
            ExternalIdentity.provider == provider,
            ExternalIdentity.external_id == external_id,
        )
        return await self._session.scalar(stmt)
