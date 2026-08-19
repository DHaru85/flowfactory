"""RBAC 校验。"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from service.auth.errors import USER_NOT_FOUND, AuthError
from service.auth.schemas import AssetRef, PermissionCheckRequest, PermissionCheckResult
from service.cache.client import get_redis_client
from service.cache.stores import GrantCacheStore
from service.persistence.factory import get_repositories

GRANT_TTL = 300


class PermissionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        grant_cache: GrantCacheStore | None = None,
    ) -> None:
        self._session = session
        self._cache = grant_cache or GrantCacheStore(get_redis_client())

    async def check(self, request: PermissionCheckRequest) -> PermissionCheckResult:
        repos = get_repositories(self._session)
        user = await repos.permission.user.get(request.user_id)
        if user is None or user.deleted_at is not None:
            raise AuthError(USER_NOT_FOUND, "用户不存在")
        if user.is_superuser:
            return PermissionCheckResult(allowed=True, reason="superuser")
        grants = await self._grants_for_user(user.id)
        for item in grants:
            if item["asset_type"] != request.asset_type:
                continue
            if item["asset_key"] != request.asset_key:
                continue
            actions = item.get("actions") or []
            if request.action in actions or "admin" in actions:
                return PermissionCheckResult(allowed=True, reason=None)
        return PermissionCheckResult(allowed=False, reason="missing_grant")

    async def list_accessible_assets(
        self,
        user_id: uuid.UUID,
        asset_type: str,
        action: str,
    ) -> list[AssetRef]:
        repos = get_repositories(self._session)
        user = await repos.permission.user.get(user_id)
        if user is None:
            raise AuthError(USER_NOT_FOUND, "用户不存在")
        if user.is_superuser:
            assets = await repos.permission.list_assets_by_type(asset_type)
            return [
                AssetRef(asset_type=item.asset_type, asset_key=item.asset_key, name=item.name)
                for item in assets
            ]
        grants = await self._grants_for_user(user_id)
        seen: set[str] = set()
        result: list[AssetRef] = []
        for item in grants:
            if item["asset_type"] != asset_type:
                continue
            actions = item.get("actions") or []
            if action not in actions and "admin" not in actions:
                continue
            key = str(item["asset_key"])
            if key in seen:
                continue
            seen.add(key)
            result.append(
                AssetRef(
                    asset_type=str(item["asset_type"]),
                    asset_key=key,
                    name=str(item.get("name") or key),
                )
            )
        return result

    async def _grants_for_user(self, user_id: uuid.UUID) -> list[dict[str, object]]:
        repos = get_repositories(self._session)
        roles = await repos.permission.list_user_roles(user_id)
        merged: list[dict[str, object]] = []
        for role in roles:
            cached = self._cache.get_role_grants(role.id)
            if cached is not None:
                payload = json.loads(cached)
                if isinstance(payload, list):
                    merged.extend(item for item in payload if isinstance(item, dict))
                continue
            rows = await repos.permission.list_role_grants(role.id)
            serialized: list[dict[str, object]] = [
                {
                    "asset_type": asset.asset_type,
                    "asset_key": asset.asset_key,
                    "name": asset.name,
                    "actions": list(grant.actions),
                }
                for grant, asset in rows
            ]
            self._cache.set_role_grants(
                role.id,
                json.dumps(serialized, ensure_ascii=False),
                GRANT_TTL,
            )
            merged.extend(serialized)
        return merged
