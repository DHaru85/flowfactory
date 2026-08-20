import { Button, Form, Input, Modal, Select, Space, Table, Tag, message } from "antd";
import axios from "axios";
import { useCallback, useEffect, useState, type ReactElement } from "react";
import { Link, useNavigate } from "react-router-dom";

import { errorMessage } from "@/api/client";
import { createStudioFlow, listStudioFlows, listStudioProfiles, newStudioDraft } from "@/api/studio";
import { findApp, useSession } from "@/auth/context";
import type { FlowOut, FlowStatus, ProfileCatalogOut } from "@/types";

export function StudioListPage(): ReactElement {
  const { apps } = useSession();
  const canControl = findApp(apps, "studio")?.can_control === true;
  const navigate = useNavigate();
  const [rows, setRows] = useState<FlowOut[]>([]);
  const [profiles, setProfiles] = useState<ProfileCatalogOut[]>([]);
  const [status, setStatus] = useState<FlowStatus | "all">("all");
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<{ code: string; name: string; profile_id: string }>();

  const reload = useCallback(async () => {
    setRows(await listStudioFlows(status === "all" ? undefined : status));
  }, [status]);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载 Flow 失败")));
  }, [reload]);

  useEffect(() => {
    void listStudioProfiles()
      .then(setProfiles)
      .catch((err: unknown) => message.error(errorMessage(err, "加载 Profile 失败")));
  }, []);

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Select
          value={status}
          style={{ width: 160 }}
          onChange={(value: FlowStatus | "all") => setStatus(value)}
          options={[
            { value: "all", label: "全部状态" },
            { value: "draft", label: "draft" },
            { value: "published", label: "published" },
            { value: "archived", label: "archived" },
          ]}
        />
        {canControl ? (
          <Button type="primary" onClick={() => setOpen(true)}>
            新建草稿
          </Button>
        ) : null}
      </Space>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "code", dataIndex: "code" },
          { title: "name", dataIndex: "name" },
          { title: "version", dataIndex: "version", width: 90 },
          {
            title: "状态",
            dataIndex: "status",
            render: (value: FlowStatus) => <Tag>{value}</Tag>,
          },
          {
            title: "操作",
            render: (_: unknown, row: FlowOut) => (
              <Space>
                <Link to={`/studio/${row.id}`}>打开</Link>
                {canControl && row.status === "published" ? (
                  <Button
                    type="link"
                    onClick={() => {
                      void newStudioDraft(row.id)
                        .then((created) => navigate(`/studio/${created.id}`))
                        .catch((err: unknown) => message.error(errorMessage(err, "开新草稿失败")));
                    }}
                  >
                    新草稿
                  </Button>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title="新建 Flow 草稿"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => {
          void form.validateFields().then(async (values) => {
            const created = await createStudioFlow({
              code: values.code,
              name: values.name,
              profile_id: values.profile_id,
              definition: null,
            });
            setOpen(false);
            navigate(`/studio/${created.id}`);
          }).catch((err: unknown) => {
            if (axios.isAxiosError(err)) {
              message.error(errorMessage(err, "创建失败"));
            }
          });
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="code" rules={[{ required: true, message: "必填" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "必填" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="profile_id" label="Profile" rules={[{ required: true, message: "必填" }]}>
            <Select
              options={profiles.map((item) => ({
                value: item.id,
                label: `${item.code} ${item.name}`,
              }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
