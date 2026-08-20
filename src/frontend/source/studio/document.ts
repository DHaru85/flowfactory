import type { FlowBranch, FlowDefinitionV1, FlowEdge, FlowNode, FlowView, NodeType } from "@/types";

export const NODE_TYPES: { type: NodeType; label: string }[] = [
  { type: "llm", label: "LLM" },
  { type: "tool", label: "工具" },
  { type: "assign", label: "赋值" },
  { type: "hitl", label: "人工" },
  { type: "subgraph", label: "子图" },
  { type: "custom", label: "自定义" },
  { type: "end", label: "结束" },
];

export function defaultNodeData(type: NodeType): Record<string, unknown> {
  switch (type) {
    case "start":
      return { inject: [] };
    case "end":
      return { output_channels: ["messages", "variables", "metadata"] };
    case "llm":
      return { llm_ref: "", system_prompt: null, stream: true };
    case "tool":
      return { tool_code: "", arguments_from: {}, output_to: "variables.result" };
    case "assign":
      return { assignments: [] };
    case "hitl":
      return { prompt_template: "请审批", form_schema: null, on_reject: "fail" };
    case "subgraph":
      return {
        flow_code: "",
        version: null,
        input_map: [],
        output_map: [],
        timeout_seconds: null,
      };
    case "custom":
      return { handler_key: "passthrough", config: {} };
  }
}

export function newNodeId(type: NodeType): string {
  return `${type}-${crypto.randomUUID().slice(0, 8)}`;
}

export function newEdgeId(): string {
  return `e-${crypto.randomUUID().slice(0, 8)}`;
}

export function newBranchId(): string {
  return `b-${crypto.randomUUID().slice(0, 8)}`;
}

export function cloneDefinition(doc: FlowDefinitionV1): FlowDefinitionV1 {
  return structuredClone(doc);
}

export function ensureView(doc: FlowDefinitionV1): FlowView {
  if (doc.view !== null) {
    return doc.view;
  }
  return {
    nodes: {},
    edges: {},
    branches: {},
    groups: null,
    computed_levels: null,
  };
}

export function setNodeLayout(doc: FlowDefinitionV1, nodeId: string, x: number, y: number): FlowDefinitionV1 {
  const next = cloneDefinition(doc);
  const view = ensureView(next);
  const prev = view.nodes[nodeId];
  view.nodes[nodeId] = {
    x,
    y,
    w: prev?.w ?? null,
    h: prev?.h ?? null,
    z: prev?.z ?? null,
  };
  next.view = view;
  return next;
}

export function upsertNode(doc: FlowDefinitionV1, node: FlowNode, x: number, y: number): FlowDefinitionV1 {
  const next = cloneDefinition(doc);
  next.nodes = [...next.nodes, node];
  return setNodeLayout(next, node.id, x, y);
}

export function replaceNode(doc: FlowDefinitionV1, node: FlowNode): FlowDefinitionV1 {
  const next = cloneDefinition(doc);
  next.nodes = next.nodes.map((item) => (item.id === node.id ? node : item));
  return next;
}

export function removeNode(doc: FlowDefinitionV1, nodeId: string): FlowDefinitionV1 | string {
  const node = doc.nodes.find((item) => item.id === nodeId);
  if (node === undefined) {
    return "节点不存在";
  }
  if (node.type === "start") {
    return "不可删除 start 节点";
  }
  if (node.type === "end" && doc.nodes.filter((item) => item.type === "end").length <= 1) {
    return "至少保留一个 end 节点";
  }
  const next = cloneDefinition(doc);
  next.nodes = next.nodes.filter((item) => item.id !== nodeId);
  next.edges = next.edges.filter((item) => item.source !== nodeId && item.target !== nodeId);
  next.branches = next.branches
    .map((branch) => ({
      ...branch,
      cases: branch.cases.filter((item) => item.target !== nodeId),
      default_target: branch.default_target === nodeId ? null : branch.default_target,
    }))
    .filter((branch) => branch.source !== nodeId);
  if (next.view !== null) {
    const rest = { ...next.view.nodes };
    delete rest[nodeId];
    next.view.nodes = rest;
  }
  return next;
}

export function addEdge(doc: FlowDefinitionV1, edge: FlowEdge): FlowDefinitionV1 | string {
  if (edge.source === edge.target) {
    return "不允许自环";
  }
  if (!doc.nodes.some((item) => item.id === edge.source)) {
    return "连线起点不存在";
  }
  if (!doc.nodes.some((item) => item.id === edge.target) && edge.target !== "__end__") {
    return "连线终点不存在";
  }
  const next = cloneDefinition(doc);
  next.edges = [...next.edges, edge];
  return next;
}

export function replaceEdge(doc: FlowDefinitionV1, edge: FlowEdge): FlowDefinitionV1 {
  const next = cloneDefinition(doc);
  next.edges = next.edges.map((item) => (item.id === edge.id ? edge : item));
  return next;
}

export function removeEdge(doc: FlowDefinitionV1, edgeId: string): FlowDefinitionV1 {
  const next = cloneDefinition(doc);
  next.edges = next.edges.filter((item) => item.id !== edgeId);
  return next;
}

export function addBranch(doc: FlowDefinitionV1, branch: FlowBranch): FlowDefinitionV1 {
  const next = cloneDefinition(doc);
  next.branches = [...next.branches, branch];
  return next;
}

export function replaceBranch(doc: FlowDefinitionV1, branch: FlowBranch): FlowDefinitionV1 {
  const next = cloneDefinition(doc);
  next.branches = next.branches.map((item) => (item.id === branch.id ? branch : item));
  return next;
}

export function removeBranch(doc: FlowDefinitionV1, branchId: string): FlowDefinitionV1 {
  const next = cloneDefinition(doc);
  next.branches = next.branches.filter((item) => item.id !== branchId);
  return next;
}

export function edgeToBranch(doc: FlowDefinitionV1, edgeId: string): FlowDefinitionV1 | string {
  const edge = doc.edges.find((item) => item.id === edgeId);
  if (edge === undefined) {
    return "边不存在";
  }
  const next = removeEdge(doc, edgeId);
  return addBranch(next, {
    id: newBranchId(),
    source: edge.source,
    router: { kind: "state_path", path: "variables.route", expr: null },
    cases: [{ key: "default-case", target: edge.target }],
    default_target: null,
    max_visits: null,
  });
}

function isNonEmptyString(value: unknown): boolean {
  return typeof value === "string" && value.trim() !== "";
}

export function clientValidate(doc: FlowDefinitionV1): string | null {
  const ids = doc.nodes.map((item) => item.id);
  if (new Set(ids).size !== ids.length) {
    return "节点 id 必须唯一";
  }
  if (doc.nodes.filter((item) => item.type === "start").length !== 1) {
    return "必须恰好一个 start 节点";
  }
  if (doc.nodes.filter((item) => item.type === "end").length < 1) {
    return "至少需要一个 end 节点";
  }
  const edgeIds = doc.edges.map((item) => item.id);
  const branchIds = doc.branches.map((item) => item.id);
  if (new Set(edgeIds).size !== edgeIds.length) {
    return "边 id 必须唯一";
  }
  if (new Set(branchIds).size !== branchIds.length) {
    return "分支 id 必须唯一";
  }
  if (edgeIds.some((id) => branchIds.includes(id))) {
    return "边 id 与分支 id 不可冲突";
  }
  for (const node of doc.nodes) {
    if (node.type === "llm" && !isNonEmptyString(node.data.llm_ref)) {
      return `节点 ${node.id} 缺少 llm_ref`;
    }
    if (node.type === "tool") {
      if (!isNonEmptyString(node.data.tool_code)) {
        return `节点 ${node.id} 缺少 tool_code`;
      }
      if (typeof node.data.output_to !== "string" || !node.data.output_to.startsWith("variables.")) {
        return `节点 ${node.id} 的 output_to 必须为 variables.*`;
      }
    }
    if (node.type === "hitl" && !isNonEmptyString(node.data.prompt_template)) {
      return `节点 ${node.id} 缺少 prompt_template`;
    }
    if (node.type === "subgraph" && !isNonEmptyString(node.data.flow_code)) {
      return `节点 ${node.id} 缺少 flow_code`;
    }
    if (node.type === "custom" && !isNonEmptyString(node.data.handler_key)) {
      return `节点 ${node.id} 缺少 handler_key`;
    }
  }
  return null;
}
