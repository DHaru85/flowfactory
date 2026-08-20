"""HITL 待办列表与恢复 HTTP。"""

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
from data_schema.conversation.models import Conversation  # noqa: E402
from data_schema.permission.models import Organization, User  # noqa: E402
from data_schema.workflow.models import HitlPending, RunSnapshot  # noqa: E402
from service.auth.password import hash_password  # noqa: E402
from service.database.session import session_scope  # noqa: E402


async def _make_user(*, superuser: bool) -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"ht-{suffix}", name="ht", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"ht-{suffix}",
            display_name="ht",
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


async def _seed_pending(owner: User) -> tuple[str, str]:
    async with session_scope() as session:
        conv = Conversation(
            user_id=owner.id,
            title="hitl-conv",
            app_key="workflow",
            flow_id=uuid4(),
            status="active",
            metadata_={},
        )
        session.add(conv)
        await session.flush()
        run = RunSnapshot(
            flow_id=uuid4(),
            conversation_id=conv.id,
            user_id=owner.id,
            status="interrupted",
            input_payload={},
            thread_id=uuid4(),
            langgraph_thread_id=str(uuid4()),
        )
        session.add(run)
        await session.flush()
        pending = HitlPending(
            run_id=run.id,
            node_id="hitl-1",
            prompt="请审批",
            resume_payload={"on_reject": "fail", "form_schema": {"type": "object"}},
            status="pending",
        )
        session.add(pending)
        await session.flush()
        return str(pending.id), str(run.id)


@pytest.fixture
async def api_bundle() -> AsyncIterator[tuple[AsyncClient, FakeWorkflowRuntime]]:
    fake = FakeWorkflowRuntime()
    set_workflow_runtime_override(fake)
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, fake
    set_workflow_runtime_override(None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hitl_list_resume_and_forbidden(
    api_bundle: tuple[AsyncClient, FakeWorkflowRuntime],
) -> None:
    api_client, fake = api_bundle
    admin = await _make_user(superuser=True)
    owner = await _make_user(superuser=False)
    other = await _make_user(superuser=False)
    admin_h = await _login(api_client, admin)
    owner_h = await _login(api_client, owner)
    other_h = await _login(api_client, other)

    bound = await api_client.put(
        "/api/v1/auth/apps/conversation/bindings",
        headers=admin_h,
        json={
            "bindings": [
                {
                    "subject_type": "organization",
                    "subject_id": str(owner.organization_id),
                    "actions": ["read", "use"],
                },
                {
                    "subject_type": "organization",
                    "subject_id": str(other.organization_id),
                    "actions": ["read", "use"],
                },
            ]
        },
    )
    assert bound.status_code == 200

    hitl_id, run_id = await _seed_pending(owner)

    listed = await api_client.get(
        "/api/v1/conversations/workflow/hitl-pendings",
        headers=owner_h,
        params={"run_id": run_id},
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == hitl_id
    assert listed.json()[0]["form_schema"] == {"type": "object"}

    other_list = await api_client.get(
        "/api/v1/conversations/workflow/hitl-pendings",
        headers=other_h,
    )
    assert other_list.status_code == 200
    assert other_list.json() == []

    hidden = await api_client.get(
        f"/api/v1/conversations/workflow/hitl-pendings/{hitl_id}",
        headers=other_h,
    )
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "hitl_not_found"

    denied_resume = await api_client.post(
        f"/api/v1/conversations/workflow/hitl-pendings/{hitl_id}/resume",
        headers=other_h,
        json={"decision": "approve"},
    )
    assert denied_resume.status_code == 404

    ok = await api_client.post(
        f"/api/v1/conversations/workflow/hitl-pendings/{hitl_id}/resume",
        headers=owner_h,
        json={"decision": "approve", "user_input": "同意"},
    )
    assert ok.status_code == 200
    assert ok.json()["resumed"] is True
    assert len(fake.resumes) == 1
    assert fake.resumes[0].user_input == "同意"
