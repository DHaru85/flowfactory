"""Flow 图定义 schema_version=1（配置态校验与 runtime 编译共用）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChannelName = Literal["messages", "variables", "metadata"]
NodeType = Literal["start", "end", "llm", "tool", "assign", "hitl", "subgraph", "custom"]
END_REF = "__end__"

_MODEL_CONFIG = ConfigDict(extra="forbid")


class StrictModel(BaseModel):
    model_config = _MODEL_CONFIG


class StateChannelSpec(StrictModel):
    name: ChannelName
    reducer: Literal["append", "merge"]
    json_schema: dict[str, object] | None = None

    @model_validator(mode="after")
    def _reducer_matches_channel(self) -> StateChannelSpec:
        if self.name == "messages" and self.reducer != "append":
            raise ValueError("messages 的 reducer 必须为 append")
        if self.name != "messages" and self.reducer != "merge":
            raise ValueError(f"{self.name} 的 reducer 必须为 merge")
        if self.json_schema is not None and self.name != "variables":
            raise ValueError("仅 variables 可带 json_schema")
        return self


class GraphStateSpec(StrictModel):
    channels: list[StateChannelSpec]

    @model_validator(mode="after")
    def _exactly_three_slots(self) -> GraphStateSpec:
        names = [item.name for item in self.channels]
        expected = ["messages", "variables", "metadata"]
        if sorted(names) != sorted(expected) or len(names) != 3:
            raise ValueError("state.channels 必须恰好为 messages / variables / metadata 三槽")
        return self


class InjectSpec(StrictModel):
    source: Literal["run", "user", "conversation", "beat", "clock"]
    channel: ChannelName
    key: str | None = None


class StartNodeData(StrictModel):
    inject: list[InjectSpec] = Field(default_factory=list)


class EndNodeData(StrictModel):
    output_channels: list[ChannelName] = Field(default_factory=list)


class LlmNodeData(StrictModel):
    llm_ref: str
    system_prompt: str | None = None
    stream: bool = True


class ToolNodeData(StrictModel):
    tool_code: str
    arguments_from: dict[str, str] = Field(default_factory=dict)
    output_to: str

    @model_validator(mode="after")
    def _output_to_variables(self) -> ToolNodeData:
        if not self.output_to.startswith("variables."):
            raise ValueError("tool.output_to 必须为 variables.*")
        return self


class AssignOp(StrictModel):
    target: str
    expr: str

    @model_validator(mode="after")
    def _target_slot(self) -> AssignOp:
        if not (
            self.target.startswith("variables.") or self.target.startswith("metadata.")
        ):
            raise ValueError("assign.target 必须为 variables.* 或 metadata.*")
        return self


class AssignNodeData(StrictModel):
    assignments: list[AssignOp] = Field(default_factory=list)


class HitlNodeData(StrictModel):
    prompt_template: str
    form_schema: dict[str, object] | None = None
    on_reject: Literal["fail", "route"] = "fail"


class StateMapEntry(StrictModel):
    from_path: str
    to_path: str


class SubgraphNodeData(StrictModel):
    flow_code: str
    version: int | None = None
    input_map: list[StateMapEntry] = Field(default_factory=list)
    output_map: list[StateMapEntry] = Field(default_factory=list)
    timeout_seconds: int | None = None


class CustomNodeData(StrictModel):
    handler_key: str
    config: dict[str, object] = Field(default_factory=dict)


_DATA_MODELS: dict[str, type[BaseModel]] = {
    "start": StartNodeData,
    "end": EndNodeData,
    "llm": LlmNodeData,
    "tool": ToolNodeData,
    "assign": AssignNodeData,
    "hitl": HitlNodeData,
    "subgraph": SubgraphNodeData,
    "custom": CustomNodeData,
}


class FlowNode(StrictModel):
    id: str
    type: NodeType
    title: str | None = None
    data: dict[str, object]

    @model_validator(mode="after")
    def _typed_data(self) -> FlowNode:
        _DATA_MODELS[self.type].model_validate(self.data)
        return self


class FlowEdge(StrictModel):
    id: str
    source: str
    target: str
    label: str | None = None


class BranchCase(StrictModel):
    key: str
    target: str


class BranchRouter(StrictModel):
    kind: Literal["state_path", "expr", "hitl_decision", "child_status"]
    path: str | None = None
    expr: str | None = None


class FlowBranch(StrictModel):
    id: str
    source: str
    router: BranchRouter
    cases: list[BranchCase]
    default_target: str | None = None
    max_visits: int | None = None


class NodeLayout(StrictModel):
    x: float
    y: float
    w: float | None = None
    h: float | None = None
    z: int | None = None


class EdgeLayout(StrictModel):
    waypoints: list[list[float]] | None = None
    color: str | None = None


class FlowView(StrictModel):
    nodes: dict[str, NodeLayout] = Field(default_factory=dict)
    edges: dict[str, EdgeLayout] = Field(default_factory=dict)
    branches: dict[str, EdgeLayout] = Field(default_factory=dict)
    groups: list[dict[str, object]] | None = None
    computed_levels: dict[str, int] | None = None


class FlowDefinitionV1(StrictModel):
    """配置态与运行态共用的 v1 图文档。"""

    schema_version: Literal[1] = 1
    state: GraphStateSpec
    nodes: list[FlowNode]
    edges: list[FlowEdge] = Field(default_factory=list)
    branches: list[FlowBranch] = Field(default_factory=list)
    view: FlowView | None = None

    @model_validator(mode="after")
    def _graph_invariants(self) -> FlowDefinitionV1:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("节点 id 必须唯一")
        id_set = set(node_ids)
        starts = [n for n in self.nodes if n.type == "start"]
        ends = [n for n in self.nodes if n.type == "end"]
        if len(starts) != 1:
            raise ValueError("必须恰好一个 start 节点")
        if len(ends) < 1:
            raise ValueError("至少需要一个 end 节点")

        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("边 id 必须唯一")
        branch_ids = [branch.id for branch in self.branches]
        if len(branch_ids) != len(set(branch_ids)):
            raise ValueError("分支 id 必须唯一")
        if set(edge_ids) & set(branch_ids):
            raise ValueError("边 id 与分支 id 不可冲突")

        def _endpoint_ok(ref: str) -> bool:
            return ref == END_REF or ref in id_set

        for edge in self.edges:
            if edge.source not in id_set:
                raise ValueError(f"边 {edge.id} 的 source 不存在: {edge.source}")
            if not _endpoint_ok(edge.target):
                raise ValueError(f"边 {edge.id} 的 target 不存在: {edge.target}")
        for branch in self.branches:
            if branch.source not in id_set:
                raise ValueError(f"分支 {branch.id} 的 source 不存在")
            if branch.default_target is not None and not _endpoint_ok(branch.default_target):
                raise ValueError(f"分支 {branch.id} 的 default_target 不存在")
            for case in branch.cases:
                if not _endpoint_ok(case.target):
                    raise ValueError(f"分支 {branch.id} 的 case {case.key} target 不存在")
        return self


def default_state_spec() -> GraphStateSpec:
    return GraphStateSpec(
        channels=[
            StateChannelSpec(name="messages", reducer="append"),
            StateChannelSpec(name="variables", reducer="merge"),
            StateChannelSpec(name="metadata", reducer="merge"),
        ]
    )


def empty_flow_definition() -> FlowDefinitionV1:
    """合法空图：start → end。"""
    return FlowDefinitionV1(
        state=default_state_spec(),
        nodes=[
            FlowNode(id="start", type="start", title="开始", data={"inject": []}),
            FlowNode(
                id="end",
                type="end",
                title="结束",
                data={"output_channels": ["messages", "variables", "metadata"]},
            ),
        ],
        edges=[FlowEdge(id="e-start-end", source="start", target="end")],
        branches=[],
        view=None,
    )


def parse_flow_definition(raw: dict[str, object]) -> FlowDefinitionV1:
    return FlowDefinitionV1.model_validate(raw)


def subgraph_flow_codes(document: FlowDefinitionV1) -> list[str]:
    codes: list[str] = []
    for node in document.nodes:
        if node.type != "subgraph":
            continue
        data = SubgraphNodeData.model_validate(node.data)
        codes.append(data.flow_code)
    return codes
