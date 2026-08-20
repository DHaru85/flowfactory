"""Agent 配置：CRUD、绑定与工作流 Beat。"""

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
from service.persistence.factory import get_repositories  # noqa: E402
from service.runtime.definition_v1 import empty_flow_definition  # noqa: E402


async def _user() -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"ac-{suffix}", name="ac", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"ac-{suffix}",
            display_name="ac",
            organization_id=org.id,
            status="active",
            password_hash=hash_password("pw-ok"),
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_config_requires_jwt(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/agent-config/profiles")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_config_crud_bindings_beat_and_asset(api_client: AsyncClient) -> None:
    user = await _user()
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "pw-ok"},
    )
    headers = _auth(login.json()["access_token"])
    suffix = uuid4().hex[:8]

    llm = await api_client.post(
        "/api/v1/models/llms",
        headers=headers,
        json={"code": f"l-{suffix}", "provider": "local", "model_name": "m"},
    )
    assert llm.status_code == 200
    llm_id = llm.json()["id"]

    mcp = await api_client.post(
        "/api/v1/agent-config/mcp-servers",
        headers=headers,
        json={
            "code": f"mcp-{suffix}",
            "name": "mcp",
            "transport": "sse",
            "config": {"url": "http://mcp"},
        },
    )
    assert mcp.status_code == 200
    mcp_id = mcp.json()["id"]

    tool = await api_client.post(
        "/api/v1/agent-config/tools",
        headers=headers,
        json={
            "code": f"t-{suffix}",
            "name": "tool",
            "kind": "mcp",
            "schema": {"type": "object"},
            "mcp_server_id": mcp_id,
        },
    )
    assert tool.status_code == 200
    tool_id = tool.json()["id"]

    skill = await api_client.post(
        "/api/v1/agent-config/skills",
        headers=headers,
        json={
            "code": f"s-{suffix}",
            "name": "skill",
            "tool_ids": [tool_id],
            "prompt_template": "do",
        },
    )
    assert skill.status_code == 200
    skill_id = skill.json()["id"]

    profile = await api_client.post(
        "/api/v1/agent-config/profiles",
        headers=headers,
        json={
            "code": f"p-{suffix}",
            "name": "prof",
            "system_prompt": "sys",
            "default_llm_id": llm_id,
            "skill_ids": [skill_id],
        },
    )
    assert profile.status_code == 200
    profile_id = profile.json()["id"]

    bound = await api_client.put(
        f"/api/v1/agent-config/profiles/{profile_id}/bindings",
        headers=headers,
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
    assert bound.json()[0]["subject_type"] == "organization"

    got = await api_client.get(
        f"/api/v1/agent-config/profiles/{profile_id}/bindings",
        headers=headers,
    )
    assert got.status_code == 200
    assert len(got.json()) == 1

    flow = await api_client.post(
        "/api/v1/studio/flows",
        headers=headers,
        json={
            "code": f"wf-{suffix}",
            "name": "wf",
            "profile_id": profile_id,
            "definition": empty_flow_definition().model_dump(mode="json"),
        },
    )
    assert flow.status_code == 200
    flow_id = flow.json()["id"]

    missing = await api_client.post(
        "/api/v1/agent-config/beat-tasks",
        headers=headers,
        json={"code": f"b-miss-{suffix}", "cron": "* * * * *"},
    )
    assert missing.status_code == 422

    bad_flow = await api_client.post(
        "/api/v1/agent-config/beat-tasks",
        headers=headers,
        json={
            "code": f"b-bad-{suffix}",
            "flow_id": str(uuid4()),
            "cron": "* * * * *",
        },
    )
    assert bad_flow.status_code == 400
    assert bad_flow.json()["code"] == "flow_not_found"

    beat = await api_client.post(
        "/api/v1/agent-config/beat-tasks",
        headers=headers,
        json={
            "code": f"b-{suffix}",
            "flow_id": flow_id,
            "cron": "*/5 * * * *",
        },
    )
    assert beat.status_code == 200
    assert beat.json()["flow_id"] == flow_id
    assert "profile_id" not in beat.json()

    async with session_scope() as session:
        repos = get_repositories(session)
        asset = await repos.permission.get_asset_by_key("profile", profile_id)
        assert asset is not None
        assert asset.name == "prof"
        skill_asset = await repos.permission.get_asset_by_key("skill", skill_id)
        assert skill_asset is not None
        mcp_asset = await repos.permission.get_asset_by_key("mcp_server", mcp_id)
        assert mcp_asset is not None
        tool_asset = await repos.permission.get_asset_by_key("tool", tool_id)
        assert tool_asset is not None
