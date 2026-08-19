"""LDAP 适配器工厂。"""

from __future__ import annotations

from service.auth.ldap.fake import FakeLdapAdapter
from service.auth.ldap.ldap3_adapter import Ldap3Adapter, connection_config_from_settings
from service.auth.ldap.protocol import LdapAdapter
from settings.config import get_settings

_override: LdapAdapter | None = None


def set_ldap_adapter_override(adapter: LdapAdapter | None) -> None:
    global _override
    _override = adapter


def get_ldap_adapter() -> LdapAdapter:
    if _override is not None:
        return _override
    cfg = get_settings()
    if not cfg.ldap_enabled:
        return FakeLdapAdapter()
    return Ldap3Adapter(connection_config_from_settings())
