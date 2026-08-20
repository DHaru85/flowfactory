"""登记 sys_asset、绑定与配置可见性。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.apps.agent_config.schemas import BindingItem, ResourceType, SubjectType
from api.errors import http_error
from data_schema.agent.models import (
    AgentMcpServer,
    AgentProfile,
    AgentResourceBinding,
    AgentSkill,
    AgentTool,
)
from data_schema.permission.models import Asset, Department
from service.auth.access import AccessControl
from service.persistence.factory import get_repositories

_SUBJECT_TYPES: frozenset[str] = frozenset({"organization", "department", "role", "user"})

TModel = TypeVar("TModel")


class _ListRepo(Protocol[TModel]):
    async def list(self, *, offset: int = 0, limit: int = 50) -> list[TModel]: ...

    async def list_by_ids(
        self,
        ids: Sequence[UUID],
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[TModel]: ...


async def upsert_config_asset(
    session: AsyncSession,
    *,
    asset_type: ResourceType,
    resource_id: UUID,
    name: str,
) -> None:
    repos = get_repositories(session)
    key = str(resource_id)
    existing = await repos.permission.get_asset_by_key(asset_type, key)
    if existing is None:
        await repos.permission.asset.add(
            Asset(asset_type=asset_type, asset_key=key, name=name, metadata_={})
        )
        return
    existing.name = name


async def assert_subject_exists(
    session: AsyncSession,
    subject_type: SubjectType,
    subject_id: UUID,
) -> None:
    repos = get_repositories(session)
    found: object | None
    if subject_type == "organization":
        found = await repos.permission.organization.get(subject_id)
    elif subject_type == "department":
        found = await session.get(Department, subject_id)
    elif subject_type == "role":
        found = await repos.permission.role.get(subject_id)
    else:
        found = await repos.permission.user.get(subject_id)
    if found is None:
        raise http_error(400, "subject_not_found", "绑定主体不存在")


def parse_resource_type(value: str) -> ResourceType:
    if value not in {"profile", "skill", "tool", "mcp_server"}:
        raise http_error(400, "resource_type_invalid", "未知 resource_type")
    return value  # type: ignore[return-value]


async def load_bindings(
    session: AsyncSession,
    resource_type: str,
    resource_id: UUID,
) -> list[BindingItem]:
    repos = get_repositories(session)
    rows = await repos.agent.list_bindings(resource_type, resource_id)
    return [
        BindingItem(
            subject_type=row.subject_type,  # type: ignore[arg-type]
            subject_id=row.subject_id,
            actions=list(row.actions),
        )
        for row in rows
        if row.subject_type in _SUBJECT_TYPES
    ]


async def save_bindings(
    session: AsyncSession,
    resource_type: str,
    resource_id: UUID,
    items: list[BindingItem],
) -> list[BindingItem]:
    for item in items:
        await assert_subject_exists(session, item.subject_type, item.subject_id)
    repos = get_repositories(session)
    rows = [
        AgentResourceBinding(
            resource_type=resource_type,
            resource_id=resource_id,
            subject_type=item.subject_type,
            subject_id=item.subject_id,
            actions=list(item.actions) or ["read", "use"],
        )
        for item in items
    ]
    await repos.agent.replace_bindings(resource_type, resource_id, rows)
    return items


async def _load_visible_rows(
    session: AsyncSession,
    user_id: UUID,
    resource_type: ResourceType,
    repo: _ListRepo[TModel],
    *,
    offset: int,
    limit: int,
) -> list[TModel]:
    access = AccessControl(session)
    bound = min(limit, 100)
    if await access.sees_all_agent_config(user_id):
        return await repo.list(offset=offset, limit=bound)
    ids = await access.visible_resource_ids(user_id, resource_type)
    return await repo.list_by_ids(ids, offset=offset, limit=bound)


async def load_visible_profile_rows(
    session: AsyncSession,
    user_id: UUID,
    *,
    offset: int,
    limit: int,
) -> list[AgentProfile]:
    repos = get_repositories(session)
    return await _load_visible_rows(
        session,
        user_id,
        "profile",
        repos.agent.profile,
        offset=offset,
        limit=limit,
    )


async def load_visible_skill_rows(
    session: AsyncSession,
    user_id: UUID,
    *,
    offset: int,
    limit: int,
) -> list[AgentSkill]:
    repos = get_repositories(session)
    return await _load_visible_rows(
        session, user_id, "skill", repos.agent.skill, offset=offset, limit=limit
    )


async def load_visible_tool_rows(
    session: AsyncSession,
    user_id: UUID,
    *,
    offset: int,
    limit: int,
) -> list[AgentTool]:
    repos = get_repositories(session)
    return await _load_visible_rows(
        session, user_id, "tool", repos.agent.tool, offset=offset, limit=limit
    )


async def load_visible_mcp_rows(
    session: AsyncSession,
    user_id: UUID,
    *,
    offset: int,
    limit: int,
) -> list[AgentMcpServer]:
    repos = get_repositories(session)
    return await _load_visible_rows(
        session, user_id, "mcp_server", repos.agent.mcp_server, offset=offset, limit=limit
    )


async def assert_config_visible(
    session: AsyncSession,
    user_id: UUID,
    resource_type: ResourceType,
    resource_id: UUID,
    *,
    missing_code: str,
    missing_message: str,
) -> None:
    repos = get_repositories(session)
    getters = {
        "profile": repos.agent.profile.get,
        "skill": repos.agent.skill.get,
        "tool": repos.agent.tool.get,
        "mcp_server": repos.agent.mcp_server.get,
    }
    row = await getters[resource_type](resource_id)
    if row is None:
        raise http_error(404, missing_code, missing_message)
    access = AccessControl(session)
    if not await access.can_see_agent_resource(user_id, resource_type, resource_id):
        raise http_error(404, missing_code, missing_message)
