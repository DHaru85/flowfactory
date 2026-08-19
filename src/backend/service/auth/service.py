"""AuthService：登录、刷新、吊销、校验。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from data_schema.permission.models import RefreshToken, User
from service.auth.errors import (
    INVALID_CREDENTIALS,
    REFRESH_REUSE,
    TOKEN_EXPIRED,
    TOKEN_INVALID,
    TOKEN_REVOKED,
    USER_DISABLED,
    AuthError,
)
from service.auth.jwt_codec import JwtCodec, build_access_claims
from service.auth.ldap.factory import get_ldap_adapter
from service.auth.ldap.provision import provision_ldap_user
from service.auth.password import verify_password
from service.auth.schemas import (
    LoginCredentials,
    LogoutRequest,
    RefreshTokenRequest,
    TokenClaims,
    TokenPairResponse,
)
from service.auth.tokens import hash_refresh_token, new_refresh_token, sanitize_client_ip
from service.cache.client import get_redis_client
from service.cache.stores import JwtCacheStore
from service.persistence.factory import get_repositories
from settings.config import get_settings


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        codec: JwtCodec | None = None,
        jwt_store: JwtCacheStore | None = None,
        ldap_enabled: bool | None = None,
    ) -> None:
        self._session = session
        self._codec = codec or JwtCodec()
        self._jwt_store = jwt_store or JwtCacheStore(get_redis_client())
        cfg = get_settings()
        self._ldap_enabled = cfg.ldap_enabled if ldap_enabled is None else ldap_enabled

    async def login(self, credentials: LoginCredentials) -> TokenPairResponse:
        user = await self._authenticate(credentials.username, credentials.password)
        self._assert_active(user)
        user.last_login_at = datetime.now(UTC)
        await self._session.flush()
        return await self._issue_pair(
            user,
            family_id=uuid.uuid4(),
            user_agent=credentials.user_agent,
            client_ip=credentials.client_ip,
        )

    async def refresh(self, request: RefreshTokenRequest) -> TokenPairResponse:
        repos = get_repositories(self._session)
        token_hash = hash_refresh_token(request.refresh_token)
        record = await repos.permission.get_refresh_by_hash(token_hash)
        if record is None:
            raise AuthError(TOKEN_INVALID, "refresh token 无效")
        now = datetime.now(UTC)
        if record.revoked_at is not None:
            await repos.permission.revoke_refresh_family(record.family_id, now)
            self._jwt_store.clear_user_sessions(record.user_id)
            raise AuthError(REFRESH_REUSE, "refresh token 重用，已吊销该会话族")
        if record.expires_at <= now:
            raise AuthError(TOKEN_EXPIRED, "refresh token 已过期")
        user = await repos.permission.user.get(record.user_id)
        if user is None:
            raise AuthError(TOKEN_INVALID, "refresh 对应用户不存在")
        self._assert_active(user)
        record.revoked_at = now
        await self._session.flush()
        return await self._issue_pair(
            user,
            family_id=record.family_id,
            user_agent=request.user_agent,
            client_ip=request.client_ip,
        )

    async def logout(self, request: LogoutRequest) -> None:
        cfg = get_settings()
        now = int(datetime.now(UTC).timestamp())
        if request.access_exp is not None:
            exp = request.access_exp
        else:
            exp = now + cfg.jwt_access_ttl_seconds
        ttl = max(1, exp - now)
        self._jwt_store.blacklist_jti(request.access_jti, ttl)
        if not request.refresh_token:
            return
        repos = get_repositories(self._session)
        token_hash = hash_refresh_token(request.refresh_token)
        record = await repos.permission.get_refresh_by_hash(token_hash)
        if record is None or record.revoked_at is not None:
            return
        record.revoked_at = datetime.now(UTC)
        self._jwt_store.remove_session_refresh(record.user_id, str(record.jti))
        await self._session.flush()

    async def revoke_all_sessions(self, user_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        self._jwt_store.set_revoke_before(user_id, int(now.timestamp()))
        self._jwt_store.clear_user_sessions(user_id)
        repos = get_repositories(self._session)
        await repos.permission.revoke_user_refresh_tokens(user_id, now)
        await self._session.flush()

    async def verify_access_token(self, raw_token: str) -> TokenClaims:
        claims = self._codec.decode(raw_token)
        if self._jwt_store.is_jti_blacklisted(claims.jti):
            raise AuthError(TOKEN_REVOKED, "access token 已登出")
        revoke_before = self._jwt_store.get_revoke_before(claims.sub)
        if revoke_before is not None and claims.iat <= revoke_before:
            raise AuthError(TOKEN_REVOKED, "access token 已整体作废")
        repos = get_repositories(self._session)
        user = await repos.permission.user.get(claims.sub)
        if user is None or user.deleted_at is not None:
            raise AuthError(TOKEN_REVOKED, "用户不存在")
        self._assert_active(user)
        return claims

    async def _authenticate(self, username: str, password: str) -> User:
        repos = get_repositories(self._session)
        user = await repos.permission.get_user_by_username(username)
        if user is not None and user.password_hash:
            if verify_password(password, user.password_hash):
                return user
            raise AuthError(INVALID_CREDENTIALS, "用户名或密码错误")
        if self._ldap_enabled:
            ldap_user = await self._authenticate_ldap(username, password)
            if ldap_user is not None:
                return ldap_user
        raise AuthError(INVALID_CREDENTIALS, "用户名或密码错误")

    async def _authenticate_ldap(self, username: str, password: str) -> User | None:
        adapter = get_ldap_adapter()
        snapshot = adapter.bind_user(username, password)
        if snapshot is None:
            return None
        mapping = adapter.map_identity(snapshot)
        user, _created = await provision_ldap_user(self._session, mapping)
        return user

    def _assert_active(self, user: User) -> None:
        if user.status != "active" or user.deleted_at is not None:
            raise AuthError(USER_DISABLED, "用户已禁用")

    async def _issue_pair(
        self,
        user: User,
        *,
        family_id: uuid.UUID,
        user_agent: str | None,
        client_ip: str | None,
    ) -> TokenPairResponse:
        cfg = get_settings()
        repos = get_repositories(self._session)
        roles = await repos.permission.list_user_role_codes(user.id)
        claims = build_access_claims(user_id=user.id, org_id=user.organization_id, roles=roles)
        access = self._codec.encode(claims)
        raw_refresh = new_refresh_token()
        now = datetime.now(UTC)
        record = RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            family_id=family_id,
            jti=claims.jti,
            expires_at=now + timedelta(seconds=cfg.jwt_refresh_ttl_seconds),
            user_agent=user_agent,
            client_ip=sanitize_client_ip(client_ip),
        )
        await repos.permission.refresh_token.add(record)
        self._jwt_store.add_session_refresh(
            user.id,
            str(record.jti),
            cfg.jwt_refresh_ttl_seconds,
        )
        await self._session.flush()
        return TokenPairResponse(
            access_token=access,
            refresh_token=raw_refresh,
            expires_in=cfg.jwt_access_ttl_seconds,
        )
