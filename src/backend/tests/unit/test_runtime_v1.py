"""FlowRuntime schema_version=1 编译。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from service.runtime.context import (  # noqa: E402
    GraphExecContext,
    attach_graph_exec_ctx,
    reset_graph_exec_ctx,
)
from service.runtime.definition_v1 import (  # noqa: E402
    FlowDefinitionV1,
    FlowEdge,
    FlowNode,
    default_state_spec,
    empty_flow_definition,
)
from service.runtime.flow import FlowRuntime  # noqa: E402
from service.runtime.schemas import RunStatePayload  # noqa: E402
from service.tools.schemas import ToolCallResult  # noqa: E402


def _compile(doc: FlowDefinitionV1) -> FlowRuntime:
    return FlowRuntime.compile(doc, flow_id=uuid4(), checkpointer=InMemorySaver())


@pytest.mark.asyncio
async def test_v1_empty_start_end() -> None:
    runtime = _compile(empty_flow_definition())
    result = await runtime.graph.ainvoke(
        RunStatePayload(variables={"input": "hi"}).to_graph_state(),
        {"configurable": {"thread_id": "t-empty"}},
    )
    assert result["variables"]["input"] == "hi"
    snap = await runtime.graph.aget_state({"configurable": {"thread_id": "t-empty"}})
    assert snap.next == ()


@pytest.mark.asyncio
async def test_v1_assign_and_state_path_branch() -> None:
    doc = FlowDefinitionV1(
        state=default_state_spec(),
        nodes=[
            FlowNode(id="start", type="start", data={"inject": []}),
            FlowNode(
                id="set",
                type="assign",
                data={
                    "assignments": [
                        {"target": "variables.route", "expr": "\"go\""},
                    ]
                },
            ),
            FlowNode(
                id="yes",
                type="assign",
                data={"assignments": [{"target": "variables.hit", "expr": "true"}]},
            ),
            FlowNode(id="end", type="end", data={"output_channels": []}),
        ],
        edges=[
            FlowEdge(id="e1", source="start", target="set"),
            FlowEdge(id="e2", source="yes", target="end"),
        ],
        branches=[
            {
                "id": "b1",
                "source": "set",
                "router": {"kind": "state_path", "path": "variables.route"},
                "cases": [{"key": "go", "target": "yes"}],
                "default_target": "end",
            }
        ],
    )
    runtime = _compile(doc)
    result = await runtime.graph.ainvoke(
        RunStatePayload().to_graph_state(),
        {"configurable": {"thread_id": "t-br"}},
    )
    assert result["variables"]["hit"] is True


@pytest.mark.asyncio
async def test_v1_hitl_interrupt_resume() -> None:
    doc = FlowDefinitionV1(
        state=default_state_spec(),
        nodes=[
            FlowNode(id="start", type="start", data={"inject": []}),
            FlowNode(
                id="ask",
                type="hitl",
                data={"prompt_template": "确认?", "on_reject": "fail"},
            ),
            FlowNode(id="end", type="end", data={"output_channels": []}),
        ],
        edges=[
            FlowEdge(id="e1", source="start", target="ask"),
            FlowEdge(id="e2", source="ask", target="end"),
        ],
    )
    runtime = _compile(doc)
    config = {"configurable": {"thread_id": "t-h"}}
    first = await runtime.graph.ainvoke(RunStatePayload().to_graph_state(), config)
    assert "__interrupt__" in first
    second = await runtime.graph.ainvoke(Command(resume="approve"), config)
    assert second["variables"]["hitl_resume"] == "approve"


@pytest.mark.asyncio
async def test_v1_tool_writes_variables() -> None:
    async def _exec(request: object) -> ToolCallResult:
        return ToolCallResult(tool_call_id="1", success=True, output={"n": 7})

    doc = FlowDefinitionV1(
        state=default_state_spec(),
        nodes=[
            FlowNode(id="start", type="start", data={"inject": []}),
            FlowNode(
                id="t",
                type="tool",
                data={
                    "tool_code": "demo",
                    "arguments_from": {"q": "variables.input"},
                    "output_to": "variables.tool_out",
                },
            ),
            FlowNode(id="end", type="end", data={"output_channels": []}),
        ],
        edges=[
            FlowEdge(id="e1", source="start", target="t"),
            FlowEdge(id="e2", source="t", target="end"),
        ],
    )
    token = attach_graph_exec_ctx(GraphExecContext(tool_execute=_exec))
    try:
        runtime = _compile(doc)
        result = await runtime.graph.ainvoke(
            RunStatePayload(variables={"input": "x"}).to_graph_state(),
            {"configurable": {"thread_id": "t-tool"}},
        )
        assert result["variables"]["tool_out"] == {"n": 7}
    finally:
        reset_graph_exec_ctx(token)


def test_v1_unknown_custom_fails_compile() -> None:
    doc = FlowDefinitionV1(
        state=default_state_spec(),
        nodes=[
            FlowNode(id="start", type="start", data={"inject": []}),
            FlowNode(
                id="c",
                type="custom",
                data={"handler_key": "nope", "config": {}},
            ),
            FlowNode(id="end", type="end", data={"output_channels": []}),
        ],
        edges=[
            FlowEdge(id="e1", source="start", target="c"),
            FlowEdge(id="e2", source="c", target="end"),
        ],
    )
    with pytest.raises(ValueError, match="handler_key"):
        _compile(doc)


@pytest.mark.asyncio
async def test_v1_subgraph_interrupts_without_nested_compile() -> None:
    doc = FlowDefinitionV1(
        state=default_state_spec(),
        nodes=[
            FlowNode(id="start", type="start", data={"inject": []}),
            FlowNode(
                id="sub",
                type="subgraph",
                data={"flow_code": "child", "input_map": [], "output_map": []},
            ),
            FlowNode(id="end", type="end", data={"output_channels": []}),
        ],
        edges=[
            FlowEdge(id="e1", source="start", target="sub"),
            FlowEdge(id="e2", source="sub", target="end"),
        ],
    )
    runtime = _compile(doc)
    config = {"configurable": {"thread_id": "t-sub"}}
    first = await runtime.graph.ainvoke(RunStatePayload().to_graph_state(), config)
    assert "__interrupt__" in first
    interrupts = first["__interrupt__"]
    value = interrupts[0].value
    assert value["kind"] == "subgraph_request"
    assert value["flow_code"] == "child"
    second = await runtime.graph.ainvoke(
        Command(resume={"status": "completed", "output": {"variables": {"k": 1}}, "error": None}),
        config,
    )
    assert second["variables"]["__subgraph__"]["sub"]["status"] == "completed"
