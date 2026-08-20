import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button, Input, Select, Space, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useState, type ReactElement } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { errorMessage } from "@/api/client";
import {
  getStudioFlow,
  listPublishedFlowCodes,
  listStudioFlows,
  listStudioLlms,
  listStudioProfiles,
  listStudioTools,
  newStudioDraft,
  patchStudioFlow,
  publishStudioFlow,
} from "@/api/studio";
import { findApp, useSession } from "@/auth/context";
import { Inspector, type Selection } from "@/studio/Inspector";
import { TypedFlowNode, type CanvasNode } from "@/studio/TypedNode";
import {
  addEdge,
  clientValidate,
  defaultNodeData,
  edgeToBranch,
  newEdgeId,
  newNodeId,
  NODE_TYPES,
  removeBranch,
  removeEdge,
  removeNode,
  replaceBranch,
  replaceEdge,
  replaceNode,
  setNodeLayout,
  upsertNode,
} from "@/studio/document";
import type {
  FlowDefinitionV1,
  FlowOut,
  LlmCatalogOut,
  NodeType,
  ProfileCatalogOut,
  PublishedFlowCodeOut,
  ToolCatalogOut,
} from "@/types";

const DRILL_MAX_DEPTH = 8;

interface DrillFrame {
  flowId: string;
  code: string;
  version: number;
  document: FlowDefinitionV1;
}

function frameKey(code: string, version: number): string {
  return `${code}@${version}`;
}

const nodeTypes = { typed: TypedFlowNode };

interface BranchEdgeData extends Record<string, unknown> {
  kind: "branch";
  branchId: string;
}

function toRfNodes(doc: FlowDefinitionV1, readOnly: boolean): CanvasNode[] {
  return doc.nodes.map((node, index) => {
    const layout = doc.view?.nodes[node.id];
    return {
      id: node.id,
      type: "typed",
      position: {
        x: layout?.x ?? 80 + (index % 4) * 220,
        y: layout?.y ?? 80 + Math.floor(index / 4) * 140,
      },
      data: { nodeType: node.type, title: node.title ?? node.id },
      deletable: !readOnly && node.type !== "start",
    };
  });
}

function toRfEdges(doc: FlowDefinitionV1): Edge[] {
  const plain: Edge[] = doc.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label ?? undefined,
  }));
  const branched: Edge[] = [];
  for (const branch of doc.branches) {
    for (const item of branch.cases) {
      branched.push({
        id: `br:${branch.id}:c:${item.key}`,
        source: branch.source,
        target: item.target,
        label: item.key,
        style: { stroke: "#fa8c16" },
        data: { kind: "branch", branchId: branch.id } satisfies BranchEdgeData,
      });
    }
    if (branch.default_target !== null) {
      branched.push({
        id: `br:${branch.id}:d`,
        source: branch.source,
        target: branch.default_target,
        label: "default",
        style: { stroke: "#fa8c16", strokeDasharray: "4 4" },
        data: { kind: "branch", branchId: branch.id } satisfies BranchEdgeData,
      });
    }
  }
  return [...plain, ...branched];
}

function StudioCanvasInner(): ReactElement {
  const { flowId } = useParams<{ flowId: string }>();
  const navigate = useNavigate();
  const { apps } = useSession();
  const canControl = findApp(apps, "studio")?.can_control === true;

  const [flow, setFlow] = useState<FlowOut | null>(null);
  const [document, setDocument] = useState<FlowDefinitionV1 | null>(null);
  const [name, setName] = useState("");
  const [profileId, setProfileId] = useState("");
  const [dirty, setDirty] = useState(false);
  const [nodes, setNodes] = useState<CanvasNode[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selection, setSelection] = useState<Selection>(null);
  const [profiles, setProfiles] = useState<ProfileCatalogOut[]>([]);
  const [llms, setLlms] = useState<LlmCatalogOut[]>([]);
  const [tools, setTools] = useState<ToolCatalogOut[]>([]);
  const [publishedCodes, setPublishedCodes] = useState<PublishedFlowCodeOut[]>([]);
  const [stack, setStack] = useState<DrillFrame[]>([]);

  const rootReadOnly = !canControl || flow?.status !== "draft";
  const readOnly = rootReadOnly || stack.length > 0;
  const viewingDocument =
    stack.length > 0 ? stack[stack.length - 1].document : document;

  const load = useCallback(async (id: string) => {
    const row = await getStudioFlow(id);
    setFlow(row);
    setDocument(row.definition);
    setName(row.name);
    setProfileId(row.profile_id);
    setDirty(false);
    setSelection(null);
    setStack([]);
  }, []);

  useEffect(() => {
    if (flowId === undefined) {
      return;
    }
    void load(flowId).catch((err: unknown) => message.error(errorMessage(err, "加载 Flow 失败")));
  }, [flowId, load]);

  useEffect(() => {
    void Promise.all([
      listStudioProfiles(),
      listStudioLlms(),
      listStudioTools(),
      listPublishedFlowCodes(),
    ])
      .then(([p, l, t, c]) => {
        setProfiles(p);
        setLlms(l);
        setTools(t);
        setPublishedCodes(c);
      })
      .catch((err: unknown) => message.error(errorMessage(err, "加载目录失败")));
  }, []);

  useEffect(() => {
    if (viewingDocument === null) {
      return;
    }
    setNodes(toRfNodes(viewingDocument, readOnly));
    setEdges(toRfEdges(viewingDocument));
  }, [viewingDocument, readOnly]);

  const mutate = useCallback((next: FlowDefinitionV1) => {
    setDocument(next);
    setDirty(true);
  }, []);

  const drillInto = async (flowCode: string, version: number | null): Promise<void> => {
    if (flow === null || document === null) {
      return;
    }
    if (1 + stack.length >= DRILL_MAX_DEPTH) {
      message.warning("下钻深度已达上限");
      return;
    }
    const rows = await listStudioFlows("published", flowCode);
    if (rows.length === 0) {
      message.error("未找到已发布的子图");
      return;
    }
    const target =
      version === null
        ? rows.reduce((best, row) => (row.version > best.version ? row : best))
        : rows.find((row) => row.version === version);
    if (target === undefined) {
      message.error("未找到指定版本的子图");
      return;
    }
    const key = frameKey(target.code, target.version);
    const seen = [frameKey(flow.code, flow.version), ...stack.map((item) => frameKey(item.code, item.version))];
    if (seen.includes(key)) {
      message.warning("子图引用成环，已拒绝下钻");
      return;
    }
    const full = await getStudioFlow(target.id);
    setStack((prev) => [
      ...prev,
      { flowId: full.id, code: full.code, version: full.version, document: full.definition },
    ]);
    setSelection(null);
  };

  const onNodesChange = useCallback(
    (changes: NodeChange<CanvasNode>[]) => {
      setNodes((current) => applyNodeChanges(changes, current));
      if (readOnly) {
        return;
      }
      for (const change of changes) {
        if (change.type === "position" && change.position !== undefined && change.dragging === false) {
          const { x, y } = change.position;
          setDirty(true);
          setDocument((current) =>
            current === null ? current : setNodeLayout(current, change.id, x, y),
          );
        }
        if (change.type === "remove") {
          setDocument((current) => {
            if (current === null) {
              return current;
            }
            const result = removeNode(current, change.id);
            if (typeof result === "string") {
              message.warning(result);
              return current;
            }
            setSelection(null);
            setDirty(true);
            return result;
          });
        }
      }
    },
    [readOnly],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setEdges((current) => applyEdgeChanges(changes, current));
      if (readOnly) {
        return;
      }
      for (const change of changes) {
        if (change.type !== "remove") {
          continue;
        }
        setDocument((current) => {
          if (current === null) {
            return current;
          }
          const rf = current.edges.find((item) => item.id === change.id);
          if (rf !== undefined) {
            setDirty(true);
            return removeEdge(current, change.id);
          }
          const parts = change.id.split(":");
          const branchId = change.id.startsWith("br:") ? parts[1] : undefined;
          if (branchId !== undefined && branchId !== "") {
            setDirty(true);
            return removeBranch(current, branchId);
          }
          return current;
        });
      }
    },
    [readOnly],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (readOnly || document === null || connection.source === null || connection.target === null) {
        return;
      }
      const result = addEdge(document, {
        id: newEdgeId(),
        source: connection.source,
        target: connection.target,
        label: null,
      });
      if (typeof result === "string") {
        message.warning(result);
        return;
      }
      mutate(result);
    },
    [document, mutate, readOnly],
  );

  const addPaletteNode = (type: NodeType): void => {
    if (document === null || readOnly) {
      return;
    }
    const id = type === "end" ? newNodeId("end") : newNodeId(type);
    mutate(
      upsertNode(
        document,
        { id, type, title: type, data: defaultNodeData(type) },
        120 + document.nodes.length * 24,
        200,
      ),
    );
  };

  const save = async (): Promise<void> => {
    if (flow === null || document === null) {
      return;
    }
    const problem = clientValidate(document);
    if (problem !== null) {
      message.error(problem);
      return;
    }
    const saved = await patchStudioFlow(flow.id, {
      name,
      profile_id: profileId,
      definition: document,
    });
    setFlow(saved);
    setDocument(saved.definition);
    setDirty(false);
    message.success("已保存");
  };

  const publish = async (): Promise<void> => {
    if (flow === null) {
      return;
    }
    if (dirty) {
      await save();
    }
    const published = await publishStudioFlow(flow.id);
    setFlow(published);
    setDocument(published.definition);
    setDirty(false);
    message.success("已发布");
  };

  const openNewDraft = async (): Promise<void> => {
    if (flow === null) {
      return;
    }
    const created = await newStudioDraft(flow.id);
    navigate(`/studio/${created.id}`);
  };

  const selectedRf = useMemo(() => {
    if (selection?.kind === "node") {
      return { nodes: [selection.id], edges: [] as string[] };
    }
    if (selection?.kind === "edge") {
      return { nodes: [] as string[], edges: [selection.id] };
    }
    if (selection?.kind === "branch") {
      return {
        nodes: [] as string[],
        edges: edges.filter((item) => {
          const data = item.data as BranchEdgeData | undefined;
          return data?.kind === "branch" && data.branchId === selection.id;
        }).map((item) => item.id),
      };
    }
    return { nodes: [] as string[], edges: [] as string[] };
  }, [edges, selection]);

  if (flow === null || document === null || viewingDocument === null) {
    return <Typography.Text>加载中…</Typography.Text>;
  }

  return (
    <div style={{ margin: -24, height: "calc(100vh - 64px)", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          padding: "8px 16px",
          borderBottom: "1px solid #f0f0f0",
          display: "flex",
          gap: 12,
          alignItems: "center",
        }}
      >
        <Link to="/studio">返回列表</Link>
        <Button type="link" onClick={() => { setStack([]); setSelection(null); }}>
          {flow.code}@{flow.version}
        </Button>
        {stack.map((frame, idx) => (
          <Button
            key={`${frame.flowId}-${idx}`}
            type="link"
            onClick={() => {
              setStack((prev) => prev.slice(0, idx + 1));
              setSelection(null);
            }}
          >
            / {frame.code}@{frame.version}
          </Button>
        ))}
        <Typography.Text>
          {stack.length > 0 ? "只读子图" : flow.status}
          {dirty && stack.length === 0 ? " · 未保存" : ""}
        </Typography.Text>
        <Input
          value={name}
          onChange={(ev) => {
            setName(ev.target.value);
            setDirty(true);
          }}
          disabled={readOnly}
          style={{ width: 200 }}
        />
        <Select
          value={profileId}
          onChange={(value: string) => {
            setProfileId(value);
            setDirty(true);
          }}
          disabled={readOnly}
          style={{ width: 240 }}
          options={profiles.map((item) => ({ value: item.id, label: `${item.code} ${item.name}` }))}
        />
        <Space>
          {canControl && flow.status === "draft" ? (
            <>
              <Button type="primary" onClick={() => void save().catch((err: unknown) => message.error(errorMessage(err, "保存失败")))}>
                保存
              </Button>
              <Button onClick={() => void publish().catch((err: unknown) => message.error(errorMessage(err, "发布失败")))}>
                发布
              </Button>
            </>
          ) : null}
          {canControl && flow.status === "published" ? (
            <Button onClick={() => void openNewDraft().catch((err: unknown) => message.error(errorMessage(err, "开新草稿失败")))}>
              新草稿
            </Button>
          ) : null}
        </Space>
      </div>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ width: 140, borderRight: "1px solid #f0f0f0", padding: 8 }}>
          <Typography.Text type="secondary">节点</Typography.Text>
          {NODE_TYPES.map((item) => (
            <Button
              key={item.type}
              block
              size="small"
              disabled={readOnly}
              style={{ marginTop: 8 }}
              onClick={() => addPaletteNode(item.type)}
            >
              {item.label}
            </Button>
          ))}
        </div>
        <div style={{ flex: 1 }}>
          <ReactFlow
            nodes={nodes.map((node) => ({
              ...node,
              selected: selectedRf.nodes.includes(node.id),
            }))}
            edges={edges.map((edge) => ({
              ...edge,
              selected: selectedRf.edges.includes(edge.id),
            }))}
            nodeTypes={nodeTypes}
            nodesDraggable={!readOnly}
            nodesConnectable={!readOnly}
            deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_ev, node) => setSelection({ kind: "node", id: node.id })}
            onEdgeClick={(_ev, edge) => {
              const data = edge.data as BranchEdgeData | undefined;
              if (data?.kind === "branch") {
                setSelection({ kind: "branch", id: data.branchId });
                return;
              }
              setSelection({ kind: "edge", id: edge.id });
            }}
            onPaneClick={() => setSelection(null)}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>
        <div style={{ width: 320, borderLeft: "1px solid #f0f0f0", padding: 12, overflow: "auto" }}>
          <Inspector
            document={viewingDocument}
            selection={selection}
            readOnly={readOnly}
            llms={llms}
            tools={tools}
            publishedCodes={publishedCodes}
            onDrill={(code, version) => {
              void drillInto(code, version).catch((err: unknown) =>
                message.error(errorMessage(err, "下钻失败")),
              );
            }}
            onChangeNode={(node) => mutate(replaceNode(document, node))}
            onChangeEdge={(edge) => mutate(replaceEdge(document, edge))}
            onChangeBranch={(branch) => mutate(replaceBranch(document, branch))}
            onConvertEdge={(edgeId) => {
              const result = edgeToBranch(document, edgeId);
              if (typeof result === "string") {
                message.warning(result);
                return;
              }
              mutate(result);
              const created = result.branches[result.branches.length - 1];
              if (created !== undefined) {
                setSelection({ kind: "branch", id: created.id });
              }
            }}
            onDelete={() => {
              if (selection === null) {
                return;
              }
              if (selection.kind === "node") {
                const result = removeNode(document, selection.id);
                if (typeof result === "string") {
                  message.warning(result);
                  return;
                }
                mutate(result);
                setSelection(null);
                return;
              }
              if (selection.kind === "edge") {
                mutate(removeEdge(document, selection.id));
                setSelection(null);
                return;
              }
              mutate(removeBranch(document, selection.id));
              setSelection(null);
            }}
          />
        </div>
      </div>
    </div>
  );
}

export function StudioCanvasPage(): ReactElement {
  return (
    <ReactFlowProvider>
      <StudioCanvasInner />
    </ReactFlowProvider>
  );
}
