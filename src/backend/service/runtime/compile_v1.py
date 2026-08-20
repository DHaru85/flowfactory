"""schema_version=1 编译为 StateGraph。"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from service.guardrail.instrument import wrap_guardrail_node
from service.observability.instrument import wrap_graph_node
from service.runtime.context import get_graph_exec_ctx
from service.runtime.definition_v1 import (
    END_REF,
    AssignNodeData,
    CustomNodeData,
    FlowBranch,
    FlowDefinitionV1,
    FlowNode,
    HitlNodeData,
    LlmNodeData,
    StartNodeData,
    SubgraphNodeData,
    ToolNodeData,
)
from service.runtime.expr import eval_expr, router_key
from service.runtime.flow import GraphState, NodeFn, _make_llm_node, _passthrough_node
from service.runtime.llm import ChatCompletionClient, get_chat_client, has_chat_client_override
from service.runtime.state_path import get_path, map_state, set_path
from service.tools.schemas import ToolCallRequest, ToolCallResult

VISIT_KEY = "__branch_visits__"
SUBGRAPH_KEY = "__subgraph__"
TOOL_ERROR_KEY = "__tool_error__"


def compile_v1_builder(
    document: FlowDefinitionV1,
    *,
    chat_client: ChatCompletionClient | None,
) -> tuple[StateGraph[GraphState], str, list[str]]:
    client = chat_client or get_chat_client()
    builder: StateGraph[GraphState] = StateGraph(GraphState)
    nodes = {node.id: node for node in document.nodes}
    start = next(n for n in document.nodes if n.type == "start")
    branch_by_source = _index_branches(document.branches)
    successors_of_start = [
        edge.target for edge in document.edges if edge.source == start.id
    ]
    for branch in document.branches:
        if branch.source == start.id:
            successors_of_start.extend([c.target for c in branch.cases])
            if branch.default_target:
                successors_of_start.append(branch.default_target)
    entry = next(
        (sid for sid in successors_of_start if sid not in {END_REF, start.id}),
        start.id,
    )

    for node in document.nodes:
        inner = _make_node(node, client)
        if node.id in branch_by_source:
            inner = _wrap_branch_visits(inner, branch_by_source[node.id])
        is_entry = node.id == entry or (
            node.id != start.id and node.id in successors_of_start
        )
        guarded = wrap_guardrail_node(node.id, node.type, inner, is_entry=is_entry)
        builder.add_node(node.id, wrap_graph_node(node.id, node.type, guarded))

    builder.add_edge(START, start.id)
    sourced_branch = set(branch_by_source)
    for edge in document.edges:
        if edge.source in sourced_branch:
            continue
        builder.add_edge(edge.source, _graph_target(edge.target, nodes))
    for source, branch in branch_by_source.items():
        mapping, router = _branch_mapping(branch, nodes)
        builder.add_conditional_edges(source, router, mapping)
    for node in document.nodes:
        if node.type == "end":
            builder.add_edge(node.id, END)
    return builder, start.id, [n.id for n in document.nodes]


def apply_start_inject(
    state: dict[str, object], document: FlowDefinitionV1
) -> dict[str, object]:
    start = next(n for n in document.nodes if n.type == "start")
    data = StartNodeData.model_validate(start.data)
    ctx = get_graph_exec_ctx()
    acc: dict[str, object] = {
        "messages": list(state.get("messages") or []),
        "variables": dict(state.get("variables") or {})
        if isinstance(state.get("variables"), dict)
        else {},
        "metadata": dict(state.get("metadata") or {})
        if isinstance(state.get("metadata"), dict)
        else {},
    }
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    for spec in data.inject:
        value: object
        if spec.source == "clock":
            value = now
        elif spec.source == "run":
            value = str(ctx.run_id) if ctx and ctx.run_id else None
        elif spec.source == "user":
            value = str(ctx.user_id) if ctx and ctx.user_id else None
        elif spec.source == "conversation":
            value = str(ctx.conversation_id) if ctx and ctx.conversation_id else None
        else:
            meta = acc["metadata"]
            value = meta.get("beat_task_id") if isinstance(meta, dict) else None
        if spec.channel == "messages":
            if value is not None:
                acc["messages"] = [
                    *list(acc["messages"]),
                    {"role": "system", "content": str(value)},
                ]
            continue
        key = spec.key or spec.source
        acc = set_path(acc, f"{spec.channel}.{key}", value)
    return acc


def _index_branches(branches: list[FlowBranch]) -> dict[str, FlowBranch]:
    indexed: dict[str, FlowBranch] = {}
    for branch in branches:
        if branch.source in indexed:
            raise ValueError(f"同一源节点不可有多条分支: {branch.source}")
        indexed[branch.source] = branch
    return indexed


def _graph_target(target: str, nodes: dict[str, FlowNode]) -> object:
    if target == END_REF:
        return END
    return target


def _make_node(node: FlowNode, client: ChatCompletionClient) -> NodeFn:
    if node.type in {"start", "end"}:
        return _passthrough_node
    if node.type == "llm":
        data = LlmNodeData.model_validate(node.data)
        return _make_v1_llm_node(data, client)
    if node.type == "tool":
        return _make_tool_node(node.id, ToolNodeData.model_validate(node.data))
    if node.type == "assign":
        return _make_assign_node(AssignNodeData.model_validate(node.data))
    if node.type == "hitl":
        return _make_hitl_node(node.id, HitlNodeData.model_validate(node.data))
    if node.type == "subgraph":
        return _make_subgraph_node(node.id, SubgraphNodeData.model_validate(node.data))
    if node.type == "custom":
        data = CustomNodeData.model_validate(node.data)
        if data.handler_key != "passthrough":
            raise ValueError(f"未知 custom.handler_key: {data.handler_key}")
        return _passthrough_node
    raise ValueError(f"未知节点类型: {node.type}")


def _make_v1_llm_node(data: LlmNodeData, fallback: ChatCompletionClient) -> NodeFn:
    async def _node(state: GraphState) -> dict[str, object]:
        client = fallback
        if not has_chat_client_override():
            client = await _client_from_ref(data.llm_ref)
        if data.stream:
            inner = _make_llm_node(client, data.system_prompt)
            return await inner(state)  # type: ignore[misc, no-any-return]
        from service.runtime.flow import _as_chat_messages

        messages = _as_chat_messages(state)
        if data.system_prompt:
            messages = [{"role": "system", "content": data.system_prompt}, *messages]
        content = await client.complete(messages)
        new_messages: list[dict[str, object]] = [
            *list(state.get("messages") or []),
            {"role": "assistant", "content": content},
        ]
        variables = dict(state.get("variables") or {})
        variables["last_output"] = content
        return {"messages": new_messages, "variables": variables}

    return _node


async def _client_from_ref(llm_ref: str) -> ChatCompletionClient:
    from service.runtime.llm import resolve_llm_client

    return await resolve_llm_client(code=llm_ref)


def _make_tool_node(node_id: str, data: ToolNodeData) -> NodeFn:
    async def _node(state: GraphState) -> dict[str, object]:
        arguments: dict[str, object] = {}
        mapping = dict(state)
        for name, path in data.arguments_from.items():
            arguments[name] = get_path(mapping, path)
        request = ToolCallRequest(
            tool_call_id=str(uuid4()),
            tool_code=data.tool_code,
            arguments=arguments,
        )
        result = await _execute_tool(request)
        variables = dict(state.get("variables") or {})
        if result.success:
            updated = set_path(
                {"messages": [], "variables": variables, "metadata": {}},
                data.output_to,
                result.output,
            )
            raw_vars = updated["variables"]
            variables = dict(raw_vars) if isinstance(raw_vars, dict) else variables
        else:
            raw_err = variables.get(TOOL_ERROR_KEY)
            errors = dict(raw_err) if isinstance(raw_err, dict) else {}
            errors[node_id] = result.error
            variables[TOOL_ERROR_KEY] = errors
        return {"variables": variables}

    return _node


async def _execute_tool(request: ToolCallRequest) -> ToolCallResult:
    ctx = get_graph_exec_ctx()
    if ctx is not None and ctx.tool_execute is not None:
        return await ctx.tool_execute(request)
    from service.database.session import session_scope
    from service.tools.executor import ToolExecutor

    async with session_scope() as session:
        return await ToolExecutor(session).execute(request)


def _make_assign_node(data: AssignNodeData) -> NodeFn:
    def _node(state: GraphState) -> dict[str, object]:
        acc: dict[str, object] = {
            "messages": list(state.get("messages") or []),
            "variables": dict(state.get("variables") or {})
            if isinstance(state.get("variables"), dict)
            else {},
            "metadata": dict(state.get("metadata") or {})
            if isinstance(state.get("metadata"), dict)
            else {},
        }
        for op in data.assignments:
            acc = set_path(acc, op.target, eval_expr(op.expr, acc))
        return {"variables": acc["variables"], "metadata": acc["metadata"]}

    return _node


def _make_hitl_node(node_id: str, data: HitlNodeData) -> NodeFn:
    def _node(state: GraphState) -> dict[str, object]:
        decision = interrupt(
            {
                "prompt": data.prompt_template,
                "form_schema": data.form_schema,
                "node_id": node_id,
                "on_reject": data.on_reject,
            }
        )
        variables = dict(state.get("variables") or {})
        variables["hitl_resume"] = decision
        return {"variables": variables}

    return _node


def _make_subgraph_node(node_id: str, data: SubgraphNodeData) -> NodeFn:
    def _node(state: GraphState) -> dict[str, object]:
        mapping = [(item.from_path, item.to_path) for item in data.input_map]
        child_input = map_state(dict(state), mapping)
        resumed = interrupt(
            {
                "kind": "subgraph_request",
                "node_id": node_id,
                "flow_code": data.flow_code,
                "version": data.version,
                "timeout_seconds": data.timeout_seconds,
                "child_input": child_input,
                "output_map": [item.model_dump() for item in data.output_map],
            }
        )
        return _merge_subgraph_resume(dict(state), node_id, resumed, data)

    return _node


def _merge_subgraph_resume(
    state: dict[str, object],
    node_id: str,
    resumed: object,
    data: SubgraphNodeData,
) -> dict[str, object]:
    payload = (
        resumed
        if isinstance(resumed, dict)
        else {"status": "failed", "output": {}, "error": str(resumed)}
    )
    variables = (
        dict(state.get("variables") or {})
        if isinstance(state.get("variables"), dict)
        else {}
    )
    raw_bucket = variables.get(SUBGRAPH_KEY)
    bucket = dict(raw_bucket) if isinstance(raw_bucket, dict) else {}
    bucket[node_id] = payload
    variables[SUBGRAPH_KEY] = bucket
    acc: dict[str, object] = {
        "messages": list(state.get("messages") or []),
        "variables": variables,
        "metadata": dict(state.get("metadata") or {})
        if isinstance(state.get("metadata"), dict)
        else {},
    }
    output = payload.get("output") if isinstance(payload, dict) else None
    source = output if isinstance(output, dict) else {}
    mapped = map_state(
        {
            "messages": list(source.get("messages") or [])
            if isinstance(source.get("messages"), list)
            else [],
            "variables": dict(source.get("variables") or {})
            if isinstance(source.get("variables"), dict)
            else {},
            "metadata": dict(source.get("metadata") or {})
            if isinstance(source.get("metadata"), dict)
            else {},
        },
        [(item.from_path, item.to_path) for item in data.output_map],
        target=acc,
    )
    return {
        "messages": mapped["messages"],
        "variables": mapped["variables"],
        "metadata": mapped["metadata"],
    }


def _wrap_branch_visits(inner: NodeFn, branch: FlowBranch) -> NodeFn:
    branch_id = branch.id

    async def _run(state: GraphState) -> object:
        from inspect import iscoroutinefunction

        out = await inner(state) if iscoroutinefunction(inner) else inner(state)
        return _bump_visits(state, out, branch_id)

    return _run


def _bump_visits(state: GraphState, out: object, branch_id: str) -> object:
    mapping = dict(out) if isinstance(out, dict) else {}
    metadata = dict(mapping.get("metadata") or state.get("metadata") or {})
    raw_visits = metadata.get(VISIT_KEY)
    visits = dict(raw_visits) if isinstance(raw_visits, dict) else {}
    current = visits.get(branch_id)
    visits[branch_id] = int(current) + 1 if isinstance(current, int) else 1
    metadata[VISIT_KEY] = visits
    mapping["metadata"] = metadata
    return mapping


def _branch_mapping(
    branch: FlowBranch, nodes: dict[str, FlowNode]
) -> tuple[dict[str, object], Callable[[GraphState], str]]:
    mapping: dict[str, object] = {}
    for case in branch.cases:
        mapping[case.key] = _graph_target(case.target, nodes)
    default_id = "__default__"
    if branch.default_target is not None:
        mapping[default_id] = _graph_target(branch.default_target, nodes)

    def _router(state: GraphState) -> str:
        visits_root = state.get("metadata") or {}
        visits: dict[str, object] = {}
        if isinstance(visits_root, dict):
            raw = visits_root.get(VISIT_KEY) or {}
            if isinstance(raw, dict):
                visits = raw
        count = visits.get(branch.id)
        n = int(count) if isinstance(count, int) else 0
        if branch.max_visits is not None and n > branch.max_visits:
            if branch.default_target is not None:
                return default_id
            raise ValueError(f"分支 {branch.id} 超过 max_visits={branch.max_visits}")
        key = _route_key(branch, dict(state))
        if key in mapping:
            return key
        if branch.default_target is not None:
            return default_id
        raise ValueError(f"分支 {branch.id} 未命中 case 且无 default_target: {key}")

    return mapping, _router


def _route_key(branch: FlowBranch, state: dict[str, object]) -> str:
    router = branch.router
    if router.kind == "state_path":
        if not router.path:
            raise ValueError(f"分支 {branch.id} 缺少 path")
        return router_key(get_path(state, router.path))
    if router.kind == "expr":
        if not router.expr:
            raise ValueError(f"分支 {branch.id} 缺少 expr")
        return router_key(eval_expr(router.expr, state))
    if router.kind == "hitl_decision":
        variables = (
            state.get("variables") if isinstance(state.get("variables"), dict) else {}
        )
        raw = variables.get("hitl_resume") if isinstance(variables, dict) else None
        if isinstance(raw, dict) and "decision" in raw:
            return str(raw["decision"])
        return router_key(raw)
    variables = state.get("variables") if isinstance(state.get("variables"), dict) else {}
    bucket = variables.get(SUBGRAPH_KEY) if isinstance(variables, dict) else None
    node_bucket = bucket.get(branch.source) if isinstance(bucket, dict) else None
    status = node_bucket.get("status") if isinstance(node_bucket, dict) else None
    return router_key(status)
