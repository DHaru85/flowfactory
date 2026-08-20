"""自研规划循环：Profile 装配固定图，模型自选工具。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import UUID, uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from service.events.context import get_stream_ctx
from service.events.factory import get_stream_bus
from service.events.schemas import step_running_event, tool_calling_event
from service.guardrail.instrument import wrap_guardrail_node
from service.observability.instrument import wrap_graph_node
from service.runtime.constants import NODE_LLM
from service.runtime.context import get_graph_exec_ctx
from service.runtime.flow import GraphState, _publish_reasoning, _publish_speaking
from service.runtime.llm import (
    ChatCompletionClient,
    ChatMessage,
    ChatTurn,
    ChatTurnMessage,
    ToolCallSpec,
    ToolSpec,
)
from service.tools.schemas import ToolCallRequest, ToolCallResult

PENDING_KEY = "pending_tool_calls"
STEP_KEY = "planner_step"


def _system_prompt(profile_prompt: str, skill_extra: str) -> str:
    parts = [profile_prompt.strip()]
    if skill_extra.strip():
        parts.append(skill_extra.strip())
    return "\n\n".join(part for part in parts if part)


def _llm_messages(state: GraphState, system: str) -> list[ChatTurnMessage]:
    out: list[ChatTurnMessage] = []
    if system:
        out.append({"role": "system", "content": system})
    for item in state.get("messages") or []:
        if not isinstance(item, dict):
            continue
        out.append(dict(item))
    if len(out) == 1 and out[0].get("role") == "system":
        variables = state.get("variables") or {}
        user_input = str(variables.get("input") or variables.get("user_input") or "")
        if user_input:
            out.append({"role": "user", "content": user_input})
    return out


async def _publish_tool_calling(
    *,
    tool_call_id: str,
    tool_name: str,
    arguments: dict[str, object],
    status: str,
    result: object | None = None,
) -> None:
    ctx = get_stream_ctx()
    if ctx is None or ctx.conversation_id is None:
        return
    try:
        await get_stream_bus().publish(
            ctx.conversation_id,
            tool_calling_event(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=arguments,
                status=status,
                result=result,
            ),
        )
    except Exception:
        logger.warning("tool_calling 投递失败 run_id={}", ctx.run_id)


async def _publish_step(node_id: str, step_name: str, status: str) -> None:
    ctx = get_stream_ctx()
    if ctx is None or ctx.conversation_id is None:
        return
    try:
        await get_stream_bus().publish(
            ctx.conversation_id,
            step_running_event(node_id=node_id, step_name=step_name, status=status),
        )
    except Exception:
        logger.warning("step_running 投递失败 run_id={}", ctx.run_id)


async def _execute_tool(request: ToolCallRequest) -> ToolCallResult:
    ctx = get_graph_exec_ctx()
    if ctx is not None and ctx.tool_execute is not None:
        return await ctx.tool_execute(request)
    from service.database.session import session_scope
    from service.tools.executor import ToolExecutor

    async with session_scope() as session:
        return await ToolExecutor(session).execute(request)


def _assistant_tool_message(content: str, calls: Sequence[ToolCallSpec]) -> dict[str, object]:
    payload: dict[str, object] = {"role": "assistant", "content": content}
    payload["tool_calls"] = [
        {
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.tool_code,
                "arguments": json.dumps(call.arguments, ensure_ascii=False),
            },
        }
        for call in calls
    ]
    return payload


class PlannerRuntime:
    """已编译的规划循环图。"""

    def __init__(self, graph: object, checkpointer: BaseCheckpointSaver) -> None:
        self.graph = graph
        self.checkpointer = checkpointer

    @classmethod
    def compile(
        cls,
        *,
        system_prompt: str,
        tools: Sequence[ToolSpec],
        chat_client: ChatCompletionClient,
        checkpointer: BaseCheckpointSaver,
        max_steps: int,
        profile_id: UUID | None = None,
    ) -> PlannerRuntime:
        _ = profile_id
        specs = list(tools)
        system = system_prompt

        async def planner_node(state: GraphState) -> dict[str, object]:
            await _publish_step("planner", "规划", "started")
            variables = dict(state.get("variables") or {})
            step = int(variables.get(STEP_KEY) or 0) + 1
            variables[STEP_KEY] = step
            messages = list(state.get("messages") or [])
            if step > max_steps:
                text = "已达到规划最大步数，停止调用工具。"
                messages.append({"role": "assistant", "content": text})
                variables["last_output"] = text
                variables.pop(PENDING_KEY, None)
                await _publish_speaking(text)
                variables["last_reasoning"] = ""
                await _publish_step("planner", "规划", "completed")
                return {"messages": messages, "variables": variables}

            if not specs:
                parts: list[str] = []
                reasoning_parts: list[str] = []
                streamed: list[ChatMessage] = []
                for item in _llm_messages(state, system):
                    streamed.append(
                        {
                            "role": str(item.get("role") or "user"),
                            "content": str(item.get("content") or ""),
                        }
                    )
                async for part in chat_client.stream_parts(streamed):
                    if part.kind == "reasoning":
                        reasoning_parts.append(part.text)
                        await _publish_reasoning(part.text)
                    else:
                        parts.append(part.text)
                        await _publish_speaking(part.text)
                turn = ChatTurn(content="".join(parts), reasoning="".join(reasoning_parts))
            else:
                turn = await chat_client.complete_turn(_llm_messages(state, system), specs)
                if turn.reasoning:
                    await _publish_reasoning(turn.reasoning)
            if turn.tool_calls:
                for call in turn.tool_calls:
                    await _publish_tool_calling(
                        tool_call_id=call.id,
                        tool_name=call.tool_code,
                        arguments=call.arguments,
                        status="started",
                    )
                messages.append(_assistant_tool_message(turn.content, turn.tool_calls))
                variables[PENDING_KEY] = [c.model_dump(mode="json") for c in turn.tool_calls]
                await _publish_step("planner", "规划", "completed")
                return {"messages": messages, "variables": variables}

            content = turn.content
            if content and specs:
                await _publish_speaking(content)
            messages.append({"role": "assistant", "content": content})
            variables["last_output"] = content
            variables["last_reasoning"] = turn.reasoning
            variables.pop(PENDING_KEY, None)
            await _publish_step("planner", "规划", "completed")
            return {"messages": messages, "variables": variables}

        async def tools_node(state: GraphState) -> dict[str, object]:
            await _publish_step("tools", "工具", "started")
            variables = dict(state.get("variables") or {})
            raw_pending = variables.get(PENDING_KEY) or []
            messages = list(state.get("messages") or [])
            pending: list[ToolCallSpec] = []
            if isinstance(raw_pending, list):
                for item in raw_pending:
                    if isinstance(item, dict):
                        pending.append(ToolCallSpec.model_validate(item))
            for call in pending:
                request = ToolCallRequest(
                    tool_call_id=call.id or str(uuid4()),
                    tool_code=call.tool_code,
                    arguments=call.arguments,
                )
                result = await _execute_tool(request)
                status = "completed" if result.success else "failed"
                output = result.output if result.success else result.error
                await _publish_tool_calling(
                    tool_call_id=request.tool_call_id,
                    tool_name=call.tool_code,
                    arguments=call.arguments,
                    status=status,
                    result=output,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": request.tool_call_id,
                        "content": json.dumps(output, ensure_ascii=False, default=str),
                    }
                )
            variables.pop(PENDING_KEY, None)
            await _publish_step("tools", "工具", "completed")
            return {"messages": messages, "variables": variables}

        def route(state: GraphState) -> str:
            variables = state.get("variables") or {}
            pending = variables.get(PENDING_KEY)
            if isinstance(pending, list) and pending:
                return "tools"
            return "__end__"

        builder: StateGraph[GraphState] = StateGraph(GraphState)
        planner_fn = wrap_guardrail_node("planner", NODE_LLM, planner_node, is_entry=True)
        tools_fn = wrap_guardrail_node("tools", "tool", tools_node, is_entry=False)
        builder.add_node("planner", wrap_graph_node("planner", NODE_LLM, planner_fn))
        builder.add_node("tools", wrap_graph_node("tools", "tool", tools_fn))
        builder.add_edge(START, "planner")
        builder.add_conditional_edges(
            "planner",
            route,
            {"tools": "tools", "__end__": END},
        )
        builder.add_edge("tools", "planner")
        compiled = builder.compile(checkpointer=checkpointer, interrupt_before=[])
        logger.info("编译 PlannerRuntime tools={}", [spec.code for spec in specs])
        return cls(graph=compiled, checkpointer=checkpointer)

    @classmethod
    async def compile_for_profile(
        cls,
        session: AsyncSession,
        profile_id: UUID,
        checkpointer: BaseCheckpointSaver,
        chat_client: ChatCompletionClient | None = None,
    ) -> PlannerRuntime:
        from service.persistence.factory import get_repositories
        from service.runtime.llm import (
            get_chat_client,
            has_chat_client_override,
            resolve_llm_client,
        )
        from service.tools.skill import SkillRuntime
        from settings.config import get_settings

        repos = get_repositories(session)
        profile = await repos.agent.profile.get(profile_id)
        if profile is None:
            raise ValueError(f"Profile 不存在: {profile_id}")
        assembled = await SkillRuntime(session).assemble(profile.skill_ids)
        client = chat_client or get_chat_client()
        if chat_client is None and not has_chat_client_override():
            client = await resolve_llm_client(llm_id=profile.default_llm_id)
        return cls.compile(
            system_prompt=_system_prompt(profile.system_prompt, assembled.extra_system),
            tools=assembled.tool_specs(),
            chat_client=client,
            checkpointer=checkpointer,
            max_steps=get_settings().planner_max_steps,
            profile_id=profile.id,
        )
