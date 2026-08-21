import { Button, Form, Input, Modal, Select, Space, Switch, Table, Tag, message } from "antd";
import { useCallback, useEffect, useState, type ReactElement } from "react";

import { errorMessage } from "@/api/client";
import { createLlm, deactivateLlm, deleteLlm, listLlms, patchLlm } from "@/api/models";
import { ConfirmDelete } from "@/components/ConfirmDelete";
import { findApp, useSession } from "@/auth/context";
import { parseObjectJson, prettyJson } from "@/lib/json";
import type { LlmOut } from "@/types";

interface LlmFormValues {
  code: string;
  provider: string;
  model_name: string;
  configText: string;
  api_key: string;
  is_active: boolean;
}

export function ModelsPage(): ReactElement {
  const { apps } = useSession();
  const canControl = findApp(apps, "models")?.can_control === true;
  const [rows, setRows] = useState<LlmOut[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<LlmOut | null>(null);
  const [form] = Form.useForm<LlmFormValues>();

  const reload = useCallback(async () => {
    setRows(await listLlms());
  }, []);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载失败")));
  }, [reload]);

  const openCreate = (): void => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      provider: "openai",
      is_active: true,
      configText: "{}",
      api_key: "",
    });
    setOpen(true);
  };

  const openEdit = (row: LlmOut): void => {
    setEditing(row);
    form.setFieldsValue({
      code: row.code,
      provider: row.provider,
      model_name: row.model_name,
      is_active: row.is_active,
      configText: prettyJson(row.config),
      api_key: "",
    });
    setOpen(true);
  };

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        {canControl ? (
          <Button type="primary" onClick={openCreate}>
            新建模型
          </Button>
        ) : null}
      </Space>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "code", dataIndex: "code" },
          { title: "provider", dataIndex: "provider" },
          { title: "model", dataIndex: "model_name" },
          {
            title: "密钥",
            render: (_: unknown, row: LlmOut) =>
              row.has_api_key ? <Tag color="green">已配置</Tag> : <Tag>未配置</Tag>,
          },
          {
            title: "状态",
            render: (_: unknown, row: LlmOut) => (row.is_active ? "启用" : "停用"),
          },
          {
            title: "操作",
            render: (_: unknown, row: LlmOut) =>
              canControl ? (
                <Space>
                  <Button type="link" onClick={() => openEdit(row)}>
                    编辑
                  </Button>
                  {row.is_active ? (
                    <Button
                      type="link"
                      danger
                      onClick={() => {
                        void deactivateLlm(row.id)
                          .then(reload)
                          .catch((err: unknown) => message.error(errorMessage(err, "停用失败")));
                      }}
                    >
                      停用
                    </Button>
                  ) : null}
                  <ConfirmDelete
                    onConfirm={async () => {
                      await deleteLlm(row.id);
                      await reload();
                    }}
                  />
                </Space>
              ) : null,
          },
        ]}
      />
      <Modal
        title={editing ? "编辑模型" : "新建模型"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => {
          void form.validateFields().then(async (values) => {
            try {
              const config = parseObjectJson(values.configText, {});
              if (values.api_key.trim() !== "") {
                config.api_key = values.api_key;
              }
              if (editing) {
                const patch: {
                  provider: string;
                  model_name: string;
                  is_active: boolean;
                  config?: Record<string, unknown>;
                } = {
                  provider: values.provider,
                  model_name: values.model_name,
                  is_active: values.is_active,
                };
                if (values.api_key.trim() !== "" || values.configText.trim() !== prettyJson(editing.config)) {
                  patch.config = config;
                }
                await patchLlm(editing.id, patch);
              } else {
                await createLlm({
                  code: values.code,
                  provider: values.provider,
                  model_name: values.model_name,
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
          <Form.Item name="provider" label="provider" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "openai", label: "openai" },
                { value: "azure", label: "azure" },
                { value: "local", label: "local" },
              ]}
            />
          </Form.Item>
          <Form.Item name="model_name" label="model_name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="configText" label="config（不含密钥）">
            <Input.TextArea rows={6} />
          </Form.Item>
          <Form.Item
            name="api_key"
            label={editing?.has_api_key ? "api_key（留空则不覆盖已有密钥）" : "api_key"}
          >
            <Input.Password autoComplete="new-password" placeholder="只写不回显" />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
