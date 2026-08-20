import {
  AuditOutlined,
  ApiOutlined,
  ApartmentOutlined,
  CommentOutlined,
  DeploymentUnitOutlined,
  LogoutOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Typography } from "antd";
import { useMemo, type ReactElement, type ReactNode } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { logout } from "@/api/auth";
import { findApp, useSession } from "@/auth/context";

export function AppShell(): ReactElement {
  const { me, apps } = useSession();
  const location = useLocation();
  const navigate = useNavigate();

  const items = useMemo(() => {
    const conv = findApp(apps, "conversation");
    const result: { key: string; icon: ReactNode; label: ReactNode }[] = [];
    if (conv?.can_use) {
      result.push({
        key: "/planner",
        icon: <RobotOutlined />,
        label: <Link to="/planner">规划会话</Link>,
      });
      result.push({
        key: "/workflow",
        icon: <CommentOutlined />,
        label: <Link to="/workflow">工作流会话</Link>,
      });
      result.push({
        key: "/hitl",
        icon: <AuditOutlined />,
        label: <Link to="/hitl">HITL 待办</Link>,
      });
    }
    if (findApp(apps, "studio")?.can_use) {
      result.push({
        key: "/studio",
        icon: <ApartmentOutlined />,
        label: <Link to="/studio">Studio</Link>,
      });
    }
    if (findApp(apps, "models")?.can_use) {
      result.push({
        key: "/models",
        icon: <ApiOutlined />,
        label: <Link to="/models">模型</Link>,
      });
    }
    if (findApp(apps, "agent_config")?.can_use) {
      result.push({
        key: "/agent-config",
        icon: <DeploymentUnitOutlined />,
        label: <Link to="/agent-config">Agent 配置</Link>,
      });
    }
    return result;
  }, [apps]);

  const selected = items.find((item) => location.pathname.startsWith(item.key))?.key ?? "";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider theme="light" width={220}>
        <div style={{ padding: 16, fontWeight: 600 }}>FlowFactory</div>
        <Menu mode="inline" selectedKeys={selected ? [selected] : []} items={items} />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{
            background: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: 16,
            paddingInline: 24,
          }}
        >
          <Typography.Text>{me?.username}</Typography.Text>
          <LogoutOutlined
            style={{ cursor: "pointer" }}
            onClick={() => {
              void logout().finally(() => navigate("/login", { replace: true }));
            }}
          />
        </Layout.Header>
        <Layout.Content style={{ padding: 24 }}>{<Outlet />}</Layout.Content>
      </Layout>
    </Layout>
  );
}
