"""Studio 应用层：JWT、Flow v1 草稿与发布。"""

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
from data_schema.agent.models import AgentLlm, AgentProfile, AgentTool  # noqa: E402
from data_schema.permission.models import Organization, User  # noqa: E402
from service.auth.password import hash_password  # noqa: E402
from service.database.session import session_scope  # noqa: E402
from service.runtime.definition_v1 import empty_flow_definition  # noqa: E402


async def _user() -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"st-{suffix}", name="st-org", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"st-{suffix}",
            display_name="st",
            organization_id=org.id,
            status="active",
            password_hash=hash_password("pw-ok"),
        )
        session.add(user)
        await session.flush()
        session.expunge(user)
        return user


async def _profile() -> AgentProfile:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"pf-{suffix}", name="pf", status="active")
        session.add(org)
        await session.flush()
        llm = AgentLlm(
            code=f"llm-{suffix}",
            provider="local",
            model_name="demo",
            config={},
            is_active=True,
        )
        session.add(llm)
        await session.flush()
        profile = AgentProfile(
            code=f"prof-{suffix}",
            name="p",
            system_prompt="sys",
            default_llm_id=llm.id,
            skill_ids=[],
            owner_organization_id=org.id,
        )
        session.add(profile)
        tool = AgentTool(
            code=f"tool-{suffix}",
            name="t",
            kind="builtin",
            schema_={"type": "object"},
            config={},
        )
        session.add(tool)
        await session.flush()
        session.expunge(profile)
        session.expunge(llm)
        session.expunge(tool)
        return profile


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_health_includes_studio() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert "studio" in resp.json()["apps"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_studio_requires_jwt(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/studio/flows")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_studio_flow_lifecycle(api_client: AsyncClient) -> None:
    user = await _user()
    profile = await _profile()
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "pw-ok"},
    )
    token = login.json()["access_token"]
    headers = _auth(token)

    created = await api_client.post(
        "/api/v1/studio/flows",
        headers=headers,
        json={
            "code": f"wf-{uuid4().hex[:8]}",
            "name": "demo",
            "profile_id": str(profile.id),
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "draft"
    assert body["definition"]["schema_version"] == 1
    flow_id = body["id"]

    bad = await api_client.patch(
        f"/api/v1/studio/flows/{flow_id}",
        headers=headers,
        json={"definition": {"schema_version": 1, "nodes": []}},
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "definition_invalid"

    ok_def = empty_flow_definition().model_dump(mode="json")
    patched = await api_client.patch(
        f"/api/v1/studio/flows/{flow_id}",
        headers=headers,
        json={"name": "demo2", "definition": ok_def},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "demo2"

    published = await api_client.post(
        f"/api/v1/studio/flows/{flow_id}/publish",
        headers=headers,
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    locked = await api_client.patch(
        f"/api/v1/studio/flows/{flow_id}",
        headers=headers,
        json={"name": "nope"},
    )
    assert locked.status_code == 400
    assert locked.json()["code"] == "flow_not_draft"

    draft2 = await api_client.post(
        f"/api/v1/studio/flows/{flow_id}/new-draft",
        headers=headers,
    )
    assert draft2.status_code == 200
    assert draft2.json()["status"] == "draft"
    assert draft2.json()["version"] == published.json()["version"] + 1

    codes = await api_client.get("/api/v1/studio/flows/published-codes", headers=headers)
    assert codes.status_code == 200
    assert any(item["code"] == body["code"] for item in codes.json())

    profiles = await api_client.get("/api/v1/studio/profiles", headers=headers)
    assert profiles.status_code == 200
    assert any(item["id"] == str(profile.id) for item in profiles.json())

    llms = await api_client.get("/api/v1/studio/llms", headers=headers)
    assert llms.status_code == 200
    assert llms.json()

    tools = await api_client.get("/api/v1/studio/tools", headers=headers)
    assert tools.status_code == 200
    assert tools.json()
