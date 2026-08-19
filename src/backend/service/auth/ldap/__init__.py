"""LDAP 适配器。"""

from service.auth.ldap.factory import get_ldap_adapter, set_ldap_adapter_override
from service.auth.ldap.fake import FakeLdapAdapter
from service.auth.ldap.ldap3_adapter import Ldap3Adapter
from service.auth.ldap.protocol import LdapAdapter

__all__ = [
    "LdapAdapter",
    "FakeLdapAdapter",
    "Ldap3Adapter",
    "get_ldap_adapter",
    "set_ldap_adapter_override",
]
