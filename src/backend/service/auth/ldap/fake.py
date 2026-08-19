"""内存 LDAP，供单测与未接目录时的注入。"""

from __future__ import annotations

from service.auth.schemas import (
    ExternalIdentityMapping,
    LdapEntrySnapshot,
    LdapSearchFilter,
    LdapSyncPayload,
    LdapSyncResult,
)


class FakeLdapAdapter:
    """以 username 为键的内存目录。"""

    def __init__(self) -> None:
        self.entries: dict[str, tuple[str, LdapEntrySnapshot]] = {}
        self.connected = False
        self.bind_calls: list[str] = []

    def seed(self, password: str, entry: LdapEntrySnapshot) -> None:
        self.entries[entry.username] = (password, entry)

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def bind_user(self, username: str, password: str) -> LdapEntrySnapshot | None:
        self.bind_calls.append(username)
        stored = self.entries.get(username)
        if stored is None:
            return None
        expected, entry = stored
        if expected != password:
            return None
        return entry

    def fetch_entries(self, query: LdapSearchFilter) -> list[LdapEntrySnapshot]:
        del query
        return [item[1] for item in self.entries.values()]

    def map_identity(self, entry: LdapEntrySnapshot) -> ExternalIdentityMapping:
        return ExternalIdentityMapping(
            external_id=entry.external_id,
            ldap_dn=entry.dn,
            username=entry.username,
            email=entry.email,
            display_name=entry.display_name,
            attrs=entry.attrs,
        )

    def sync_users(self, payload: LdapSyncPayload) -> LdapSyncResult:
        if payload.dry_run:
            return LdapSyncResult(created=len(self.entries), updated=0, disabled=0)
        return LdapSyncResult(created=len(self.entries), updated=0, disabled=0)

    def sync_departments(self, payload: LdapSyncPayload) -> LdapSyncResult:
        del payload
        return LdapSyncResult()
