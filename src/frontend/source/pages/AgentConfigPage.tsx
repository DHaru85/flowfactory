import { Button, Form, Input, Modal, Radio, Select, Space, Switch, Table, Tabs, message } from "antd";
import { useCallback, useEffect, useState, type ReactElement } from "react";

import {
  createBeat,
  createMcp,
  createProfile,
  createSkill,
  createTool,
  disableBeat,
  enableBeat,
  getBindings,
  listBeats,
  listMcps,
  listProfiles,
  listSkills,
  listTools,
  patchBeat,
  patchMcp,
  patchProfile,
  patchSkill,
  patchTool,
  putBindings,
  type ConfigResource,
} from "@/api/agentConfig";
import { errorMessage } from "@/api/client";
import { listLlms } from "@/api/models";
import { findApp, useSession } from "@/auth/context";
import { BindingEditor } from "@/components/BindingEditor";
import { parseObjectJson, prettyJson } from "@/lib/json";
import type { BeatOut, BindingItem, LlmOut, McpOut, ProfileOut, SkillOut, ToolKind, ToolOut } from "@/types";

export function AgentConfigPage(): ReactElement {
  const { apps } = useSession();
  const canControl = findApp(apps, "agent_config")?.can_control === true;
  return (
    <Tabs
      items={[
        { key: "profiles", label: "Profile", children: <ProfilesTab canControl={canControl} /> },
        { key: "skills", label: "Skill", children: <SkillsTab canControl={canControl} /> },
        { key: "tools", label: "Tool", children: <ToolsTab canControl={canControl} /> },
        { key: "mcp", label: "MCP", children: <McpTab canControl={canControl} /> },
        { key: "beat", label: "Beat", children: <BeatTab canControl={canControl} /> },
      ]}
    />
  );
}

function BindingsModal(props: {
  open: boolean;
  kind: ConfigResource;
  id: string | null;
  canControl: boolean;
  onClose: () => void;
}): ReactElement {
  const [rows, setRows] = useState<BindingItem[]>([]);
  useEffect(() => {
    if (!props.open || props.id === null) {
      return;
    }
    void getBindings(props.kind, props.id)
      .then(setRows)
      .catch((err: unknown) => message.error(errorMessage(err, "加载绑定失败")));
  }, [props.open, props.kind, props.id]);

  return (
    <Modal
      title="绑定"
      open={props.open}
      width={800}
      onCancel={props.onClose}
      onOk={() => {
        if (props.id === null) {
          return;
        }
        void putBindings(props.kind, props.id, { bindings: rows })
          .then(() => {
            message.success("已保存");
            props.onClose();
          })
          .catch((err: unknown) => message.error(errorMessage(err, "保存绑定失败")));
      }}
      okButtonProps={{ disabled: !props.canControl }}
    >
      <BindingEditor value={rows} onChange={setRows} disabled={!props.canControl} />
    </Modal>
  );
}

function ProfilesTab({ canControl }: { canControl: boolean }): ReactElement {
  const [rows, setRows] = useState<ProfileOut[]>([]);
  const [llms, setLlms] = useState<LlmOut[]>([]);
  const [skills, setSkills] = useState<SkillOut[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ProfileOut | null>(null);
  const [bindId, setBindId] = useState<string | null>(null);
  const [form] = Form.useForm<{
    code: string;
    name: string;
    system_prompt: string;
    default_llm_id: string | null;
    skill_ids: string[];
  }>();

  const reload = useCallback(async () => {
    const [p, l, s] = await Promise.all([listProfiles(), listLlms().catch(() => []), listSkills()]);
    setRows(p);
    setLlms(l);
    setSkills(s);
  }, []);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载失败")));
  }, [reload]);

  return (
    <>
      {canControl ? (
        <Button
          type="primary"
          style={{ marginBottom: 16 }}
          onClick={() => {
            setEditing(null);
            form.resetFields();
            form.setFieldsValue({ skill_ids: [], default_llm_id: null });
            setOpen(true);
          }}
        >
          新建
        </Button>
      ) : null}
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "code", dataIndex: "code" },
          { title: "name", dataIndex: "name" },
          {
            title: "操作",
            render: (_: unknown, row: ProfileOut) => (
              <Space>
                {canControl ? (
                  <Button
                    type="link"
                    onClick={() => {
                      setEditing(row);
                      form.setFieldsValue({
                        code: row.code,
                        name: row.name,
                        system_prompt: row.system_prompt,
                        default_llm_id: row.default_llm_id,
                        skill_ids: row.skill_ids,
                      });
                      setOpen(true);
                    }}
                  >
                    编辑
                  </Button>
                ) : null}
                <Button type="link" onClick={() => setBindId(row.id)}>
                  绑定
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? "编辑 Profile" : "新建 Profile"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => {
          void form.validateFields().then(async (values) => {
            try {
              if (editing) {
                await patchProfile(editing.id, {
                  name: values.name,
                  system_prompt: values.system_prompt,
                  default_llm_id: values.default_llm_id,
                  skill_ids: values.skill_ids,
                });
              } else {
                await createProfile(values);
              }
              setOpen(false);
              await reload();
            } catch (err) {
              message.error(errorMessage(err, "保存失败"));
            }
          });
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="code" rules={[{ required: true }]}>
            <Input disabled={editing !== null} />
          </Form.Item>
          <Form.Item name="name" label="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="system_prompt" label="system_prompt" rules={[{ required: true }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="default_llm_id" label="默认 LLM">
            <Select allowClear options={llms.map((item) => ({ value: item.id, label: item.code }))} />
          </Form.Item>
          <Form.Item name="skill_ids" label="技能">
            <Select mode="multiple" options={skills.map((item) => ({ value: item.id, label: item.code }))} />
          </Form.Item>
        </Form>
      </Modal>
      <BindingsModal
        open={bindId !== null}
        kind="profiles"
        id={bindId}
        canControl={canControl}
        onClose={() => setBindId(null)}
      />
    </>
  );
}

function SkillsTab({ canControl }: { canControl: boolean }): ReactElement {
  const [rows, setRows] = useState<SkillOut[]>([]);
  const [tools, setTools] = useState<ToolOut[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<SkillOut | null>(null);
  const [bindId, setBindId] = useState<string | null>(null);
  const [form] = Form.useForm<{
    code: string;
    name: string;
    description: string | null;
    tool_ids: string[];
    prompt_template: string | null;
  }>();

  const reload = useCallback(async () => {
    const [s, t] = await Promise.all([listSkills(), listTools()]);
    setRows(s);
    setTools(t);
  }, []);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载失败")));
  }, [reload]);

  return (
    <>
      {canControl ? (
        <Button
          type="primary"
          style={{ marginBottom: 16 }}
          onClick={() => {
            setEditing(null);
            form.resetFields();
            form.setFieldsValue({ tool_ids: [] });
            setOpen(true);
          }}
        >
          新建
        </Button>
      ) : null}
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "code", dataIndex: "code" },
          { title: "name", dataIndex: "name" },
          {
            title: "操作",
            render: (_: unknown, row: SkillOut) => (
              <Space>
                {canControl ? (
                  <Button
                    type="link"
                    onClick={() => {
                      setEditing(row);
                      form.setFieldsValue(row);
                      setOpen(true);
                    }}
                  >
                    编辑
                  </Button>
                ) : null}
                <Button type="link" onClick={() => setBindId(row.id)}>
                  绑定
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? "编辑 Skill" : "新建 Skill"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => {
          void form.validateFields().then(async (values) => {
            try {
              if (editing) {
                await patchSkill(editing.id, values);
              } else {
                await createSkill(values);
              }
              setOpen(false);
              await reload();
            } catch (err) {
              message.error(errorMessage(err, "保存失败"));
            }
          });
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="code" rules={[{ required: true }]}>
            <Input disabled={editing !== null} />
          </Form.Item>
          <Form.Item name="name" label="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="description">
            <Input.TextArea />
          </Form.Item>
          <Form.Item name="prompt_template" label="prompt_template">
            <Input.TextArea />
          </Form.Item>
          <Form.Item name="tool_ids" label="工具">
            <Select mode="multiple" options={tools.map((item) => ({ value: item.id, label: item.code }))} />
          </Form.Item>
        </Form>
      </Modal>
      <BindingsModal
        open={bindId !== null}
        kind="skills"
        id={bindId}
        canControl={canControl}
        onClose={() => setBindId(null)}
      />
    </>
  );
}

function ToolsTab({ canControl }: { canControl: boolean }): ReactElement {
  const [rows, setRows] = useState<ToolOut[]>([]);
  const [mcps, setMcps] = useState<McpOut[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ToolOut | null>(null);
  const [bindId, setBindId] = useState<string | null>(null);
  const [form] = Form.useForm<{
    code: string;
    name: string;
    kind: ToolKind;
    schemaText: string;
    configText: string;
    mcp_server_id: string | null;
  }>();

  const reload = useCallback(async () => {
    const [t, m] = await Promise.all([listTools(), listMcps()]);
    setRows(t);
    setMcps(m);
  }, []);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载失败")));
  }, [reload]);

  return (
    <>
      {canControl ? (
        <Button
          type="primary"
          style={{ marginBottom: 16 }}
          onClick={() => {
            setEditing(null);
            form.resetFields();
            form.setFieldsValue({ kind: "builtin", schemaText: "{}", configText: "{}" });
            setOpen(true);
          }}
        >
          新建
        </Button>
      ) : null}
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "code", dataIndex: "code" },
          { title: "name", dataIndex: "name" },
          { title: "kind", dataIndex: "kind" },
          {
            title: "操作",
            render: (_: unknown, row: ToolOut) => (
              <Space>
                {canControl ? (
                  <Button
                    type="link"
                    onClick={() => {
                      setEditing(row);
                      form.setFieldsValue({
                        code: row.code,
                        name: row.name,
                        kind: row.kind,
                        schemaText: prettyJson(row.schema ?? {}),
                        configText: prettyJson(row.config),
                        mcp_server_id: row.mcp_server_id,
                      });
                      setOpen(true);
                    }}
                  >
                    编辑
                  </Button>
                ) : null}
                <Button type="link" onClick={() => setBindId(row.id)}>
                  绑定
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? "编辑 Tool" : "新建 Tool"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => {
          void form.validateFields().then(async (values) => {
            try {
              const schema = parseObjectJson(values.schemaText, {});
              const config = parseObjectJson(values.configText, {});
              if (editing) {
                await patchTool(editing.id, {
                  name: values.name,
                  kind: values.kind,
                  schema,
                  config,
                  mcp_server_id: values.mcp_server_id,
                });
              } else {
                await createTool({
                  code: values.code,
                  name: values.name,
                  kind: values.kind,
                  schema,
                  config,
                  mcp_server_id: values.mcp_server_id ?? null,
                });
              }
              setOpen(false);
              await reload();
            } catch (err) {
              message.error(errorMessage(err, "保存失败"));
            }
          });
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="code" rules={[{ required: true }]}>
            <Input disabled={editing !== null} />
          </Form.Item>
          <Form.Item name="name" label="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="kind" label="kind" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "builtin", label: "builtin" },
                { value: "http", label: "http" },
                { value: "mcp", label: "mcp" },
              ]}
            />
          </Form.Item>
          <Form.Item name="schemaText" label="schema">
            <Input.TextArea rows={6} />
          </Form.Item>
          <Form.Item name="configText" label="config">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="mcp_server_id" label="MCP Server">
            <Select allowClear options={mcps.map((item) => ({ value: item.id, label: item.code }))} />
          </Form.Item>
        </Form>
      </Modal>
      <BindingsModal
        open={bindId !== null}
        kind="tools"
        id={bindId}
        canControl={canControl}
        onClose={() => setBindId(null)}
      />
    </>
  );
}

function McpTab({ canControl }: { canControl: boolean }): ReactElement {
  const [rows, setRows] = useState<McpOut[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<McpOut | null>(null);
  const [bindId, setBindId] = useState<string | null>(null);
  const [form] = Form.useForm<{
    code: string;
    name: string;
    transport: "stdio" | "sse";
    configText: string;
    is_active: boolean;
  }>();

  const reload = useCallback(async () => {
    setRows(await listMcps());
  }, []);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载失败")));
  }, [reload]);

  return (
    <>
      {canControl ? (
        <Button
          type="primary"
          style={{ marginBottom: 16 }}
          onClick={() => {
            setEditing(null);
            form.resetFields();
            form.setFieldsValue({ transport: "sse", configText: "{}", is_active: true });
            setOpen(true);
          }}
        >
          新建
        </Button>
      ) : null}
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "code", dataIndex: "code" },
          { title: "name", dataIndex: "name" },
          { title: "transport", dataIndex: "transport" },
          {
            title: "操作",
            render: (_: unknown, row: McpOut) => (
              <Space>
                {canControl ? (
                  <Button
                    type="link"
                    onClick={() => {
                      setEditing(row);
                      form.setFieldsValue({
                        code: row.code,
                        name: row.name,
                        transport: row.transport,
                        configText: prettyJson(row.config),
                        is_active: row.is_active,
                      });
                      setOpen(true);
                    }}
                  >
                    编辑
                  </Button>
                ) : null}
                <Button type="link" onClick={() => setBindId(row.id)}>
                  绑定
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? "编辑 MCP" : "新建 MCP"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => {
          void form.validateFields().then(async (values) => {
            try {
              const config = parseObjectJson(values.configText, {});
              if (editing) {
                await patchMcp(editing.id, {
                  name: values.name,
                  transport: values.transport,
                  config,
                  is_active: values.is_active,
                });
              } else {
                await createMcp({
                  code: values.code,
                  name: values.name,
                  transport: values.transport,
                  config,
                  is_active: values.is_active,
                });
              }
              setOpen(false);
              await reload();
            } catch (err) {
              message.error(errorMessage(err, "保存失败"));
            }
          });
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="code" rules={[{ required: true }]}>
            <Input disabled={editing !== null} />
          </Form.Item>
          <Form.Item name="name" label="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="transport" label="transport">
            <Select
              options={[
                { value: "stdio", label: "stdio" },
                { value: "sse", label: "sse" },
              ]}
            />
          </Form.Item>
          <Form.Item name="configText" label="config">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
      <BindingsModal
        open={bindId !== null}
        kind="mcp-servers"
        id={bindId}
        canControl={canControl}
        onClose={() => setBindId(null)}
      />
    </>
  );
}

function BeatTab({ canControl }: { canControl: boolean }): ReactElement {
  const [rows, setRows] = useState<BeatOut[]>([]);
  const [profiles, setProfiles] = useState<ProfileOut[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<BeatOut | null>(null);
  const [form] = Form.useForm<{
    code: string;
    mode: "workflow" | "planner";
    flow_id: string | null;
    profile_id: string | null;
    cron: string;
    payloadText: string;
    is_enabled: boolean;
  }>();

  const reload = useCallback(async () => {
    const [b, p] = await Promise.all([listBeats(), listProfiles().catch(() => [])]);
    setRows(b);
    setProfiles(p);
  }, []);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载失败")));
  }, [reload]);

  return (
    <>
      {canControl ? (
        <Button
          type="primary"
          style={{ marginBottom: 16 }}
          onClick={() => {
            setEditing(null);
            form.resetFields();
            form.setFieldsValue({
              mode: "planner",
              cron: "0 * * * *",
              payloadText: "{}",
              is_enabled: true,
            });
            setOpen(true);
          }}
        >
          新建
        </Button>
      ) : null}
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "code", dataIndex: "code" },
          { title: "cron", dataIndex: "cron" },
          {
            title: "目标",
            render: (_: unknown, row: BeatOut) =>
              row.profile_id ? `profile ${row.profile_id}` : `flow ${row.flow_id ?? ""}`,
          },
          { title: "启用", dataIndex: "is_enabled", render: (v: boolean) => (v ? "是" : "否") },
          {
            title: "操作",
            render: (_: unknown, row: BeatOut) =>
              canControl ? (
                <Space>
                  <Button
                    type="link"
                    onClick={() => {
                      setEditing(row);
                      form.setFieldsValue({
                        code: row.code,
                        mode: row.profile_id ? "planner" : "workflow",
                        flow_id: row.flow_id,
                        profile_id: row.profile_id,
                        cron: row.cron,
                        payloadText: prettyJson(row.input_payload),
                        is_enabled: row.is_enabled,
                      });
                      setOpen(true);
                    }}
                  >
                    编辑
                  </Button>
                  <Button
                    type="link"
                    onClick={() => {
                      void (row.is_enabled ? disableBeat(row.id) : enableBeat(row.id))
                        .then(reload)
                        .catch((err: unknown) => message.error(errorMessage(err, "切换失败")));
                    }}
                  >
                    {row.is_enabled ? "停用" : "启用"}
                  </Button>
                </Space>
              ) : null,
          },
        ]}
      />
      <Modal
        title={editing ? "编辑 Beat" : "新建 Beat"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => {
          void form.validateFields().then(async (values) => {
            try {
              const input_payload = parseObjectJson(values.payloadText, {});
              if (editing) {
                await patchBeat(editing.id, { cron: values.cron, input_payload });
              } else {
                await createBeat({
                  code: values.code,
                  flow_id: values.mode === "workflow" ? values.flow_id : null,
                  profile_id: values.mode === "planner" ? values.profile_id : null,
                  cron: values.cron,
                  input_payload,
                  is_enabled: values.is_enabled,
                });
              }
              setOpen(false);
              await reload();
            } catch (err) {
              message.error(errorMessage(err, "保存失败"));
            }
          });
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="code" rules={[{ required: true }]}>
            <Input disabled={editing !== null} />
          </Form.Item>
          <Form.Item name="mode" label="类型">
            <Radio.Group disabled={editing !== null}>
              <Radio.Button value="planner">规划</Radio.Button>
              <Radio.Button value="workflow">工作流</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item noStyle shouldUpdate>
            {(ctx) =>
              ctx.getFieldValue("mode") === "planner" ? (
                <Form.Item name="profile_id" label="Profile" rules={[{ required: editing === null }]}>
                  <Select
                    disabled={editing !== null}
                    options={profiles.map((item) => ({ value: item.id, label: item.code }))}
                  />
                </Form.Item>
              ) : (
                <Form.Item name="flow_id" label="Flow UUID" rules={[{ required: editing === null }]}>
                  <Input disabled={editing !== null} />
                </Form.Item>
              )
            }
          </Form.Item>
          <Form.Item name="cron" label="cron" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="payloadText" label="input_payload">
            <Input.TextArea rows={4} />
          </Form.Item>
          {editing ? null : (
            <Form.Item name="is_enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  );
}
