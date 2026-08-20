"""RBAC：应用两档与配置绑定可见性。"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.app import create_app  # noqa: E402
from data_schema.permission.models import Organization, User  # noqa: E402
from service.auth.password import hash_password  # noqa: E402
from service.database.session import session_scope  # noqa: E402


async def _make_user(*, superuser: bool = False) -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"rb-{suffix}", name="rb", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"rb-{suffix}",
            display_name="rb",
            organization_id=org.id,
            status="active",
            password_hash=hash_password("pw-ok"),
            is_superuser=superuser,
        )
        session.add(user)
        await session.flush()
        session.expunge(user)
        return user


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(client: AsyncClient, user: User) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "pw-ok"},
    )
    assert login.status_code == 200
    return _auth(login.json()["access_token"])


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_plain_user_forbidden_without_app_binding(api_client: AsyncClient) -> None:
    user = await _make_user()
    headers = await _login(api_client, user)
    denied = await api_client.get("/api/v1/agent-config/profiles", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["code"] == "app_forbidden"
    models = await api_client.get("/api/v1/models/llms", headers=headers)
    assert models.status_code == 403
    studio = await api_client.get("/api/v1/studio/flows", headers=headers)
    assert studio.status_code == 403
    conv = await api_client.get("/api/v1/conversations", headers=headers)
    assert conv.status_code == 403
    apps = await api_client.get("/api/v1/auth/apps", headers=headers)
    assert apps.status_code == 200
    keys = {item["app_key"] for item in apps.json()}
    assert keys == {"auth"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_app_use_and_control_two_tiers(api_client: AsyncClient) -> None:
    admin = await _make_user(superuser=True)
    user = await _make_user()
    admin_h = await _login(api_client, admin)
    user_h = await _login(api_client, user)

    bound = await api_client.put(
        "/api/v1/auth/apps/models/bindings",
        headers=admin_h,
        json={
            "bindings": [
                {
                    "subject_type": "organization",
                    "subject_id": str(user.organization_id),
                    "actions": ["read", "use"],
                }
            ]
        },
    )
    assert bound.status_code == 200

    listed = await api_client.get("/api/v1/models/llms", headers=user_h)
    assert listed.status_code == 200
    created = await api_client.post(
        "/api/v1/models/llms",
        headers=user_h,
        json={"code": f"l-{uuid4().hex[:8]}", "provider": "local", "model_name": "m"},
    )
    assert created.status_code == 403

    control = await api_client.put(
        "/api/v1/auth/apps/models/bindings",
        headers=admin_h,
        json={
            "bindings": [
                {
                    "subject_type": "organization",
                    "subject_id": str(user.organization_id),
                    "actions": ["write", "admin"],
                }
            ]
        },
    )
    assert control.status_code == 200
    created_ok = await api_client.post(
        "/api/v1/models/llms",
        headers=user_h,
        json={"code": f"l-{uuid4().hex[:8]}", "provider": "local", "model_name": "m"},
    )
    assert created_ok.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_profile_binding_visibility_and_404(api_client: AsyncClient) -> None:
    admin = await _make_user(superuser=True)
    viewer = await _make_user()
    outsider = await _make_user()
    admin_h = await _login(api_client, admin)
    viewer_h = await _login(api_client, viewer)
    out_h = await _login(api_client, outsider)

    both = await api_client.put(
        "/api/v1/auth/apps/agent_config/bindings",
        headers=admin_h,
        json={
            "bindings": [
                {
                    "subject_type": "organization",
                    "subject_id": str(viewer.organization_id),
                    "actions": ["read", "use"],
                },
                {
                    "subject_type": "organization",
                    "subject_id": str(outsider.organization_id),
                    "actions": ["read", "use"],
                },
            ]
        },
    )
    assert both.status_code == 200

    profile = await api_client.post(
        "/api/v1/agent-config/profiles",
        headers=admin_h,
        json={
            "code": f"p-{uuid4().hex[:8]}",
            "name": "p",
            "system_prompt": "s",
        },
    )
    assert profile.status_code == 200
    profile_id = profile.json()["id"]

    hidden = await api_client.get(
        f"/api/v1/agent-config/profiles/{profile_id}",
        headers=viewer_h,
    )
    assert hidden.status_code == 404
    listed = await api_client.get("/api/v1/agent-config/profiles", headers=viewer_h)
    assert listed.status_code == 200
    assert listed.json() == []

    forbidden_bind = await api_client.put(
        f"/api/v1/agent-config/profiles/{profile_id}/bindings",
        headers=viewer_h,
        json={
            "bindings": [
                {
                    "subject_type": "organization",
                    "subject_id": str(viewer.organization_id),
                    "actions": ["read", "use"],
                }
            ]
        },
    )
    assert forbidden_bind.status_code == 403

    await api_client.put(
        f"/api/v1/agent-config/profiles/{profile_id}/bindings",
        headers=admin_h,
        json={
            "bindings": [
                {
                    "subject_type": "organization",
                    "subject_id": str(viewer.organization_id),
                    "actions": ["read", "use"],
                }
            ]
        },
    )
    seen = await api_client.get(
        f"/api/v1/agent-config/profiles/{profile_id}",
        headers=viewer_h,
    )
    assert seen.status_code == 200
    miss = await api_client.get(
        f"/api/v1/agent-config/profiles/{profile_id}",
        headers=out_h,
    )
    assert miss.status_code == 404

    apps = await api_client.get("/api/v1/auth/apps", headers=viewer_h)
    keys = {item["app_key"] for item in apps.json()}
    assert "agent_config" in keys
    assert "models" not in keys
