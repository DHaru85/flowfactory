"""将 LDAP 映射写入本地用户与外部身份。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.permission.models import ExternalIdentity, Organization, User
from service.auth.errors import LDAP_PROVISION_FAILED, AuthError
from service.auth.schemas import ExternalIdentityMapping
from service.persistence.factory import get_repositories
from settings.config import get_settings


async def provision_ldap_user(
    session: AsyncSession,
    mapping: ExternalIdentityMapping,
) -> tuple[User, bool]:
    """按 external_id / username 关联或创建本地用户。返回 (user, created)。"""
    repos = get_repositories(session)
    existing = await repos.permission.get_external_identity("ldap", mapping.external_id)
    now = datetime.now(UTC)
    if existing is not None:
        user = await repos.permission.user.get(existing.user_id)
        if user is None:
            raise AuthError(LDAP_PROVISION_FAILED, "外部身份指向的用户不存在")
        existing.ldap_dn = mapping.ldap_dn
        existing.attrs_snapshot = mapping.attrs
        existing.last_synced_at = now
        user.ldap_dn = mapping.ldap_dn
        if mapping.email:
            user.email = mapping.email
        if mapping.display_name:
            user.display_name = mapping.display_name
        await session.flush()
        return user, False

    user = await repos.permission.get_user_by_username(mapping.username)
    if user is None:
        org = await _resolve_default_org(session)
        user = User(
            username=mapping.username,
            email=mapping.email,
            password_hash=None,
            display_name=mapping.display_name,
            organization_id=org.id,
            status="active",
            ldap_dn=mapping.ldap_dn,
        )
        await repos.permission.user.add(user)
        created = True
    else:
        user.ldap_dn = mapping.ldap_dn
        created = False

    identity = ExternalIdentity(
        provider="ldap",
        external_id=mapping.external_id,
        ldap_dn=mapping.ldap_dn,
        user_id=user.id,
        attrs_snapshot=mapping.attrs,
        last_synced_at=now,
    )
    await repos.permission.external_identity.add(identity)
    await session.flush()
    return user, created


async def _resolve_default_org(session: AsyncSession) -> Organization:
    code = get_settings().ldap_default_org_code
    repos = get_repositories(session)
    if code:
        org = await repos.permission.get_organization_by_code(code)
        if org is not None:
            return org
    orgs = await repos.permission.organization.list(limit=1)
    if not orgs:
        raise AuthError(LDAP_PROVISION_FAILED, "无法为 LDAP 用户确定组织")
    return orgs[0]
