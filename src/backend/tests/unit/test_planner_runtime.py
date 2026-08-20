"""自研规划循环：Fake LLM 调工具后结束。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.runtime.context import (  # noqa: E402
    GraphExecContext,
    attach_graph_exec_ctx,
    reset_graph_exec_ctx,
)
from service.runtime.llm import (  # noqa: E402
    ChatTurn,
    FakeChatCompletionClient,
    ToolCallSpec,
    ToolSpec,
)
from service.runtime.planner import PlannerRuntime  # noqa: E402
from service.tools.schemas import ToolCallRequest, ToolCallResult  # noqa: E402


@pytest.mark.asyncio
async def test_planner_loop_tool_then_stop() -> None:
    async def _exec(request: ToolCallRequest) -> ToolCallResult:
        return ToolCallResult(
            tool_call_id=request.tool_call_id,
            success=True,
            output={"echo": request.arguments},
        )

    token = attach_graph_exec_ctx(GraphExecContext(tool_execute=_exec))
    fake = FakeChatCompletionClient(
        turns=[
            ChatTurn(
                content="",
                tool_calls=[
                    ToolCallSpec(id="c1", tool_code="echo", arguments={"q": "hi"}),
                ],
            ),
            ChatTurn(content="已经完成"),
        ]
    )
    try:
        runtime = PlannerRuntime.compile(
            system_prompt="你是规划助手",
            tools=[
                ToolSpec(
                    code="echo",
                    name="echo",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            chat_client=fake,
            checkpointer=InMemorySaver(),
            max_steps=8,
            profile_id=uuid4(),
        )
        result = await runtime.graph.ainvoke(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "variables": {"input": "hi"},
                "metadata": {},
            },
            {"configurable": {"thread_id": "planner-t1"}},
        )
        assert result["variables"]["last_output"] == "已经完成"
        assert len(fake.turn_calls) == 2
        roles = [str(m.get("role")) for m in result["messages"] if isinstance(m, dict)]
        assert "tool" in roles
    finally:
        reset_graph_exec_ctx(token)


def test_no_deepagents_dependency() -> None:
    import importlib.util

    assert importlib.util.find_spec("deepagents") is None
    assert importlib.util.find_spec("langchain_deepagents") is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_planner_writes_assistant_message() -> None:
    from data_schema.agent.models import AgentLlm, AgentProfile
    from data_schema.conversation.models import Conversation, Message
    from data_schema.permission.models import Organization, User
    from service.database.session import session_scope
    from service.orchestration.passthrough import PassthroughOrchestrator
    from service.persistence.factory import get_repositories
    from service.runtime.checkpointer import (
        new_memory_checkpointer,
        set_checkpointer_override,
    )
    from service.runtime.llm import set_chat_client_override
    from service.runtime.schemas import RunStatePayload, StartRunRequest

    set_checkpointer_override(new_memory_checkpointer())
    set_chat_client_override(FakeChatCompletionClient("规划完成"))
    try:
        suffix = uuid4().hex[:8]
        async with session_scope() as session:
            org = Organization(code=f"pl-{suffix}", name="pl", status="active")
            session.add(org)
            await session.flush()
            user = User(
                username=f"pl-{suffix}",
                display_name="pl",
                organization_id=org.id,
                status="active",
            )
            session.add(user)
            await session.flush()
            llm = AgentLlm(
                code=f"pl-llm-{suffix}",
                provider="local",
                model_name="demo",
                config={},
                is_active=True,
            )
            session.add(llm)
            await session.flush()
            profile = AgentProfile(
                code=f"pl-pf-{suffix}",
                name="p",
                system_prompt="sys",
                default_llm_id=llm.id,
                skill_ids=[],
                owner_organization_id=org.id,
            )
            session.add(profile)
            await session.flush()
            conv = Conversation(
                user_id=user.id,
                title="t",
                app_key="planner",
                status="active",
                metadata_={"profile_id": str(profile.id)},
            )
            session.add(conv)
            await session.flush()
            assistant = Message(
                conversation_id=conv.id,
                role="assistant",
                content_blocks=[],
                status="streaming",
            )
            session.add(assistant)
            await session.flush()
            user_id = user.id
            profile_id = profile.id
            conv_id = conv.id
            assistant_id = assistant.id

        orch = PassthroughOrchestrator()
        run_id = await orch.start_run(
            StartRunRequest(
                user_id=user_id,
                flow_id=profile_id,
                conversation_id=conv_id,
                kind="planner",
                profile_id=profile_id,
                input_payload=RunStatePayload(
                    messages=[{"role": "user", "content": "hi"}],
                    variables={"input": "hi"},
                    metadata={"assistant_message_id": str(assistant_id)},
                ),
            )
        )
        async with session_scope() as session:
            repos = get_repositories(session)
            run = await repos.workflow.run.get(run_id)
            assert run is not None
            assert run.status == "completed"
            msg = await repos.conversation.message.get(assistant_id)
            assert msg is not None
            assert msg.status == "completed"
            assert msg.content_blocks[0]["text"] == "规划完成"
    finally:
        set_chat_client_override(None)
        set_checkpointer_override(None)
