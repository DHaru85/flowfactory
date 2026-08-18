"""工作流调度集成测试：真实 PG + eager Celery + 内存 checkpointer + Fake LLM。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from data_schema.permission.models import Organization, User  # noqa: E402
from service.database.session import session_scope  # noqa: E402
from service.orchestration.passthrough import PassthroughOrchestrator  # noqa: E402
from service.persistence.factory import get_repositories  # noqa: E402
from service.runtime.checkpointer import (  # noqa: E402
    get_postgres_checkpointer,
    new_memory_checkpointer,
    reset_checkpointer,
    set_checkpointer_override,
)
from service.runtime.llm import FakeChatCompletionClient, set_chat_client_override  # noqa: E402
from service.runtime.schemas import (  # noqa: E402
    FlowDefinitionDocument,
    HitlResumeInput,
    RunStatePayload,
    StartRunRequest,
)


def _llm_doc() -> FlowDefinitionDocument:
    return FlowDefinitionDocument(
        nodes=[{"id": "chat", "kind": "llm"}],
        edges=[{"source": "chat", "target": "END"}],
        entry_point="chat",
    )


def _hitl_doc() -> FlowDefinitionDocument:
    return FlowDefinitionDocument(
        nodes=[
            {"id": "prep", "kind": "passthrough"},
            {"id": "ask", "kind": "interrupt", "prompt": "是否继续?"},
        ],
        edges=[
            {"source": "prep", "target": "ask"},
            {"source": "ask", "target": "END"},
        ],
        entry_point="prep",
    )


async def _ensure_user() -> User:
    suffix = uuid4().hex[:8]
    async with session_scope() as session:
        org = Organization(code=f"wf-{suffix}", name="runtime-test", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"wf-user-{suffix}",
            display_name="runtime",
            organization_id=org.id,
            status="active",
        )
        session.add(user)
        await session.flush()
        session.expunge(user)
        return user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_run_llm_completes() -> None:
    set_checkpointer_override(new_memory_checkpointer())
    set_chat_client_override(FakeChatCompletionClient("完成"))
    try:
        user = await _ensure_user()
        orch = PassthroughOrchestrator()
        run_id = await orch.start_run(
            StartRunRequest(
                user_id=user.id,
                flow_id=uuid4(),
                input_payload=RunStatePayload(variables={"input": "ping"}),
                definition=_llm_doc(),
            )
        )
        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_id)
            assert run is not None
            assert run.status == "completed"
            assert run.output_payload is not None
            variables = run.output_payload.get("variables")
            assert isinstance(variables, dict)
            assert variables.get("last_output") == "完成"
    finally:
        set_chat_client_override(None)
        set_checkpointer_override(None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hitl_interrupt_then_resume() -> None:
    set_checkpointer_override(new_memory_checkpointer())
    set_chat_client_override(FakeChatCompletionClient("unused"))
    try:
        user = await _ensure_user()
        orch = PassthroughOrchestrator()
        run_id = await orch.start_run(
            StartRunRequest(
                user_id=user.id,
                flow_id=uuid4(),
                input_payload=RunStatePayload(variables={"input": "need-hitl"}),
                definition=_hitl_doc(),
            )
        )
        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_id)
            assert run is not None
            assert run.status == "interrupted"
            pending_list = await repos.workflow.list_pending_hitl(user.id)
            pending = next(p for p in pending_list if p.run_id == run_id)
            hitl_id = pending.id

        output = await orch.resume_run(
            HitlResumeInput(hitl_id=hitl_id, decision="approve", user_input="ok")
        )
        assert output.resumed is True
        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_id)
            assert run is not None
            assert run.status == "completed"
    finally:
        set_chat_client_override(None)
        set_checkpointer_override(None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_checkpointer_setup_and_roundtrip() -> None:
    set_checkpointer_override(None)
    await reset_checkpointer()
    try:
        saver = await get_postgres_checkpointer()
        from service.runtime.flow import FlowRuntime

        runtime = FlowRuntime.compile(
            FlowDefinitionDocument(
                nodes=[{"id": "a", "kind": "passthrough"}],
                edges=[{"source": "a", "target": "END"}],
                entry_point="a",
            ),
            flow_id=uuid4(),
            checkpointer=saver,
        )
        thread_id = f"ckpt-{uuid4()}"
        await runtime.graph.ainvoke(
            RunStatePayload(variables={"k": "v"}).to_graph_state(),
            {"configurable": {"thread_id": thread_id}},
        )
        snap = await runtime.graph.aget_state({"configurable": {"thread_id": thread_id}})
        assert snap.values["variables"]["k"] == "v"
    finally:
        await reset_checkpointer()

