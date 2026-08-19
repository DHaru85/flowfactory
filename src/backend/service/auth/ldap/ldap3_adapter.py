"""ldap3 真实目录适配器。仅在 ldap_enabled 且配置齐全时使用。"""

from __future__ import annotations

from loguru import logger

from service.auth.errors import LDAP_UNAVAILABLE, AuthError
from service.auth.schemas import (
    ExternalIdentityMapping,
    LdapConnectionConfig,
    LdapEntrySnapshot,
    LdapSearchFilter,
    LdapSyncPayload,
    LdapSyncResult,
)
from settings.config import get_settings


class Ldap3Adapter:
    """后续接入真实 LDAP 时启用；缺依赖或未连接时方法失败可预期。"""

    def __init__(self, config: LdapConnectionConfig | None = None) -> None:
        self._config = config or connection_config_from_settings()
        self._conn: object | None = None

    def connect(self) -> None:
        try:
            from ldap3 import ALL, Connection, Server
        except ImportError as exc:
            raise AuthError(LDAP_UNAVAILABLE, "未安装 ldap3") from exc
        if not self._config.host:
            raise AuthError(LDAP_UNAVAILABLE, "未配置 ldap_host")
        server = Server(
            self._config.host,
            port=self._config.port,
            use_ssl=self._config.use_tls,
            get_info=ALL,
        )
        password = self._config.bind_password.get_secret_value()
        self._conn = Connection(
            server,
            user=self._config.bind_dn or None,
            password=password or None,
            auto_bind=True,
        )

    def close(self) -> None:
        conn = self._conn
        if conn is not None:
            unbind = getattr(conn, "unbind", None)
            if callable(unbind):
                unbind()
        self._conn = None

    def bind_user(self, username: str, password: str) -> LdapEntrySnapshot | None:
        """用服务账号搜索 DN，再以用户凭据 bind。"""
        try:
            from ldap3 import Connection, Server
        except ImportError:
            logger.error("ldap3 不可用，无法 bind_user")
            return None
        if not password:
            return None
        if self._conn is None:
            self.connect()
        conn = self._conn
        assert conn is not None
        filter_expr = self._config.user_filter.format(username=_escape_ldap(username))
        search = getattr(conn, "search")
        ok = search(
            self._config.user_search_base,
            filter_expr,
            attributes=["*", "+"],
        )
        if not ok:
            return None
        entries = list(getattr(conn, "entries", []))
        if not entries:
            return None
        dn = str(entries[0].entry_dn)
        server = Server(
            self._config.host,
            port=self._config.port,
            use_ssl=self._config.use_tls,
        )
        try:
            user_conn = Connection(server, user=dn, password=password, auto_bind=True)
            user_conn.unbind()
        except Exception:
            logger.info("LDAP 用户绑定失败 username={}", username)
            return None
        return _entry_to_snapshot(entries[0], self._config.username_attr)

    def fetch_entries(self, query: LdapSearchFilter) -> list[LdapEntrySnapshot]:
        if self._conn is None:
            self.connect()
        conn = self._conn
        assert conn is not None
        search = getattr(conn, "search")
        search(query.base_dn, query.filter_expr, attributes=query.attributes or ["*", "+"])
        snapshots: list[LdapEntrySnapshot] = []
        for entry in getattr(conn, "entries", []):
            snapshots.append(_entry_to_snapshot(entry, self._config.username_attr))
        return snapshots

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
        filter_expr = payload.user_filter or "(objectClass=person)"
        entries = self.fetch_entries(
            LdapSearchFilter(
                base_dn=self._config.user_search_base,
                filter_expr=filter_expr,
                attributes=["*", "+"],
            )
        )
        if payload.dry_run:
            return LdapSyncResult(created=0, updated=len(entries), errors=[])
        return LdapSyncResult(updated=len(entries))

    def sync_departments(self, payload: LdapSyncPayload) -> LdapSyncResult:
        del payload
        return LdapSyncResult(errors=["部门同步尚未实现，预留接口"])


def connection_config_from_settings() -> LdapConnectionConfig:
    cfg = get_settings()
    return LdapConnectionConfig(
        host=cfg.ldap_host,
        port=cfg.ldap_port,
        use_tls=cfg.ldap_use_tls,
        bind_dn=cfg.ldap_bind_dn,
        bind_password=cfg.ldap_bind_password,
        user_search_base=cfg.ldap_user_search_base,
        group_search_base=cfg.ldap_group_search_base or None,
        user_filter=cfg.ldap_user_filter,
        username_attr=cfg.ldap_username_attr,
    )


def _escape_ldap(value: str) -> str:
    return (
        value.replace("\\", "\\5c")
        .replace("*", "\\2a")
        .replace("(", "\\28")
        .replace(")", "\\29")
        .replace("\x00", "\\00")
    )


def _entry_to_snapshot(entry: object, username_attr: str) -> LdapEntrySnapshot:
    dn = str(getattr(entry, "entry_dn", ""))
    raw = getattr(entry, "entry_attributes_as_dict", {}) or {}
    attrs: dict[str, object] = {}
    if isinstance(raw, dict):
        attrs = {str(key): _simplify_attr(value) for key, value in raw.items()}
    username = _first_str(attrs.get(username_attr)) or _first_str(attrs.get("uid")) or dn
    email = _first_str(attrs.get("mail"))
    display = _first_str(attrs.get("displayName")) or _first_str(attrs.get("cn")) or username
    external_id = _first_str(attrs.get("entryUUID")) or dn
    return LdapEntrySnapshot(
        dn=dn,
        external_id=external_id,
        username=username,
        email=email,
        display_name=display,
        department_dn=_first_str(attrs.get("ou")),
        attrs=attrs,
    )


def _simplify_attr(value: object) -> object:
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def _first_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        return str(value[0])
    text = str(value)
    return text or None
