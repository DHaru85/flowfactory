import { Select, Table, Typography, message } from "antd";
import { useCallback, useEffect, useState, type ReactElement } from "react";

import { errorMessage } from "@/api/client";
import { listUsers, patchUserStatus } from "@/api/auth";
import { useSession } from "@/auth/context";
import type { UserAccountOut, UserAccountStatus } from "@/types";

export function UsersPage(): ReactElement {
  const { me } = useSession();
  const [rows, setRows] = useState<UserAccountOut[]>([]);

  const reload = useCallback(async () => {
    setRows(await listUsers());
  }, []);

  useEffect(() => {
    void reload().catch((err: unknown) => message.error(errorMessage(err, "加载用户失败")));
  }, [reload]);

  const changeStatus = async (row: UserAccountOut, status: UserAccountStatus): Promise<void> => {
    await patchUserStatus(row.id, status);
    await reload();
    message.success("已更新授权状态");
  };

  return (
    <>
      <Typography.Title level={4}>用户授权</Typography.Title>
      <Typography.Paragraph type="secondary">
        不可删除用户账号。可在权限范围内停用或封禁授权；停用后无法登录。
      </Typography.Paragraph>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "用户名", dataIndex: "username" },
          { title: "显示名", dataIndex: "display_name" },
          {
            title: "状态",
            dataIndex: "status",
            width: 200,
            render: (_: unknown, row: UserAccountOut) => {
              const locked = row.id === me?.id || (row.is_superuser && me?.is_superuser !== true);
              return (
                <Select
                  value={row.status}
                  style={{ width: 140 }}
                  disabled={locked}
                  onChange={(value: UserAccountStatus) => {
                    void changeStatus(row, value).catch((err: unknown) =>
                      message.error(errorMessage(err, "更新失败")),
                    );
                  }}
                  options={[
                    { value: "active", label: "启用" },
                    { value: "disabled", label: "停用" },
                    { value: "banned", label: "封禁" },
                  ]}
                />
              );
            },
          },
          {
            title: "超管",
            dataIndex: "is_superuser",
            width: 80,
            render: (value: boolean) => (value ? "是" : "否"),
          },
        ]}
      />
    </>
  );
}
