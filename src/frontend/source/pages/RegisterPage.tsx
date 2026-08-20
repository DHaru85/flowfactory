import { Button, Form, Input, Typography } from "antd";
import { useState, type ReactElement } from "react";
import { Link, useNavigate } from "react-router-dom";

import { register } from "@/api/auth";
import { errorMessage } from "@/api/client";

interface RegisterForm {
  username: string;
  password: string;
  display_name: string;
}

export function RegisterPage(): ReactElement {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm<RegisterForm>();

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
        <Typography.Title level={3}>注册</Typography.Title>
        <Typography.Paragraph type="secondary">创建本地账号后自动登录</Typography.Paragraph>
        <Form
          form={form}
          layout="vertical"
          onFinish={async (values) => {
            setLoading(true);
            try {
              await register({
                username: values.username,
                password: values.password,
                display_name: values.display_name || null,
              });
              navigate("/", { replace: true });
            } catch (err) {
              form.setFields([{ name: "username", errors: [errorMessage(err, "注册失败")] }]);
            } finally {
              setLoading(false);
            }
          }}
        >
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名">
            <Input autoComplete="nickname" placeholder="可空，默认等于用户名" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: "请输入密码" },
              { min: 8, message: "至少 8 位" },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            注册并登录
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0 }}>
          已有账号？<Link to="/login">去登录</Link>
        </Typography.Paragraph>
      </div>
    </div>
  );
}
