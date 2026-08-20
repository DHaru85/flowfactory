import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { CSSProperties, ReactElement } from "react";

import type { NodeType } from "@/types";

export interface CanvasNodeData extends Record<string, unknown> {
  nodeType: NodeType;
  title: string;
}

export type CanvasNode = Node<CanvasNodeData>;

const COLORS: Record<NodeType, string> = {
  start: "#52c41a",
  end: "#8c8c8c",
  llm: "#1677ff",
  tool: "#13c2c2",
  assign: "#722ed1",
  hitl: "#fa8c16",
  subgraph: "#eb2f96",
  custom: "#2f54eb",
};

export function TypedFlowNode({ data, selected }: NodeProps<CanvasNode>): ReactElement {
  const color = COLORS[data.nodeType];
  const box: CSSProperties = {
    border: `2px solid ${selected ? color : "#d9d9d9"}`,
    borderRadius: 8,
    background: "#fff",
    minWidth: 140,
    padding: "8px 12px",
  };
  return (
    <div style={box}>
      {data.nodeType !== "start" ? <Handle type="target" position={Position.Left} /> : null}
      <div style={{ fontSize: 11, color }}>{data.nodeType}</div>
      <div style={{ fontWeight: 600 }}>{data.title}</div>
      {data.nodeType !== "end" ? <Handle type="source" position={Position.Right} /> : null}
    </div>
  );
}
