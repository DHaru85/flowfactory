"""登记 sys_asset 与绑定（不调用 PermissionService.check）。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.apps.agent_config.schemas import BindingItem, ResourceType, SubjectType
from api.errors import http_error
from data_schema.agent.models import AgentResourceBinding
from data_schema.permission.models import Asset, Department
from service.persistence.factory import get_repositories

_SUBJECT_TYPES: frozenset[str] = frozenset({"organization", "department", "role", "user"})


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
    resource_type: ResourceType,
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
    resource_type: ResourceType,
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
