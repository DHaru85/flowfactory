"""鉴权序列化对象。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

TokenType = Literal["access"]
BearerType = Literal["Bearer"]
LdapSyncMode = Literal["full", "incremental"]


class LoginCredentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)
    user_agent: str | None = Field(default=None, max_length=512)
    client_ip: str | None = None


class TokenClaims(BaseModel):
    sub: uuid.UUID
    jti: uuid.UUID
    iat: int
    exp: int
    org_id: uuid.UUID
    roles: list[str]
    token_type: TokenType = "access"


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: BearerType = "Bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str
    user_agent: str | None = None
    client_ip: str | None = None


class LogoutRequest(BaseModel):
    access_jti: uuid.UUID
    refresh_token: str | None = None
    access_exp: int | None = None


class PermissionCheckRequest(BaseModel):
    user_id: uuid.UUID
    asset_type: str
    asset_key: str
    action: str


class PermissionCheckResult(BaseModel):
    allowed: bool
    reason: str | None = None


class AssetRef(BaseModel):
    asset_type: str
    asset_key: str
    name: str


class LdapConnectionConfig(BaseModel):
    host: str
    port: int = 389
    use_tls: bool = False
    bind_dn: str = ""
    bind_password: SecretStr = SecretStr("")
    user_search_base: str = ""
    group_search_base: str | None = None
    user_filter: str = "(uid={username})"
    username_attr: str = "uid"


class LdapSearchFilter(BaseModel):
    base_dn: str
    filter_expr: str
    attributes: list[str]


class LdapEntrySnapshot(BaseModel):
    dn: str
    external_id: str
    username: str
    email: str | None = None
    display_name: str
    department_dn: str | None = None
    attrs: dict[str, object] = Field(default_factory=dict)


class ExternalIdentityMapping(BaseModel):
    provider: Literal["ldap"] = "ldap"
    external_id: str
    ldap_dn: str
    username: str
    email: str | None = None
    display_name: str
    attrs: dict[str, object] = Field(default_factory=dict)


class LdapSyncPayload(BaseModel):
    job_id: uuid.UUID
    mode: LdapSyncMode = "full"
    since: datetime | None = None
    user_filter: str | None = None
    dry_run: bool = False


class LdapSyncResult(BaseModel):
    created: int = 0
    updated: int = 0
    disabled: int = 0
    errors: list[str] = Field(default_factory=list)
