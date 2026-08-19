"""鉴权集成测试：PG + Redis。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from data_schema.permission.models import (  # noqa: E402
    Asset,
    Organization,
    Role,
    RoleAssetGrant,
    User,
    UserRole,
)
from service.auth.errors import (  # noqa: E402
    INVALID_CREDENTIALS,
    REFRESH_REUSE,
    TOKEN_INVALID,
    TOKEN_REVOKED,
    USER_DISABLED,
    AuthError,
)
from service.auth.ldap import FakeLdapAdapter, set_ldap_adapter_override  # noqa: E402
from service.auth.ldap.sync import execute_user_sync  # noqa: E402
from service.auth.password import hash_password  # noqa: E402
from service.auth.permission import PermissionService  # noqa: E402
from service.auth.schemas import (  # noqa: E402
    LdapEntrySnapshot,
    LdapSyncPayload,
    LoginCredentials,
    LogoutRequest,
    PermissionCheckRequest,
    RefreshTokenRequest,
)
from service.auth.service import AuthService  # noqa: E402
from service.database.session import session_scope  # noqa: E402
from service.persistence.factory import get_repositories  # noqa: E402
from settings.config import reset_settings  # noqa: E402


async def _org() -> Organization:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"auth-{suffix}", name="auth-org", status="active")
        session.add(org)
        await session.flush()
        session.expunge(org)
        return org


async def _user(
    org: Organization,
    *,
    password: str | None = "pw-ok",
    status: str = "active",
    superuser: bool = False,
) -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        user = User(
            username=f"u-{suffix}",
            display_name="tester",
            organization_id=org.id,
            status=status,
            is_superuser=superuser,
            password_hash=hash_password(password) if password else None,
        )
        session.add(user)
        await session.flush()
        session.expunge(user)
        return user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_verify_logout() -> None:
    org = await _org()
    user = await _user(org)
    async with session_scope() as session:
        auth = AuthService(session, ldap_enabled=False)
        pair = await auth.login(LoginCredentials(username=user.username, password="pw-ok"))
        claims = await auth.verify_access_token(pair.access_token)
        assert claims.sub == user.id
        await auth.logout(
            LogoutRequest(
                access_jti=claims.jti,
                refresh_token=pair.refresh_token,
                access_exp=claims.exp,
            )
        )
        with pytest.raises(AuthError) as exc:
            await auth.verify_access_token(pair.access_token)
        assert exc.value.code == TOKEN_REVOKED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bad_password_and_disabled() -> None:
    org = await _org()
    user = await _user(org)
    disabled = await _user(org, status="disabled")
    async with session_scope() as session:
        auth = AuthService(session, ldap_enabled=False)
        with pytest.raises(AuthError) as bad:
            await auth.login(LoginCredentials(username=user.username, password="nope"))
        assert bad.value.code == INVALID_CREDENTIALS
        with pytest.raises(AuthError) as off:
            await auth.login(LoginCredentials(username=disabled.username, password="pw-ok"))
        assert off.value.code == USER_DISABLED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_rotation_and_reuse() -> None:
    org = await _org()
    user = await _user(org)
    async with session_scope() as session:
        auth = AuthService(session, ldap_enabled=False)
        pair = await auth.login(LoginCredentials(username=user.username, password="pw-ok"))
        rotated = await auth.refresh(RefreshTokenRequest(refresh_token=pair.refresh_token))
        with pytest.raises(AuthError):
            await auth.refresh(RefreshTokenRequest(refresh_token=pair.refresh_token))
        # 重用旧 refresh 后整族作废，新 refresh 也不可用
        with pytest.raises(AuthError) as reuse:
            await auth.refresh(RefreshTokenRequest(refresh_token=rotated.refresh_token))
        assert reuse.value.code in {REFRESH_REUSE, TOKEN_INVALID}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_all_invalidates_access() -> None:
    org = await _org()
    user = await _user(org)
    async with session_scope() as session:
        auth = AuthService(session, ldap_enabled=False)
        pair = await auth.login(LoginCredentials(username=user.username, password="pw-ok"))
        await auth.revoke_all_sessions(user.id)
        with pytest.raises(AuthError) as exc:
            await auth.verify_access_token(pair.access_token)
        assert exc.value.code == TOKEN_REVOKED


@pytest.mark.integration
@pytest.mark.asyncio
async def test_permission_rbac() -> None:
    org = await _org()
    owner = await _user(org)
    admin = await _user(org, superuser=True)
    async with session_scope() as session:
        repos = get_repositories(session)
        role = Role(code=f"r-{uuid4().hex[:8]}", name="reader", scope="organization")
        await repos.permission.role.add(role)
        asset = Asset(
            asset_type="knowledge_collection",
            asset_key=f"kb-{uuid4().hex[:6]}",
            name="kb",
        )
        await repos.permission.asset.add(asset)
        session.add(UserRole(user_id=owner.id, role_id=role.id))
        session.add(
            RoleAssetGrant(role_id=role.id, asset_id=asset.id, actions=["read"])
        )
        await session.flush()
        svc = PermissionService(session)
        allowed = await svc.check(
            PermissionCheckRequest(
                user_id=owner.id,
                asset_type="knowledge_collection",
                asset_key=asset.asset_key,
                action="read",
            )
        )
        denied = await svc.check(
            PermissionCheckRequest(
                user_id=owner.id,
                asset_type="knowledge_collection",
                asset_key=asset.asset_key,
                action="write",
            )
        )
        super_ok = await svc.check(
            PermissionCheckRequest(
                user_id=admin.id,
                asset_type="knowledge_collection",
                asset_key=asset.asset_key,
                action="write",
            )
        )
        assert allowed.allowed is True
        assert denied.allowed is False
        assert super_ok.reason == "superuser"
        assets = await svc.list_accessible_assets(owner.id, "knowledge_collection", "read")
        assert any(item.asset_key == asset.asset_key for item in assets)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ldap_bind_login_and_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    org = await _org()
    fake = FakeLdapAdapter()
    username = f"ldap-{uuid4().hex[:8]}"
    fake.seed(
        "ldap-secret",
        LdapEntrySnapshot(
            dn=f"uid={username},dc=example,dc=com",
            external_id=str(uuid4()),
            username=username,
            email=f"{username}@example.com",
            display_name="LDAP User",
            attrs={"uid": username},
        ),
    )
    monkeypatch.setenv("FLOWFACTORY_LDAP_DEFAULT_ORG_CODE", org.code)
    reset_settings()
    set_ldap_adapter_override(fake)
    try:
        async with session_scope() as session:
            auth = AuthService(session, ldap_enabled=True)
            pair = await auth.login(LoginCredentials(username=username, password="ldap-secret"))
            claims = await auth.verify_access_token(pair.access_token)
            repos = get_repositories(session)
            local = await repos.permission.get_user_by_username(username)
            ident = await repos.permission.get_external_identity(
                "ldap", fake.entries[username][1].external_id
            )
            assert local is not None
            assert local.password_hash is None
            assert local.organization_id == org.id or local.organization_id is not None
            assert ident is not None
            assert claims.sub == local.id
            assert fake.bind_calls == [username]

        async with session_scope() as session:
            stats = await execute_user_sync(
                session,
                LdapSyncPayload(job_id=uuid4(), dry_run=True),
            )
            assert stats.created >= 1
    finally:
        set_ldap_adapter_override(None)
        reset_settings()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ldap_disabled_does_not_bind() -> None:
    fake = FakeLdapAdapter()
    fake.seed(
        "x",
        LdapEntrySnapshot(
            dn="uid=ghost,dc=x",
            external_id="1",
            username="ghost-user",
            display_name="g",
        ),
    )
    set_ldap_adapter_override(fake)
    try:
        async with session_scope() as session:
            auth = AuthService(session, ldap_enabled=False)
            with pytest.raises(AuthError) as exc:
                await auth.login(LoginCredentials(username="ghost-user", password="x"))
            assert exc.value.code == INVALID_CREDENTIALS
            assert fake.bind_calls == []
    finally:
        set_ldap_adapter_override(None)
