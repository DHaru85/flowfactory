import { App as AntApp, ConfigProvider, Spin } from "antd";
import zhCN from "antd/locale/zh_CN";
import { useCallback, useEffect, useMemo, useState, type ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { fetchApps, fetchMe } from "@/api/auth";
import { errorMessage } from "@/api/client";
import { SessionContext, findApp } from "@/auth/context";
import { isLoggedIn } from "@/auth/session";
import { AppShell } from "@/layouts/AppShell";
import { AgentConfigPage } from "@/pages/AgentConfigPage";
import { ChatPage } from "@/pages/ChatPage";
import { HitlInboxPage } from "@/pages/HitlInboxPage";
import { LoginPage } from "@/pages/LoginPage";
import { ModelsPage } from "@/pages/ModelsPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { StudioCanvasPage } from "@/pages/StudioCanvasPage";
import { StudioListPage } from "@/pages/StudioListPage";
import type { AppVisibilityOut, MeOut } from "@/types";

function HomeRedirect({ apps }: { apps: AppVisibilityOut[] }): ReactElement {
  if (findApp(apps, "conversation")?.can_use) {
    return <Navigate to="/planner" replace />;
  }
  if (findApp(apps, "models")?.can_use) {
    return <Navigate to="/models" replace />;
  }
  if (findApp(apps, "agent_config")?.can_use) {
    return <Navigate to="/agent-config" replace />;
  }
  if (findApp(apps, "studio")?.can_use) {
    return <Navigate to="/studio" replace />;
  }
  return <div>当前账号没有可打开的应用，请联系管理员绑定。</div>;
}

function Guard({
  appKey,
  children,
  apps,
}: {
  appKey: string;
  children: ReactElement;
  apps: AppVisibilityOut[];
}): ReactElement {
  if (!findApp(apps, appKey)?.can_use) {
    return <div>无权访问该应用</div>;
  }
  return children;
}

function AuthedApp(): ReactElement {
  const [me, setMe] = useState<MeOut | null>(null);
  const [apps, setApps] = useState<AppVisibilityOut[]>([]);
  const [ready, setReady] = useState(false);
  const [fail, setFail] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [m, a] = await Promise.all([fetchMe(), fetchApps()]);
    setMe(m);
    setApps(a);
  }, []);

  useEffect(() => {
    void reload()
      .catch((err: unknown) => setFail(errorMessage(err, "加载用户失败")))
      .finally(() => setReady(true));
  }, [reload]);

  const ctx = useMemo(() => ({ me, apps, reload }), [me, apps, reload]);

  if (!ready) {
    return <Spin style={{ margin: 48 }} />;
  }
  if (fail) {
    return <div style={{ padding: 24 }}>{fail}</div>;
  }

  return (
    <SessionContext.Provider value={ctx}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<HomeRedirect apps={apps} />} />
          <Route
            path="/planner"
            element={
              <Guard appKey="conversation" apps={apps}>
                <ChatPage scene="planner" />
              </Guard>
            }
          />
          <Route
            path="/workflow"
            element={
              <Guard appKey="conversation" apps={apps}>
                <ChatPage scene="workflow" />
              </Guard>
            }
          />
          <Route
            path="/hitl"
            element={
              <Guard appKey="conversation" apps={apps}>
                <HitlInboxPage />
              </Guard>
            }
          />
          <Route
            path="/models"
            element={
              <Guard appKey="models" apps={apps}>
                <ModelsPage />
              </Guard>
            }
          />
          <Route
            path="/agent-config"
            element={
              <Guard appKey="agent_config" apps={apps}>
                <AgentConfigPage />
              </Guard>
            }
          />
          <Route
            path="/studio"
            element={
              <Guard appKey="studio" apps={apps}>
                <StudioListPage />
              </Guard>
            }
          />
          <Route
            path="/studio/:flowId"
            element={
              <Guard appKey="studio" apps={apps}>
                <StudioCanvasPage />
              </Guard>
            }
          />
        </Route>
      </Routes>
    </SessionContext.Provider>
  );
}

function RequireAuth(): ReactElement {
  if (!isLoggedIn()) {
    return <Navigate to="/login" replace />;
  }
  return <AuthedApp />;
}

function GuestOnly({ children }: { children: ReactElement }): ReactElement {
  if (isLoggedIn()) {
    return <Navigate to="/" replace />;
  }
  return children;
}

export function App(): ReactElement {
  return (
    <ConfigProvider locale={zhCN}>
      <AntApp>
        <Routes>
          <Route
            path="/login"
            element={
              <GuestOnly>
                <LoginPage />
              </GuestOnly>
            }
          />
          <Route
            path="/register"
            element={
              <GuestOnly>
                <RegisterPage />
              </GuestOnly>
            }
          />
          <Route path="/*" element={<RequireAuth />} />
        </Routes>
      </AntApp>
    </ConfigProvider>
  );
}
