import { Button, Form, Input, Select, Space, Table } from "antd";
import { useEffect, type ReactElement } from "react";

import type { BindingItem, SubjectType } from "@/types";

const SUBJECTS: { value: SubjectType; label: string }[] = [
  { value: "organization", label: "组织" },
  { value: "department", label: "部门" },
  { value: "role", label: "角色" },
  { value: "user", label: "用户" },
];

const ACTIONS = ["read", "use", "write", "admin"];

interface Props {
  value: BindingItem[];
  onChange: (rows: BindingItem[]) => void;
  disabled: boolean;
}

export function BindingEditor({ value, onChange, disabled }: Props): ReactElement {
  const [form] = Form.useForm<{ subject_type: SubjectType; subject_id: string; actions: string[] }>();

  useEffect(() => {
    form.setFieldsValue({ subject_type: "user", actions: ["read", "use"] });
  }, [form]);

  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      {disabled ? null : (
        <Form
          form={form}
          layout="inline"
          onFinish={(row) => {
            onChange([
              ...value,
              {
                subject_type: row.subject_type,
                subject_id: row.subject_id.trim(),
                actions: row.actions,
              },
            ]);
            form.setFieldsValue({ subject_id: "" });
          }}
        >
          <Form.Item name="subject_type" rules={[{ required: true }]}>
            <Select style={{ width: 120 }} options={SUBJECTS} />
          </Form.Item>
          <Form.Item name="subject_id" rules={[{ required: true, message: "主体 UUID" }]}>
            <Input placeholder="主体 UUID" style={{ width: 280 }} />
          </Form.Item>
          <Form.Item name="actions" rules={[{ required: true }]}>
            <Select mode="multiple" style={{ width: 220 }} options={ACTIONS.map((a) => ({ value: a, label: a }))} />
          </Form.Item>
          <Button htmlType="submit">添加</Button>
        </Form>
      )}
      <Table
        size="small"
        rowKey={(row) => `${row.subject_type}:${row.subject_id}`}
        dataSource={value}
        pagination={false}
        columns={[
          { title: "主体类型", dataIndex: "subject_type" },
          { title: "主体 id", dataIndex: "subject_id" },
          { title: "actions", dataIndex: "actions", render: (acts: string[]) => acts.join(", ") },
          {
            title: "",
            render: (_: unknown, _row: BindingItem, index: number) =>
              disabled ? null : (
                <Button
                  type="link"
                  danger
                  onClick={() => onChange(value.filter((_, i) => i !== index))}
                >
                  移除
                </Button>
              ),
          },
        ]}
      />
    </Space>
  );
}
