import { Button, Form, Input, InputNumber, Select, Switch, Typography, message } from "antd";
import { useEffect, type ReactElement } from "react";

import { parseObjectJson, prettyJson } from "@/lib/json";
import type {
  ChannelName,
  FlowBranch,
  FlowDefinitionV1,
  FlowEdge,
  FlowNode,
  LlmCatalogOut,
  PublishedFlowCodeOut,
  ToolCatalogOut,
} from "@/types";

export type Selection =
  | { kind: "node"; id: string }
  | { kind: "edge"; id: string }
  | { kind: "branch"; id: string }
  | null;

interface Props {
  document: FlowDefinitionV1;
  selection: Selection;
  readOnly: boolean;
  llms: LlmCatalogOut[];
  tools: ToolCatalogOut[];
  publishedCodes: PublishedFlowCodeOut[];
  onChangeNode: (node: FlowNode) => void;
  onChangeEdge: (edge: FlowEdge) => void;
  onChangeBranch: (branch: FlowBranch) => void;
  onConvertEdge: (edgeId: string) => void;
  onDelete: () => void;
}

const CHANNELS: ChannelName[] = ["messages", "variables", "metadata"];

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

export function Inspector(props: Props): ReactElement {
  const selectedNode =
    props.selection?.kind === "node"
      ? props.document.nodes.find((item) => item.id === props.selection?.id)
      : undefined;
  const selectedEdge =
    props.selection?.kind === "edge"
      ? props.document.edges.find((item) => item.id === props.selection?.id)
      : undefined;
  const selectedBranch =
    props.selection?.kind === "branch"
      ? props.document.branches.find((item) => item.id === props.selection?.id)
      : undefined;

  if (selectedNode !== undefined) {
    return (
      <NodeForm
        node={selectedNode}
        readOnly={props.readOnly}
        llms={props.llms}
        tools={props.tools}
        publishedCodes={props.publishedCodes}
        onChange={props.onChangeNode}
        onDelete={props.onDelete}
      />
    );
  }
  if (selectedEdge !== undefined) {
    return (
      <EdgeForm
        edge={selectedEdge}
        readOnly={props.readOnly}
        onChange={props.onChangeEdge}
        onConvert={() => props.onConvertEdge(selectedEdge.id)}
        onDelete={props.onDelete}
      />
    );
  }
  if (selectedBranch !== undefined) {
    return (
      <BranchForm
        branch={selectedBranch}
        nodeIds={props.document.nodes.map((item) => item.id)}
        readOnly={props.readOnly}
        onChange={props.onChangeBranch}
        onDelete={props.onDelete}
      />
    );
  }
  return <Typography.Text type="secondary">选中节点或连线以编辑属性</Typography.Text>;
}

function NodeForm({
  node,
  readOnly,
  llms,
  tools,
  publishedCodes,
  onChange,
  onDelete,
}: {
  node: FlowNode;
  readOnly: boolean;
  llms: LlmCatalogOut[];
  tools: ToolCatalogOut[];
  publishedCodes: PublishedFlowCodeOut[];
  onChange: (node: FlowNode) => void;
  onDelete: () => void;
}): ReactElement {
  const [form] = Form.useForm<Record<string, unknown>>();

  useEffect(() => {
    form.setFieldsValue({
      title: node.title ?? "",
      llm_ref: node.data.llm_ref ?? "",
      system_prompt: node.data.system_prompt ?? "",
      stream: node.data.stream !== false,
      tool_code: node.data.tool_code ?? "",
      arguments_from: prettyJson(asRecord(node.data.arguments_from)),
      output_to: node.data.output_to ?? "variables.result",
      assignments: JSON.stringify(node.data.assignments ?? [], null, 2),
      prompt_template: node.data.prompt_template ?? "",
      form_schema: prettyJson(asRecord(node.data.form_schema)),
      on_reject: node.data.on_reject ?? "fail",
      flow_code: node.data.flow_code ?? "",
      version: typeof node.data.version === "number" ? node.data.version : undefined,
      input_map: JSON.stringify(node.data.input_map ?? [], null, 2),
      output_map: JSON.stringify(node.data.output_map ?? [], null, 2),
      timeout_seconds:
        typeof node.data.timeout_seconds === "number" ? node.data.timeout_seconds : undefined,
      handler_key: node.data.handler_key ?? "",
      config: prettyJson(asRecord(node.data.config)),
      inject: JSON.stringify(node.data.inject ?? [], null, 2),
      output_channels: node.data.output_channels ?? CHANNELS,
    });
  }, [form, node]);

  const apply = async (): Promise<void> => {
    try {
      const values = await form.validateFields();
      const data = { ...node.data };
      if (node.type === "start") {
        data.inject = JSON.parse(String(values.inject ?? "[]")) as unknown;
      }
      if (node.type === "end") {
        data.output_channels = values.output_channels ?? CHANNELS;
      }
      if (node.type === "llm") {
        data.llm_ref = values.llm_ref;
        data.system_prompt = String(values.system_prompt ?? "") || null;
        data.stream = values.stream !== false;
      }
      if (node.type === "tool") {
        data.tool_code = values.tool_code;
        data.arguments_from = parseObjectJson(String(values.arguments_from ?? "{}"), {});
        data.output_to = values.output_to;
      }
      if (node.type === "assign") {
        data.assignments = JSON.parse(String(values.assignments ?? "[]")) as unknown;
      }
      if (node.type === "hitl") {
        data.prompt_template = values.prompt_template;
        const schemaText = String(values.form_schema ?? "").trim();
        data.form_schema = schemaText === "" ? null : parseObjectJson(schemaText, {});
        data.on_reject = values.on_reject;
      }
      if (node.type === "subgraph") {
        data.flow_code = values.flow_code;
        data.version = values.version === "" || values.version === undefined ? null : values.version;
        data.input_map = JSON.parse(String(values.input_map ?? "[]")) as unknown;
        data.output_map = JSON.parse(String(values.output_map ?? "[]")) as unknown;
        data.timeout_seconds =
          values.timeout_seconds === "" || values.timeout_seconds === undefined
            ? null
            : values.timeout_seconds;
      }
      if (node.type === "custom") {
        data.handler_key = values.handler_key;
        data.config = parseObjectJson(String(values.config ?? "{}"), {});
      }
      const titleRaw = String(values.title ?? "").trim();
      onChange({ ...node, title: titleRaw === "" ? null : titleRaw, data });
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : "属性格式不正确");
    }
  };

  return (
    <Form form={form} layout="vertical" disabled={readOnly} onFinish={() => void apply()}>
      <Typography.Title level={5}>{node.type}</Typography.Title>
      <Form.Item name="title" label="标题">
        <Input />
      </Form.Item>
      {node.type === "start" ? (
        <Form.Item name="inject" label="inject JSON">
          <Input.TextArea rows={6} />
        </Form.Item>
      ) : null}
      {node.type === "end" ? (
        <Form.Item name="output_channels" label="输出槽">
          <Select mode="multiple" options={CHANNELS.map((item) => ({ value: item, label: item }))} />
        </Form.Item>
      ) : null}
      {node.type === "llm" ? (
        <>
          <Form.Item name="llm_ref" label="LLM" rules={[{ required: true }]}>
            <Select
              options={llms.map((item) => ({
                value: item.code,
                label: `${item.code} (${item.model_name})`,
              }))}
              showSearch
            />
          </Form.Item>
          <Form.Item name="system_prompt" label="system_prompt">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="stream" label="stream" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      ) : null}
      {node.type === "tool" ? (
        <>
          <Form.Item name="tool_code" label="工具" rules={[{ required: true }]}>
            <Select
              options={tools.map((item) => ({ value: item.code, label: `${item.code} ${item.name}` }))}
              showSearch
            />
          </Form.Item>
          <Form.Item name="arguments_from" label="arguments_from JSON">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="output_to" label="output_to" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </>
      ) : null}
      {node.type === "assign" ? (
        <Form.Item name="assignments" label="assignments JSON">
          <Input.TextArea rows={6} />
        </Form.Item>
      ) : null}
      {node.type === "hitl" ? (
        <>
          <Form.Item name="prompt_template" label="提示" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="form_schema" label="form_schema JSON">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="on_reject" label="on_reject">
            <Select options={[{ value: "fail" }, { value: "route" }]} />
          </Form.Item>
        </>
      ) : null}
      {node.type === "subgraph" ? (
        <>
          <Form.Item name="flow_code" label="子图 code" rules={[{ required: true }]}>
            <Select
              options={publishedCodes.map((item) => ({
                value: item.code,
                label: `${item.code}@${item.version}`,
              }))}
              showSearch
            />
          </Form.Item>
          <Form.Item name="version" label="version（空=当前 published）">
            <InputNumber style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="input_map" label="input_map JSON">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="output_map" label="output_map JSON">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="timeout_seconds" label="timeout_seconds">
            <InputNumber style={{ width: "100%" }} />
          </Form.Item>
        </>
      ) : null}
      {node.type === "custom" ? (
        <>
          <Form.Item name="handler_key" label="handler_key" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="config" label="config JSON">
            <Input.TextArea rows={4} />
          </Form.Item>
        </>
      ) : null}
      {readOnly ? null : (
        <>
          <Button type="primary" htmlType="submit" block>
            应用属性
          </Button>
          {node.type !== "start" ? (
            <Button danger style={{ marginTop: 8 }} block onClick={onDelete}>
              删除节点
            </Button>
          ) : null}
        </>
      )}
    </Form>
  );
}

function EdgeForm({
  edge,
  readOnly,
  onChange,
  onConvert,
  onDelete,
}: {
  edge: FlowEdge;
  readOnly: boolean;
  onChange: (edge: FlowEdge) => void;
  onConvert: () => void;
  onDelete: () => void;
}): ReactElement {
  const [form] = Form.useForm<{ label: string }>();
  useEffect(() => {
    form.setFieldsValue({ label: edge.label ?? "" });
  }, [edge, form]);
  return (
    <Form
      form={form}
      layout="vertical"
      disabled={readOnly}
      onFinish={(values) => {
        const label = values.label.trim();
        onChange({ ...edge, label: label === "" ? null : label });
      }}
    >
      <Typography.Title level={5}>无条件边</Typography.Title>
      <Form.Item name="label" label="标签">
        <Input />
      </Form.Item>
      {readOnly ? null : (
        <>
          <Button type="primary" htmlType="submit" block>
            应用
          </Button>
          <Button style={{ marginTop: 8 }} block onClick={onConvert}>
            转为条件分支
          </Button>
          <Button danger style={{ marginTop: 8 }} block onClick={onDelete}>
            删除连线
          </Button>
        </>
      )}
    </Form>
  );
}

function BranchForm({
  branch,
  nodeIds,
  readOnly,
  onChange,
  onDelete,
}: {
  branch: FlowBranch;
  nodeIds: string[];
  readOnly: boolean;
  onChange: (branch: FlowBranch) => void;
  onDelete: () => void;
}): ReactElement {
  const [form] = Form.useForm<{
    kind: FlowBranch["router"]["kind"];
    path: string;
    expr: string;
    cases: string;
    default_target: string | null;
    max_visits: number | null;
  }>();
  useEffect(() => {
    form.setFieldsValue({
      kind: branch.router.kind,
      path: branch.router.path ?? "",
      expr: branch.router.expr ?? "",
      cases: JSON.stringify(branch.cases, null, 2),
      default_target: branch.default_target,
      max_visits: branch.max_visits,
    });
  }, [branch, form]);
  const targets = nodeIds.map((id) => ({ value: id, label: id }));
  return (
    <Form
      form={form}
      layout="vertical"
      disabled={readOnly}
      onFinish={(values) => {
        try {
          onChange({
            ...branch,
            router: {
              kind: values.kind,
              path: values.path.trim() === "" ? null : values.path.trim(),
              expr: values.expr.trim() === "" ? null : values.expr.trim(),
            },
            cases: JSON.parse(values.cases) as FlowBranch["cases"],
            default_target: values.default_target || null,
            max_visits: values.max_visits ?? null,
          });
        } catch (err: unknown) {
          message.error(err instanceof Error ? err.message : "cases JSON 不正确");
        }
      }}
    >
      <Typography.Title level={5}>条件分支</Typography.Title>
      <Form.Item name="kind" label="router.kind">
        <Select
          options={[
            { value: "state_path" },
            { value: "expr" },
            { value: "hitl_decision" },
            { value: "child_status" },
          ]}
        />
      </Form.Item>
      <Form.Item name="path" label="path">
        <Input />
      </Form.Item>
      <Form.Item name="expr" label="expr">
        <Input />
      </Form.Item>
      <Form.Item name="cases" label="cases JSON">
        <Input.TextArea rows={6} />
      </Form.Item>
      <Form.Item name="default_target" label="default_target">
        <Select allowClear options={targets} />
      </Form.Item>
      <Form.Item name="max_visits" label="max_visits">
        <InputNumber style={{ width: "100%" }} />
      </Form.Item>
      {readOnly ? null : (
        <>
          <Button type="primary" htmlType="submit" block>
            应用
          </Button>
          <Button danger style={{ marginTop: 8 }} block onClick={onDelete}>
            删除分支
          </Button>
        </>
      )}
    </Form>
  );
}
