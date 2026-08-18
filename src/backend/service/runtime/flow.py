"""FlowRuntime：从定义文档编译 LangGraph 图。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import TypedDict
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from loguru import logger

from service.runtime.constants import (
    END_ALIASES,
    NODE_INTERRUPT,
    NODE_LLM,
    NODE_PASSTHROUGH,
)
from service.runtime.llm import ChatCompletionClient, ChatMessage, get_chat_client
from service.runtime.schemas import FlowDefinitionDocument, RunStatePayload


class GraphState(TypedDict):
    messages: list[dict[str, object]]
    variables: dict[str, object]
    metadata: dict[str, object]


NodeFn = Callable[[GraphState], object]


def _as_chat_messages(state: GraphState) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for item in state.get("messages") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        messages.append({"role": role, "content": content})
    if messages:
        return messages
    variables = state.get("variables") or {}
    user_input = str(variables.get("input") or variables.get("user_input") or "")
    if user_input:
        return [{"role": "user", "content": user_input}]
    return [{"role": "user", "content": ""}]


def _passthrough_node(state: GraphState) -> dict[str, object]:
    return {}


def _make_interrupt_node(prompt: str) -> NodeFn:
    def _node(state: GraphState) -> dict[str, object]:
        decision = interrupt({"prompt": prompt, "variables": state.get("variables") or {}})
        variables = dict(state.get("variables") or {})
        variables["hitl_resume"] = decision
        return {"variables": variables}

    return _node


def _make_llm_node(client: ChatCompletionClient, extra_system: str | None) -> NodeFn:
    async def _node(state: GraphState) -> dict[str, object]:
        messages = _as_chat_messages(state)
        if extra_system:
            messages = [{"role": "system", "content": extra_system}, *messages]
        content = await client.complete(messages)
        new_messages: list[dict[str, object]] = [
            *list(state.get("messages") or []),
            {"role": "assistant", "content": content},
        ]
        if not state.get("messages"):
            new_messages = [
                *messages,
                {"role": "assistant", "content": content},
            ]
        variables = dict(state.get("variables") or {})
        variables["last_output"] = content
        return {"messages": new_messages, "variables": variables}

    return _node


def _node_kind(spec: dict[str, object]) -> str:
    return str(spec.get("kind") or NODE_PASSTHROUGH)


def _node_id(spec: dict[str, object]) -> str:
    return str(spec["id"])


def _node_prompt(spec: dict[str, object]) -> str:
    raw = spec.get("prompt")
    if isinstance(raw, str) and raw:
        return raw
    return "需要人工确认"


class FlowRuntime:
    """已编译图 / LangGraph 图实例。"""

    def __init__(
        self,
        flow_id: UUID,
        graph: object,
        checkpointer: BaseCheckpointSaver,
    ) -> None:
        self.flow_id = flow_id
        self.graph = graph
        self.checkpointer = checkpointer

    @classmethod
    def compile(
        cls,
        document: FlowDefinitionDocument,
        *,
        flow_id: UUID,
        checkpointer: BaseCheckpointSaver,
        chat_client: ChatCompletionClient | None = None,
    ) -> FlowRuntime:
        client = chat_client or get_chat_client()
        builder: StateGraph[GraphState] = StateGraph(GraphState)
        node_ids: list[str] = []
        for spec in document.nodes:
            nid = _node_id(spec)
            kind = _node_kind(spec)
            if kind == NODE_INTERRUPT:
                builder.add_node(nid, _make_interrupt_node(_node_prompt(spec)))
            elif kind == NODE_LLM:
                extra = spec.get("prompt")
                extra_s = extra if isinstance(extra, str) else None
                builder.add_node(nid, _make_llm_node(client, extra_s))
            else:
                if kind != NODE_PASSTHROUGH:
                    logger.warning("未知节点 kind={}，按 passthrough 处理", kind)
                builder.add_node(nid, _passthrough_node)
            node_ids.append(nid)

        if document.entry_point not in node_ids:
            raise ValueError(f"entry_point 不存在: {document.entry_point}")
        builder.add_edge(START, document.entry_point)

        for edge in document.edges:
            source = str(edge["source"])
            target = str(edge["target"])
            if target in END_ALIASES:
                builder.add_edge(source, END)
            else:
                builder.add_edge(source, target)

        compiled = builder.compile(
            checkpointer=checkpointer,
            interrupt_before=list(document.interrupt_before),
        )
        logger.info(
            "编译 FlowRuntime flow_id={} nodes={} interrupt_before={}",
            flow_id,
            node_ids,
            document.interrupt_before,
        )
        return cls(flow_id=flow_id, graph=compiled, checkpointer=checkpointer)

    def invoke(self, payload: RunStatePayload, *, thread_id: str) -> dict[str, object]:
        config = {"configurable": {"thread_id": thread_id}}
        result = self.graph.invoke(payload.to_graph_state(), config)  # type: ignore[union-attr]
        return dict(result)

    async def astream_events(
        self,
        payload: RunStatePayload,
        *,
        thread_id: str,
    ) -> AsyncIterator[dict[str, object]]:
        config = {"configurable": {"thread_id": thread_id}}
        async for event in self.graph.astream(payload.to_graph_state(), config):  # type: ignore[union-attr]
            yield dict(event)
