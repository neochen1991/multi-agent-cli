import React, { useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Input, Space, Typography, message } from 'antd';
import { authApi } from '@/services/api';

const { Title, Text } = Typography;

const SettingsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('');
  const token = useMemo(() => localStorage.getItem('sre_token') || '', []);

  const login = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const res = await authApi.login(values.username, values.password);
      localStorage.setItem('sre_token', res.access_token);
      localStorage.setItem('sre_user', res.username);
      localStorage.setItem('sre_role', res.role);
      setUsername(res.username);
      setRole(res.role);
      message.success('登录成功');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const clearToken = () => {
    localStorage.removeItem('sre_token');
    localStorage.removeItem('sre_user');
    localStorage.removeItem('sre_role');
    setUsername('');
    setRole('');
    message.success('已清理本地凭证');
  };

  return (
    <div className="settings-page">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card>
          <Title level={4} style={{ marginTop: 0 }}>
            系统设置
          </Title>
          <Text>当前模型：kimi-k2.5</Text>
          <br />
          <Text>LLM Runtime：AutoGen Multi-Agent</Text>
          <br />
          <Text>LLM Base URL：https://ark.cn-beijing.volces.com/api/coding</Text>
        </Card>

        <Card title="登录（AUTH_ENABLED=true 时需要）">
          <Form layout="inline" onFinish={login}>
            <Form.Item name="username" rules={[{ required: true }]} initialValue="analyst">
              <Input placeholder="用户名" />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true }]} initialValue="analyst123">
              <Input.Password placeholder="密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading}>
                登录
              </Button>
            </Form.Item>
            <Form.Item>
              <Button onClick={clearToken}>清理凭证</Button>
            </Form.Item>
          </Form>
          {token && (
            <Alert
              type="success"
              showIcon
              style={{ marginTop: 16 }}
              message={`已保存 Token，用户：${username || localStorage.getItem('sre_user') || '-'}，角色：${role || localStorage.getItem('sre_role') || '-'}`}
            />
          )}
        </Card>
      </Space>
    </div>
  );
};

export default SettingsPage;
