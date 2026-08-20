import { Button, Input, Space, Table, Typography, message } from "antd";
import { useCallback, useEffect, useState, type ReactElement } from "react";
import { Link } from "react-router-dom";

import { errorMessage } from "@/api/client";
import { listHitlPendings, resumeHitl } from "@/api/conversations";
import type { HitlPendingOut } from "@/types";

export function HitlInboxPage(): ReactElement {
  const [rows, setRows] = useState<HitlPendingOut[]>([]);
  const [input, setInput] = useState("");

  const reload = useCallback(async () => {
    setRows(await listHitlPendings());
  }, []);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载待办失败")));
  }, [reload]);

  const act = async (row: HitlPendingOut, decision: "approve" | "reject"): Promise<void> => {
    await resumeHitl(row.id, { decision, user_input: input.trim() === "" ? null : input.trim() });
    setInput("");
    await reload();
    message.success(decision === "approve" ? "已批准" : "已拒绝");
  };

  return (
    <>
      <Typography.Title level={4}>HITL 待办</Typography.Title>
      <Input.TextArea
        rows={3}
        value={input}
        onChange={(ev) => setInput(ev.target.value)}
        placeholder="可选 user_input / 表单 JSON"
        style={{ marginBottom: 12 }}
      />
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "节点", dataIndex: "node_id", width: 120 },
          { title: "说明", dataIndex: "prompt" },
          {
            title: "会话",
            render: (_: unknown, row: HitlPendingOut) =>
              row.conversation_id ? (
                <Link to="/workflow">{row.conversation_id.slice(0, 8)}</Link>
              ) : (
                "—"
              ),
          },
          {
            title: "操作",
            render: (_: unknown, row: HitlPendingOut) => (
              <Space>
                <Button type="primary" size="small" onClick={() => void act(row, "approve").catch((err: unknown) => message.error(errorMessage(err, "恢复失败")))}>
                  批准
                </Button>
                <Button danger size="small" onClick={() => void act(row, "reject").catch((err: unknown) => message.error(errorMessage(err, "恢复失败")))}>
                  拒绝
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </>
  );
}
