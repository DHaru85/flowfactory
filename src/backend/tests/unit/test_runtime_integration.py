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


async def _published_flows(*, child_hitl: bool = False) -> tuple[User, object, object]:
    from data_schema.agent.models import AgentFlow
    from service.runtime.definition_v1 import empty_flow_definition

    suffix = uuid4().hex[:8]
    if child_hitl:
        child_def = {
            "schema_version": 1,
            "state": empty_flow_definition().state.model_dump(mode="json"),
            "nodes": [
                {"id": "start", "type": "start", "data": {"inject": []}},
                {
                    "id": "ask",
                    "type": "hitl",
                    "data": {"prompt_template": "wait", "on_reject": "fail"},
                },
                {"id": "end", "type": "end", "data": {"output_channels": []}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "ask"},
                {"id": "e2", "source": "ask", "target": "end"},
            ],
            "branches": [],
        }
    else:
        child_def = empty_flow_definition().model_dump(mode="json")
    parent_def = {
        "schema_version": 1,
        "state": child_def["state"],
        "nodes": [
            {"id": "start", "type": "start", "data": {"inject": []}},
            {
                "id": "sub",
                "type": "subgraph",
                "data": {
                    "flow_code": f"child-{suffix}",
                    "input_map": [],
                    "output_map": [],
                    "timeout_seconds": 60,
                },
            },
            {"id": "end", "type": "end", "data": {"output_channels": []}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "sub"},
            {"id": "e2", "source": "sub", "target": "end"},
        ],
        "branches": [],
    }
    async with session_scope() as session:
        org = Organization(code=f"sg-{suffix}", name="sg", status="active")
        session.add(org)
        await session.flush()
        user = User(
            username=f"sg-user-{suffix}",
            display_name="sg",
            organization_id=org.id,
            status="active",
        )
        session.add(user)
        child = AgentFlow(
            code=f"child-{suffix}",
            name="child",
            version=1,
            definition=child_def,
            status="published",
        )
        session.add(child)
        parent = AgentFlow(
            code=f"parent-{suffix}",
            name="parent",
            version=1,
            definition=parent_def,
            status="published",
        )
        session.add(parent)
        await session.flush()
        session.expunge(user)
        session.expunge(child)
        session.expunge(parent)
        return user, parent, child


@pytest.mark.integration
@pytest.mark.asyncio
async def test_v1_subgraph_waiting_child_then_resume() -> None:
    set_checkpointer_override(new_memory_checkpointer())
    set_chat_client_override(FakeChatCompletionClient("unused"))
    try:
        user, parent, _child = await _published_flows()
        orch = PassthroughOrchestrator()
        run_id = await orch.start_run(
            StartRunRequest(
                user_id=user.id,
                flow_id=parent.id,
                input_payload=RunStatePayload(),
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
            bucket = variables.get("__subgraph__")
            assert isinstance(bucket, dict)
            assert bucket["sub"]["status"] == "completed"
    finally:
        set_chat_client_override(None)
        set_checkpointer_override(None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_parent_does_not_resume() -> None:
    from datetime import UTC, datetime, timedelta

    from data_schema.workflow.models import ChildRunPending
    from service.runtime.constants import CHILD_PENDING, RUN_WAITING_CHILD
    from service.runtime.scheduler import cancel_run

    user = await _ensure_user()
    async with session_scope() as session:
        repos = get_repositories(session)
        from data_schema.workflow.models import RunSnapshot, ThreadSnapshot

        thread = ThreadSnapshot(queue_name="wf.run", priority=0, context_payload={})
        await repos.workflow.thread.add(thread)
        parent = RunSnapshot(
            flow_id=uuid4(),
            user_id=user.id,
            status=RUN_WAITING_CHILD,
            input_payload={},
            thread_id=thread.id,
            langgraph_thread_id="p",
        )
        await repos.workflow.run.add(parent)
        child_thread = ThreadSnapshot(queue_name="wf.run", priority=0, context_payload={})
        await repos.workflow.thread.add(child_thread)
        child = RunSnapshot(
            flow_id=uuid4(),
            user_id=user.id,
            status="running",
            input_payload={},
            thread_id=child_thread.id,
            langgraph_thread_id="c",
        )
        await repos.workflow.run.add(child)
        pending = ChildRunPending(
            parent_run_id=parent.id,
            child_run_id=child.id,
            node_id="sub",
            status=CHILD_PENDING,
            timeout_at=datetime.now(UTC) + timedelta(hours=1),
        )
        await repos.workflow.child_pending.add(pending)
        parent_id = parent.id
        child_id = child.id
        pending_id = pending.id
    await cancel_run(parent_id, notify_parent=False, cascade=True)
    async with session_scope() as session:
        repos = get_repositories(session)
        parent = await repos.workflow.run.get(parent_id)
        child = await repos.workflow.run.get(child_id)
        pending = await repos.workflow.child_pending.get(pending_id)
        assert parent is not None and parent.status == "cancelled"
        assert child is not None and child.status == "cancelled"
        assert pending is not None and pending.status == "parent_cancelled"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_timeout_resumes_parent() -> None:
    from datetime import UTC, datetime, timedelta

    from service.runtime.scheduler import expire_due_child_pending

    set_checkpointer_override(new_memory_checkpointer())
    set_chat_client_override(FakeChatCompletionClient("unused"))
    try:
        user, parent, _child = await _published_flows(child_hitl=True)
        orch = PassthroughOrchestrator()
        run_id = await orch.start_run(
            StartRunRequest(
                user_id=user.id,
                flow_id=parent.id,
                input_payload=RunStatePayload(),
            )
        )
        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_id)
            assert run is not None
            assert run.status == "waiting_child"
            children = await repos.workflow.list_pending_children(run_id)
            assert len(children) == 1
            children[0].timeout_at = datetime.now(UTC) - timedelta(seconds=1)
        count = await expire_due_child_pending()
        assert count == 1
        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_id)
            assert run is not None
            assert run.status == "completed"
            variables = (run.output_payload or {}).get("variables")
            assert isinstance(variables, dict)
            assert variables["__subgraph__"]["sub"]["status"] == "timeout"
    finally:
        set_chat_client_override(None)
        set_checkpointer_override(None)

