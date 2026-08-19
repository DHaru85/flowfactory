"""鉴权错误。"""

from __future__ import annotations


class AuthError(Exception):
    """服务层认证/授权失败，供应用层映射 HTTPException。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


INVALID_CREDENTIALS = "invalid_credentials"
USER_DISABLED = "user_disabled"
TOKEN_EXPIRED = "token_expired"
TOKEN_INVALID = "token_invalid"
TOKEN_REVOKED = "token_revoked"
REFRESH_REUSE = "refresh_reuse"
LDAP_UNAVAILABLE = "ldap_unavailable"
LDAP_PROVISION_FAILED = "ldap_provision_failed"
USER_NOT_FOUND = "user_not_found"
