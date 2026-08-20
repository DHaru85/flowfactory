"""FlowRuntime：从定义文档编译 LangGraph 图。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import TypedDict
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from loguru import logger

from service.guardrail.instrument import wrap_guardrail_node
from service.observability.instrument import wrap_graph_node
from service.runtime.constants import (
    END_ALIASES,
    NODE_INTERRUPT,
    NODE_LLM,
    NODE_PASSTHROUGH,
)
from service.runtime.definition_v1 import FlowDefinitionV1, parse_flow_definition
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
        parts: list[str] = []
        reasoning_parts: list[str] = []
        async for part in client.stream_parts(messages):
            if part.kind == "reasoning":
                reasoning_parts.append(part.text)
                await _publish_reasoning(part.text)
            else:
                parts.append(part.text)
                await _publish_speaking(part.text)
        content = "".join(parts)
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
        variables["last_reasoning"] = "".join(reasoning_parts)
        return {"messages": new_messages, "variables": variables}

    return _node


async def _publish_speaking(delta: str) -> None:
    """面向用户的流式增量；不经护栏；失败不影响图执行。"""
    await _publish_stream_delta("speaking", delta)


async def _publish_reasoning(delta: str) -> None:
    """思考增量；不经护栏；失败不影响图执行。"""
    await _publish_stream_delta("reasoning", delta)


async def _publish_stream_delta(kind: str, delta: str) -> None:
    from service.events.context import get_stream_ctx
    from service.events.factory import get_stream_bus
    from service.events.schemas import reasoning_event, speaking_event

    ctx = get_stream_ctx()
    if ctx is None or ctx.conversation_id is None or ctx.message_id is None:
        return
    if not delta:
        return
    event = (
        reasoning_event(delta=delta, message_id=ctx.message_id)
        if kind == "reasoning"
        else speaking_event(delta=delta, message_id=ctx.message_id)
    )
    try:
        await get_stream_bus().publish(ctx.conversation_id, event)
    except Exception:
        logger.warning("{} 投递失败 run_id={}", kind, ctx.run_id)
    if kind != "speaking":
        return
    try:
        from service.cache.client import get_redis_client
        from service.cache.stores import ConversationCacheStore

        ConversationCacheStore(get_redis_client()).append_stream_delta(ctx.message_id, delta)
    except Exception:
        logger.debug("流式 Redis 缓冲写入跳过")


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
        document: FlowDefinitionDocument | FlowDefinitionV1 | dict[str, object],
        *,
        flow_id: UUID,
        checkpointer: BaseCheckpointSaver,
        chat_client: ChatCompletionClient | None = None,
    ) -> FlowRuntime:
        parsed = parse_compile_document(document)
        if isinstance(parsed, FlowDefinitionV1):
            from service.runtime.compile_v1 import compile_v1_builder

            client = chat_client or get_chat_client()
            builder, _start_id, node_ids = compile_v1_builder(
                parsed, chat_client=client
            )
            compiled = builder.compile(checkpointer=checkpointer, interrupt_before=[])
            logger.info(
                "编译 FlowRuntime v1 flow_id={} nodes={}",
                flow_id,
                node_ids,
            )
            return cls(flow_id=flow_id, graph=compiled, checkpointer=checkpointer)
        return cls._compile_v0(
            parsed,
            flow_id=flow_id,
            checkpointer=checkpointer,
            chat_client=chat_client,
        )

    @classmethod
    def _compile_v0(
        cls,
        document: FlowDefinitionDocument,
        *,
        flow_id: UUID,
        checkpointer: BaseCheckpointSaver,
        chat_client: ChatCompletionClient | None,
    ) -> FlowRuntime:
        client = chat_client or get_chat_client()
        builder: StateGraph[GraphState] = StateGraph(GraphState)
        node_ids: list[str] = []
        for spec in document.nodes:
            nid = _node_id(spec)
            kind = _node_kind(spec)
            if kind == NODE_INTERRUPT:
                inner: NodeFn = _make_interrupt_node(_node_prompt(spec))
            elif kind == NODE_LLM:
                extra = spec.get("prompt")
                extra_s = extra if isinstance(extra, str) else None
                inner = _make_llm_node(client, extra_s)
            else:
                if kind != NODE_PASSTHROUGH:
                    logger.warning("未知节点 kind={}，按 passthrough 处理", kind)
                inner = _passthrough_node
            guarded = wrap_guardrail_node(
                nid, kind, inner, is_entry=nid == document.entry_point
            )
            builder.add_node(nid, wrap_graph_node(nid, kind, guarded))
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


def parse_compile_document(
    document: FlowDefinitionDocument | FlowDefinitionV1 | dict[str, object],
) -> FlowDefinitionDocument | FlowDefinitionV1:
    if isinstance(document, FlowDefinitionV1):
        return document
    if isinstance(document, FlowDefinitionDocument):
        return document
    if document.get("schema_version") == 1:
        return parse_flow_definition(document)
    nodes = document.get("nodes")
    first = nodes[0] if isinstance(nodes, list) and nodes else None
    if (
        "state" in document
        and isinstance(first, dict)
        and "type" in first
        and "kind" not in first
    ):
        return parse_flow_definition(document)
    return FlowDefinitionDocument.model_validate(document)
