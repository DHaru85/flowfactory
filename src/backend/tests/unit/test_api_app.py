"""应用层 FastAPI：鉴权、会话、SSE。"""

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
from api.deps import FakeWorkflowRuntime, set_workflow_runtime_override  # noqa: E402
from data_schema.permission.models import Organization, User  # noqa: E402
from service.auth.password import hash_password  # noqa: E402
from service.database.session import session_scope  # noqa: E402


async def _user() -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"api-{suffix}", name="api-org", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"api-{suffix}",
            display_name="api",
            organization_id=org.id,
            status="active",
            password_hash=hash_password("pw-ok"),
            is_superuser=True,
        )
        session.add(user)
        await session.flush()
        session.expunge(user)
        return user


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    set_workflow_runtime_override(FakeWorkflowRuntime())
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    set_workflow_runtime_override(None)


@pytest.mark.asyncio
async def test_health() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "auth" in body["apps"]
    assert "conversation" in body["apps"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_register_and_conflict(api_client: AsyncClient) -> None:
    suffix = uuid4().hex[:8]
    username = f"reg-{suffix}"
    created = await api_client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pw-ok-ok"},
    )
    assert created.status_code == 200
    token = created.json()["access_token"]
    me = await api_client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == username
    dup = await api_client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pw-ok-ok"},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "username_conflict"
    user = await _user()
    denied = await api_client.get("/api/v1/conversations")
    assert denied.status_code == 401
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "pw-ok"},
    )
    assert login.status_code == 200
    pair = login.json()
    me = await api_client.get("/api/v1/auth/me", headers=_auth(pair["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == user.username


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_message_and_sse(api_client: AsyncClient) -> None:
    user = await _user()
    flow_id = uuid4()
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "pw-ok"},
    )
    token = login.json()["access_token"]
    headers = _auth(token)
    conv = await api_client.post(
        "/api/v1/conversations",
        json={"title": "t", "flow_id": str(flow_id)},
        headers=headers,
    )
    assert conv.status_code == 200
    cid = conv.json()["id"]

    sent = await api_client.post(
        "/api/v1/conversations/messages",
        headers=headers,
        json={"conversation_id": cid, "flow_id": str(flow_id), "content": "你好"},
    )
    assert sent.status_code == 200
    payload = sent.json()
    assert payload["conversation_id"] == cid
    assert payload["run_id"]

    listed = await api_client.get(f"/api/v1/conversations/{cid}/messages", headers=headers)
    assert listed.status_code == 200
    roles = {item["role"] for item in listed.json()}
    assert roles == {"user", "assistant"}
