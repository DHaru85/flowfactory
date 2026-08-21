"""管理员用户列表与授权状态。"""

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


async def _user(*, superuser: bool, org: Organization | None = None, prefix: str = "u") -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        if org is None:
            org = Organization(code=f"{prefix}-{suffix}", name="org", status="active")
            session.add(org)
            await session.flush()
            org_id = org.id
        else:
            org_id = org.id
        user = User(
            username=f"{prefix}-{suffix}",
            display_name=prefix,
            organization_id=org_id,
            status="active",
            password_hash=hash_password("pw-ok"),
            is_superuser=superuser,
        )
        session.add(user)
        await session.flush()
        session.expunge(user)
        if org is not None:
            session.expunge(org)
        return user


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_lists_and_disables_user(api_client: AsyncClient) -> None:
    admin = await _user(superuser=True, prefix="adm")
    other = await _user(superuser=False, prefix="mem")
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": admin.username, "password": "pw-ok"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    listed = await api_client.get("/api/v1/auth/users", headers=headers)
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert str(admin.id) in ids
    assert str(other.id) in ids

    patched = await api_client.patch(
        f"/api/v1/auth/users/{other.id}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "disabled"

    denied = await api_client.post(
        "/api/v1/auth/login",
        json={"username": other.username, "password": "pw-ok"},
    )
    assert denied.status_code == 401

    self_patch = await api_client.patch(
        f"/api/v1/auth/users/{admin.id}",
        headers=headers,
        json={"status": "disabled"},
    )
    assert self_patch.status_code == 400
