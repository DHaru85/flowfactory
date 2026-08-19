"""LDAP 目录适配器协议。"""

from __future__ import annotations

from typing import Protocol

from service.auth.schemas import (
    ExternalIdentityMapping,
    LdapEntrySnapshot,
    LdapSearchFilter,
    LdapSyncPayload,
    LdapSyncResult,
)


class LdapAdapter(Protocol):
    """目录访问。实现不得直接依赖 ORM；映射结果交给 provision。"""

    def connect(self) -> None:
        """建立目录连接。"""

    def close(self) -> None:
        """释放连接。"""

    def bind_user(self, username: str, password: str) -> LdapEntrySnapshot | None:
        """用户绑定验证；失败返回 None。登录链路预留点。"""

    def fetch_entries(self, query: LdapSearchFilter) -> list[LdapEntrySnapshot]:
        """按过滤器拉取条目。"""

    def map_identity(self, entry: LdapEntrySnapshot) -> ExternalIdentityMapping:
        """单条目映射为外部身份 DTO。"""

    def sync_users(self, payload: LdapSyncPayload) -> LdapSyncResult:
        """同步用户；写库由调用方或实现内通过回调完成。"""

    def sync_departments(self, payload: LdapSyncPayload) -> LdapSyncResult:
        """同步组织/部门树。"""
