"""LDAP 同步编排：适配器拉条目，provision 写库。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from service.auth.ldap.factory import get_ldap_adapter
from service.auth.ldap.provision import provision_ldap_user
from service.auth.schemas import LdapSearchFilter, LdapSyncPayload, LdapSyncResult
from settings.config import get_settings


async def execute_user_sync(session: AsyncSession, payload: LdapSyncPayload) -> LdapSyncResult:
    adapter = get_ldap_adapter()
    cfg = get_settings()
    query = LdapSearchFilter(
        base_dn=cfg.ldap_user_search_base or "",
        filter_expr=payload.user_filter or "(objectClass=*)",
        attributes=["*", "+"],
    )
    adapter.connect()
    try:
        entries = adapter.fetch_entries(query)
    finally:
        adapter.close()
    if payload.dry_run:
        return LdapSyncResult(created=len(entries))
    created = 0
    updated = 0
    errors: list[str] = []
    for entry in entries:
        try:
            mapping = adapter.map_identity(entry)
            _user, was_created = await provision_ldap_user(session, mapping)
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception as exc:
            errors.append(f"{entry.username}: {exc}")
    return LdapSyncResult(created=created, updated=updated, errors=errors)
