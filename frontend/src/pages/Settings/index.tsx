import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Space, Switch, Typography, message } from 'antd';
import { authApi, settingsApi, type AgentToolingConfig } from '@/services/api';

const { Paragraph, Text, Title } = Typography;

const SettingsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [toolingLoading, setToolingLoading] = useState(false);
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('');
  const [tooling, setTooling] = useState<AgentToolingConfig | null>(null);
  const [toolingForm] = Form.useForm<AgentToolingConfig>();
  const token = useMemo(() => localStorage.getItem('sre_token') || '', []);

  useEffect(() => {
    setToolingLoading(true);
    settingsApi
      .getTooling()
      .then((res) => {
        setTooling(res);
        toolingForm.setFieldsValue(res);
      })
      .catch((e: any) => {
        message.error(e?.response?.data?.detail || e.message || '加载工具配置失败');
      })
      .finally(() => setToolingLoading(false));
  }, [toolingForm]);

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
        <Card className="module-card">
          <Title level={4} style={{ marginTop: 0, marginBottom: 8 }}>
            系统设置
          </Title>
          <Paragraph style={{ marginBottom: 8 }}>
            当前前后端统一使用火山引擎 OpenAI 兼容接口，模型为 <Text code>kimi-k2.5</Text>。
          </Paragraph>
          <Text>LLM Runtime：LangGraph Multi-Agent</Text>
          <br />
          <Text>LLM Base URL：https://ark.cn-beijing.volces.com/api/coding</Text>
        </Card>

        <Card className="module-card" title="登录凭证（AUTH_ENABLED=true 时需要）">
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

        <Card className="module-card" title="Agent 工具配置">
          <Form
            form={toolingForm}
            layout="vertical"
            onFinish={async (values) => {
              setToolingLoading(true);
              try {
                const saved = await settingsApi.updateTooling(values);
                setTooling(saved);
                toolingForm.setFieldsValue(saved);
                message.success('工具配置已保存');
              } catch (e: any) {
                message.error(e?.response?.data?.detail || e.message || '保存工具配置失败');
              } finally {
                setToolingLoading(false);
              }
            }}
          >
            <Card size="small" title="CodeAgent - Git 代码仓检索" style={{ marginBottom: 12 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Form.Item name={['code_repo', 'enabled']} label="启用 Git 工具" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name={['code_repo', 'repo_url']} label="仓库链接（HTTPS）">
                  <Input placeholder="https://git.example.com/org/repo.git" />
                </Form.Item>
                <Form.Item name={['code_repo', 'access_token']} label="访问 Token">
                  <Input.Password placeholder="可选，私有仓库时填写" />
                </Form.Item>
                <Form.Item name={['code_repo', 'branch']} label="分支">
                  <Input placeholder="main" />
                </Form.Item>
                <Form.Item name={['code_repo', 'local_repo_path']} label="本地仓库路径（可选，优先）">
                  <Input placeholder="/path/to/repo" />
                </Form.Item>
                <Form.Item name={['code_repo', 'max_hits']} label="最大命中条数">
                  <InputNumber min={1} max={200} style={{ width: 180 }} />
                </Form.Item>
              </Space>
            </Card>

            <Card size="small" title="LogAgent - 本地日志文件读取" style={{ marginBottom: 12 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Form.Item name={['log_file', 'enabled']} label="启用日志文件工具" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name={['log_file', 'file_path']} label="日志文件路径">
                  <Input placeholder="/var/log/app/app.log" />
                </Form.Item>
                <Form.Item name={['log_file', 'max_lines']} label="最多读取行数">
                  <InputNumber min={50} max={5000} style={{ width: 180 }} />
                </Form.Item>
              </Space>
            </Card>

            <Card size="small" title="DomainAgent - 责任田 Excel 查询">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Form.Item
                  name={['domain_excel', 'enabled']}
                  label="启用责任田文档工具"
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>
                <Form.Item name={['domain_excel', 'excel_path']} label="Excel/CSV 文件路径">
                  <Input placeholder="/path/to/domain-ownership.xlsx" />
                </Form.Item>
                <Form.Item name={['domain_excel', 'sheet_name']} label="工作表名称（可选）">
                  <Input placeholder="Sheet1" />
                </Form.Item>
                <Form.Item name={['domain_excel', 'max_rows']} label="最大扫描行数">
                  <InputNumber min={50} max={5000} style={{ width: 180 }} />
                </Form.Item>
                <Form.Item name={['domain_excel', 'max_matches']} label="最大命中行数">
                  <InputNumber min={1} max={200} style={{ width: 180 }} />
                </Form.Item>
              </Space>
            </Card>

            <Space style={{ marginTop: 16 }}>
              <Button type="primary" htmlType="submit" loading={toolingLoading}>
                保存工具配置
              </Button>
              <Button
                loading={toolingLoading}
                onClick={() => {
                  if (tooling) toolingForm.setFieldsValue(tooling);
                }}
              >
                还原已保存配置
              </Button>
            </Space>
          </Form>
        </Card>
      </Space>
    </div>
  );
};

export default SettingsPage;
