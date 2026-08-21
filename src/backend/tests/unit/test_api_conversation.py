"""会话路径：planner / workflow 拆分与兼容别名。"""

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


async def _user(prefix: str = "cv") -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"{prefix}-{suffix}", name="cv-org", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"{prefix}-{suffix}",
            display_name="cv",
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


async def _login(client: AsyncClient, user: User) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": "pw-ok"},
    )
    assert login.status_code == 200
    return _auth(login.json()["access_token"])


async def _create_profile(client: AsyncClient, headers: dict[str, str]) -> str:
    suffix = uuid4().hex[:8]
    llm = await client.post(
        "/api/v1/models/llms",
        headers=headers,
        json={"code": f"cv-llm-{suffix}", "provider": "local", "model_name": "m"},
    )
    assert llm.status_code == 200
    profile = await client.post(
        "/api/v1/agent-config/profiles",
        headers=headers,
        json={
            "code": f"cv-pf-{suffix}",
            "name": "p",
            "system_prompt": "s",
            "default_llm_id": llm.json()["id"],
            "skill_ids": [],
        },
    )
    assert profile.status_code == 200
    return str(profile.json()["id"])


@pytest.fixture
async def api_client() -> AsyncIterator[tuple[AsyncClient, FakeWorkflowRuntime]]:
    fake = FakeWorkflowRuntime()
    set_workflow_runtime_override(fake)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake
    set_workflow_runtime_override(None)


@pytest.mark.asyncio
async def test_planner_requires_jwt() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/api/v1/conversations/planner")
    assert denied.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_planner_and_workflow_paths(
    api_client: tuple[AsyncClient, FakeWorkflowRuntime],
) -> None:
    client, fake = api_client
    user = await _user()
    headers = await _login(client, user)
    profile_id = await _create_profile(client, headers)
    flow_id = uuid4()

    planner = await client.post(
        "/api/v1/conversations/planner",
        headers=headers,
        json={"title": "plan", "profile_id": profile_id},
    )
    assert planner.status_code == 200
    planner_body = planner.json()
    pid = planner_body["id"]
    assert planner_body["app_key"] == "planner"
    assert planner_body["metadata"]["profile_id"] == profile_id
    assert planner_body["flow_id"] is None

    listed_p = await client.get("/api/v1/conversations/planner", headers=headers)
    assert listed_p.status_code == 200
    items = listed_p.json()
    assert len(items) == 1
    assert items[0]["id"] == pid
    assert "metadata" not in items[0]
    assert "profile_id" not in items[0]

    detail = await client.get(f"/api/v1/conversations/planner/{pid}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["metadata"]["profile_id"] == profile_id

    wf = await client.post(
        "/api/v1/conversations/workflow",
        headers=headers,
        json={"title": "wf", "flow_id": str(flow_id)},
    )
    assert wf.status_code == 200
    wid = wf.json()["id"]
    assert wf.json()["app_key"] == "workflow"

    listed_w = await client.get("/api/v1/conversations/workflow", headers=headers)
    assert {row["id"] for row in listed_w.json()} == {wid}
    listed_legacy = await client.get("/api/v1/conversations", headers=headers)
    assert {row["id"] for row in listed_legacy.json()} == {wid}

    cross = await client.get(f"/api/v1/conversations/planner/{wid}", headers=headers)
    assert cross.status_code == 404
    cross2 = await client.get(f"/api/v1/conversations/workflow/{pid}", headers=headers)
    assert cross2.status_code == 404
    cross3 = await client.get(f"/api/v1/conversations/{pid}", headers=headers)
    assert cross3.status_code == 404

    sent_wf = await client.post(
        "/api/v1/conversations/workflow/messages",
        headers=headers,
        json={"conversation_id": wid, "flow_id": str(flow_id), "content": "你好"},
    )
    assert sent_wf.status_code == 200
    assert sent_wf.json()["run_id"]
    assert len(fake.requests) == 1

    before = len(fake.requests)
    sent_p = await client.post(
        "/api/v1/conversations/planner/messages",
        headers=headers,
        json={"conversation_id": pid, "content": "规划一下"},
    )
    assert sent_p.status_code == 200
    assert sent_p.json()["run_id"]
    assert len(fake.requests) == before + 1
    planner_req = fake.requests[-1]
    assert planner_req.kind == "planner"
    assert str(planner_req.profile_id) == profile_id

    msgs = await client.get(f"/api/v1/conversations/planner/{pid}/messages", headers=headers)
    assert msgs.status_code == 200
    roles = {item["role"] for item in msgs.json()}
    assert roles == {"user", "assistant"}

    deleted = await client.delete(f"/api/v1/conversations/planner/{pid}", headers=headers)
    assert deleted.status_code == 200
    listed_after = await client.get("/api/v1/conversations/planner", headers=headers)
    assert listed_after.json() == []
    gone = await client.get(f"/api/v1/conversations/planner/{pid}", headers=headers)
    assert gone.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_planner_forbidden_other_user(
    api_client: tuple[AsyncClient, FakeWorkflowRuntime],
) -> None:
    client, _fake = api_client
    owner = await _user("own")
    other = await _user("oth")
    owner_h = await _login(client, owner)
    other_h = await _login(client, other)
    profile_id = await _create_profile(client, owner_h)
    created = await client.post(
        "/api/v1/conversations/planner",
        headers=owner_h,
        json={"profile_id": profile_id},
    )
    cid = created.json()["id"]
    denied = await client.get(f"/api/v1/conversations/planner/{cid}", headers=other_h)
    assert denied.status_code == 403
    assert denied.json()["code"] == "conversation_forbidden"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_profile_after_soft_deleted_planner_conversation(
    api_client: tuple[AsyncClient, FakeWorkflowRuntime],
) -> None:
    client, _fake = api_client
    user = await _user("dp")
    headers = await _login(client, user)
    profile_id = await _create_profile(client, headers)
    created = await client.post(
        "/api/v1/conversations/planner",
        headers=headers,
        json={"title": "keep", "profile_id": profile_id},
    )
    assert created.status_code == 200
    cid = created.json()["id"]

    blocked = await client.delete(f"/api/v1/agent-config/profiles/{profile_id}", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "profile_in_use"

    removed = await client.delete(f"/api/v1/conversations/planner/{cid}", headers=headers)
    assert removed.status_code == 200
    deleted = await client.delete(f"/api/v1/agent-config/profiles/{profile_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
