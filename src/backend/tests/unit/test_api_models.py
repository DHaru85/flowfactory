"""模型应用：密钥打码与 JWT。"""

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
from api.apps.models.schemas import redact_llm_config  # noqa: E402
from data_schema.permission.models import Organization, User  # noqa: E402
from service.auth.password import hash_password  # noqa: E402
from service.database.session import session_scope  # noqa: E402
from service.runtime.llm import (  # noqa: E402
    FakeChatCompletionClient,
    resolve_llm_client,
    set_chat_client_override,
)


def test_redact_llm_config_strips_api_key() -> None:
    public, has_key = redact_llm_config({"base_url": "http://x", "api_key": "secret"})
    assert has_key is True
    assert "api_key" not in public
    assert public["base_url"] == "http://x"


@pytest.mark.asyncio
async def test_resolve_llm_client_honors_override() -> None:
    fake = FakeChatCompletionClient("ok")
    set_chat_client_override(fake)
    try:
        client = await resolve_llm_client(code="missing")
        assert client is fake
    finally:
        set_chat_client_override(None)


async def _user() -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"md-{suffix}", name="md", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"md-{suffix}",
            display_name="md",
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
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_health_includes_models() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert "models" in resp.json()["apps"]
    assert "agent_config" in resp.json()["apps"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_models_requires_jwt(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/models/llms")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_models_llm_secret_not_returned(api_client: AsyncClient) -> None:
    user = await _user()
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "pw-ok"},
    )
    headers = _auth(login.json()["access_token"])
    code = f"llm-{uuid4().hex[:8]}"
    created = await api_client.post(
        "/api/v1/models/llms",
        headers=headers,
        json={
            "code": code,
            "provider": "local",
            "model_name": "demo",
            "config": {"base_url": "http://llm", "api_key": "super-secret"},
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["has_api_key"] is True
    assert "api_key" not in body["config"]
    assert body["config"]["base_url"] == "http://llm"
    llm_id = body["id"]

    patched = await api_client.patch(
        f"/api/v1/models/llms/{llm_id}",
        headers=headers,
        json={"config": {"base_url": "http://llm2"}},
    )
    assert patched.status_code == 200
    assert patched.json()["has_api_key"] is True
    assert patched.json()["config"]["base_url"] == "http://llm2"

    studio = await api_client.get("/api/v1/studio/llms", headers=headers)
    assert studio.status_code == 200
    assert any(item["code"] == code for item in studio.json())

    off = await api_client.post(f"/api/v1/models/llms/{llm_id}/deactivate", headers=headers)
    assert off.status_code == 200
    assert off.json()["is_active"] is False

    removed = await api_client.delete(f"/api/v1/models/llms/{llm_id}", headers=headers)
    assert removed.status_code == 200
    missing = await api_client.get(f"/api/v1/models/llms/{llm_id}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_llm_rejects_bad_base_url(api_client: AsyncClient) -> None:
    user = await _user()
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "pw-ok"},
    )
    headers = _auth(login.json()["access_token"])
    created = await api_client.post(
        "/api/v1/models/llms",
        headers=headers,
        json={
            "code": f"llm-{uuid4().hex[:8]}",
            "provider": "local",
            "model_name": "demo",
            "config": {"base_url": "htttp://192.168.129.50:8122/v1"},
        },
    )
    assert created.status_code == 400
    assert created.json()["code"] == "llm_base_url_invalid"
