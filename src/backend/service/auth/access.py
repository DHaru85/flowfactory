"""应用可见性与配置资源绑定审核。"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.permission.models import User
from service.auth.errors import USER_NOT_FOUND, AuthError
from service.auth.permission import PermissionService
from service.auth.schemas import PermissionCheckRequest
from service.persistence.factory import get_repositories

USE_ACTIONS = frozenset({"read", "use", "write", "admin"})
CONTROL_ACTIONS = frozenset({"write", "admin"})
CONFIG_RESOURCE_TYPES = frozenset({"profile", "skill", "tool", "mcp_server"})
APP_RESOURCE_TYPE = "application"
APP_ASSET_TYPE = "application"


class AccessControl:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._perm = PermissionService(session)
        self._users: dict[uuid.UUID, User] = {}
        self._use_cache: dict[tuple[uuid.UUID, str], bool] = {}
        self._control_cache: dict[tuple[uuid.UUID, str], bool] = {}

    async def load_user(self, user_id: uuid.UUID) -> User:
        cached = self._users.get(user_id)
        if cached is not None:
            return cached
        repos = get_repositories(self._session)
        user = await repos.permission.user.get(user_id)
        if user is None or user.deleted_at is not None:
            raise AuthError(USER_NOT_FOUND, "用户不存在")
        self._users[user_id] = user
        return user

    async def is_platform_admin(self, user_id: uuid.UUID) -> bool:
        user = await self.load_user(user_id)
        return bool(user.is_superuser)

    async def can_use_app(self, user_id: uuid.UUID, app_key: str) -> bool:
        key = (user_id, app_key)
        if key in self._use_cache:
            return self._use_cache[key]
        allowed = await self._app_allowed(user_id, app_key, USE_ACTIONS, use_tier=True)
        self._use_cache[key] = allowed
        return allowed

    async def can_control_app(self, user_id: uuid.UUID, app_key: str) -> bool:
        key = (user_id, app_key)
        if key in self._control_cache:
            return self._control_cache[key]
        allowed = await self._app_allowed(user_id, app_key, CONTROL_ACTIONS, use_tier=False)
        self._control_cache[key] = allowed
        return allowed

    async def sees_all_agent_config(self, user_id: uuid.UUID) -> bool:
        if await self.is_platform_admin(user_id):
            return True
        return await self.can_control_app(user_id, "agent_config")

    async def visible_resource_ids(self, user_id: uuid.UUID, resource_type: str) -> list[uuid.UUID]:
        if resource_type not in CONFIG_RESOURCE_TYPES:
            return []
        user = await self.load_user(user_id)
        subjects = await self._subjects(user)
        repos = get_repositories(self._session)
        rows = await repos.agent.list_bindings_for_subjects(resource_type, subjects)
        seen: set[uuid.UUID] = set()
        ordered: list[uuid.UUID] = []
        for row in rows:
            if not USE_ACTIONS.intersection(row.actions or []):
                continue
            if row.resource_id in seen:
                continue
            seen.add(row.resource_id)
            ordered.append(row.resource_id)
        return ordered

    async def can_see_agent_resource(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> bool:
        if await self.sees_all_agent_config(user_id):
            return True
        user = await self.load_user(user_id)
        subjects = await self._subjects(user)
        repos = get_repositories(self._session)
        rows = await repos.agent.list_bindings(resource_type, resource_id)
        subject_set = set(subjects)
        for row in rows:
            if (row.subject_type, row.subject_id) not in subject_set:
                continue
            if USE_ACTIONS.intersection(row.actions or []):
                return True
        return False

    async def list_visible_app_keys(self, user_id: uuid.UUID, app_keys: Sequence[str]) -> list[str]:
        visible: list[str] = []
        for app_key in app_keys:
            if app_key == "auth" or await self.can_use_app(user_id, app_key):
                visible.append(app_key)
        return visible

    async def _app_allowed(
        self,
        user_id: uuid.UUID,
        app_key: str,
        needed: frozenset[str],
        *,
        use_tier: bool,
    ) -> bool:
        if await self.is_platform_admin(user_id):
            return True
        bound = await self._binding_actions_for_app(user_id, app_key)
        if needed.intersection(bound):
            return True
        grant_actions = ("read", "use", "write", "admin") if use_tier else ("write", "admin")
        for action in grant_actions:
            result = await self._perm.check(
                PermissionCheckRequest(
                    user_id=user_id,
                    asset_type=APP_ASSET_TYPE,
                    asset_key=app_key,
                    action=action,
                )
            )
            if result.allowed:
                return True
        return False

    async def _binding_actions_for_app(self, user_id: uuid.UUID, app_key: str) -> set[str]:
        repos = get_repositories(self._session)
        asset = await repos.permission.get_asset_by_key(APP_ASSET_TYPE, app_key)
        if asset is None:
            return set()
        user = await self.load_user(user_id)
        subjects = await self._subjects(user)
        rows = await repos.agent.list_bindings_for_resource_subjects(
            APP_RESOURCE_TYPE,
            asset.id,
            subjects,
        )
        merged: set[str] = set()
        for row in rows:
            merged.update(str(item) for item in (row.actions or []))
        return merged

    async def _subjects(self, user: User) -> list[tuple[str, uuid.UUID]]:
        repos = get_repositories(self._session)
        roles = await repos.permission.list_user_roles(user.id)
        items: list[tuple[str, uuid.UUID]] = [
            ("user", user.id),
            ("organization", user.organization_id),
        ]
        if user.department_id is not None:
            items.append(("department", user.department_id))
        for role in roles:
            items.append(("role", role.id))
        return items
