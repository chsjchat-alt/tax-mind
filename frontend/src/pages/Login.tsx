import { useNavigate, Navigate } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, Alert } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/store/authStore';

const { Title, Text } = Typography;

function Login() {
  const navigate = useNavigate();
  const { token, login, loading, error } = useAuthStore();
  const [form] = Form.useForm();

  // 已登录则跳转到 Dashboard
  if (token) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleLogin = async (values: { username: string; password: string }) => {
    try {
      await login(values.username, values.password);
      navigate('/dashboard', { replace: true });
    } catch {
      // error is handled in store
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <Card
        className="w-full max-w-md shadow-2xl"
        styles={{ body: { padding: 32 } }}
      >
        <div className="text-center mb-6">
          <Title level={3} className="!mb-1 text-slate-800">
            蒙牛全产业链 AI 内生合规决策大脑
          </Title>
          <Text type="secondary">智能税务风险评估系统</Text>
        </div>

        {error && (
          <Alert message={error} type="error" showIcon className="mb-4" />
        )}

        <Form
          form={form}
          layout="vertical"
          onFinish={handleLogin}
          autoComplete="off"
          size="large"
        >
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>

          <Form.Item className="mb-2">
            <Button type="primary" htmlType="submit" loading={loading} block>
              登 录
            </Button>
          </Form.Item>
        </Form>

        <div className="text-center mt-4">
          <Text type="secondary" className="text-xs">
            测试账号: admin_t1 / a123456
          </Text>
        </div>
      </Card>
    </div>
  );
}

export default Login;
