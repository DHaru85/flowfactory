import { Button, Form, Input, Typography } from "antd";
import { useState, type ReactElement } from "react";
import { Link, useNavigate } from "react-router-dom";

import { login } from "@/api/auth";
import { errorMessage } from "@/api/client";

interface LoginForm {
  username: string;
  password: string;
}

export function LoginPage(): ReactElement {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm<LoginForm>();

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f5f5f5",
      }}
    >
      <div style={{ width: 360, padding: 32, background: "#fff", borderRadius: 8 }}>
        <Typography.Title level={3}>FlowFactory</Typography.Title>
        <Typography.Paragraph type="secondary">登录后进入管理台与会话</Typography.Paragraph>
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            setLoading(true);
            try {
              await login(values);
              navigate("/", { replace: true });
            } catch (err) {
              form.setFields([{ name: "password", errors: [errorMessage(err, "登录失败")] }]);
            } finally {
              setLoading(false);
            }
          }}
        >
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0 }}>
          没有账号？<Link to="/register">注册</Link>
        </Typography.Paragraph>
      </div>
    </div>
  );
}
