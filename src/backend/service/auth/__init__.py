"""用户鉴权服务层。"""

from service.auth.access import AccessControl
from service.auth.errors import AuthError
from service.auth.ldap import (
    FakeLdapAdapter,
    Ldap3Adapter,
    get_ldap_adapter,
    set_ldap_adapter_override,
)
from service.auth.password import hash_password, verify_password
from service.auth.permission import PermissionService
from service.auth.schemas import LoginCredentials, PermissionCheckRequest
from service.auth.service import AuthService

__all__ = [
    "AccessControl",
    "AuthError",
    "AuthService",
    "PermissionService",
    "LoginCredentials",
    "PermissionCheckRequest",
    "hash_password",
    "verify_password",
    "FakeLdapAdapter",
    "Ldap3Adapter",
    "get_ldap_adapter",
    "set_ldap_adapter_override",
]
