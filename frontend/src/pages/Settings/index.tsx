import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Switch, Typography, message } from 'antd';
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
        const defaultDatabase = {
          enabled: false,
          engine: 'sqlite',
          db_path: '',
          postgres_dsn: '',
          pg_schema: 'public',
          connect_timeout_seconds: 8,
          max_rows: 50,
        };
        const normalized: AgentToolingConfig = {
          ...res,
          database: { ...defaultDatabase, ...(res.database || {}) },
          telemetry_source: res.telemetry_source || {
            enabled: false,
            endpoint: '',
            api_token: '',
            timeout_seconds: 8,
            verify_ssl: true,
          },
          cmdb_source: res.cmdb_source || {
            enabled: false,
            endpoint: '',
            api_token: '',
            timeout_seconds: 8,
            verify_ssl: true,
          },
          prometheus_source: res.prometheus_source || {
            enabled: false,
            endpoint: '',
            api_token: '',
            timeout_seconds: 8,
            verify_ssl: true,
          },
          loki_source: res.loki_source || {
            enabled: false,
            endpoint: '',
            api_token: '',
            timeout_seconds: 8,
            verify_ssl: true,
          },
          grafana_source: res.grafana_source || {
            enabled: false,
            endpoint: '',
            api_token: '',
            timeout_seconds: 8,
            verify_ssl: true,
          },
          apm_source: res.apm_source || {
            enabled: false,
            endpoint: '',
            api_token: '',
            timeout_seconds: 8,
            verify_ssl: true,
          },
          logcloud_source: res.logcloud_source || {
            enabled: false,
            endpoint: '',
            api_token: '',
            timeout_seconds: 8,
            verify_ssl: true,
          },
          alert_platform_source: res.alert_platform_source || {
            enabled: false,
            endpoint: '',
            api_token: '',
            timeout_seconds: 8,
            verify_ssl: true,
          },
        };
        setTooling(normalized);
        toolingForm.setFieldsValue(normalized);
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

            <Card size="small" title="DatabaseAgent - 数据库取证" style={{ marginTop: 12 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Form.Item name={['database', 'enabled']} label="启用数据库工具" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name={['database', 'engine']} label="数据库类型">
                  <Select
                    style={{ width: 220 }}
                    options={[
                      { label: 'SQLite（本地文件）', value: 'sqlite' },
                      { label: 'PostgreSQL', value: 'postgresql' },
                    ]}
                  />
                </Form.Item>
                <Form.Item name={['database', 'db_path']} label="SQLite 数据库文件路径">
                  <Input placeholder="/path/to/ops_snapshot.db" />
                </Form.Item>
                <Form.Item name={['database', 'postgres_dsn']} label="PostgreSQL DSN">
                  <Input.Password placeholder="postgresql://user:password@host:5432/dbname" />
                </Form.Item>
                <Form.Item name={['database', 'pg_schema']} label="PostgreSQL Schema">
                  <Input placeholder="public" />
                </Form.Item>
                <Form.Item name={['database', 'connect_timeout_seconds']} label="连接超时（秒）">
                  <InputNumber min={2} max={60} style={{ width: 180 }} />
                </Form.Item>
                <Form.Item name={['database', 'max_rows']} label="慢SQL/TopSQL最大返回条数">
                  <InputNumber min={1} max={500} style={{ width: 180 }} />
                </Form.Item>
              </Space>
            </Card>

            <Card size="small" title="远程数据源入口（默认关闭，不影响本地文件模式）" style={{ marginTop: 12 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Card size="small" title="Telemetry Source（遥测平台入口）">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      name={['telemetry_source', 'enabled']}
                      label="启用远程遥测入口（默认关闭）"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['telemetry_source', 'endpoint']} label="遥测 API Endpoint">
                      <Input placeholder="https://telemetry.example.com/api/v1/snapshot" />
                    </Form.Item>
                    <Form.Item name={['telemetry_source', 'api_token']} label="遥测 API Token">
                      <Input.Password placeholder="可选，启用后填写" />
                    </Form.Item>
                    <Form.Item name={['telemetry_source', 'timeout_seconds']} label="超时（秒）">
                      <InputNumber min={2} max={60} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item
                      name={['telemetry_source', 'verify_ssl']}
                      label="校验证书"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Space>
                </Card>

                <Card size="small" title="CMDB Source（资产平台入口）">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      name={['cmdb_source', 'enabled']}
                      label="启用远程 CMDB 入口（默认关闭）"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['cmdb_source', 'endpoint']} label="CMDB API Endpoint">
                      <Input placeholder="https://cmdb.example.com/api/v1/services" />
                    </Form.Item>
                    <Form.Item name={['cmdb_source', 'api_token']} label="CMDB API Token">
                      <Input.Password placeholder="可选，启用后填写" />
                    </Form.Item>
                    <Form.Item name={['cmdb_source', 'timeout_seconds']} label="超时（秒）">
                      <InputNumber min={2} max={60} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item
                      name={['cmdb_source', 'verify_ssl']}
                      label="校验证书"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Space>
                </Card>

                <Card size="small" title="Prometheus Source（指标平台入口）">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      name={['prometheus_source', 'enabled']}
                      label="启用 Prometheus 入口（默认关闭）"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['prometheus_source', 'endpoint']} label="Prometheus API Endpoint">
                      <Input placeholder="https://prometheus.example.com/api/v1/query" />
                    </Form.Item>
                    <Form.Item name={['prometheus_source', 'api_token']} label="Prometheus API Token">
                      <Input.Password placeholder="可选，启用后填写" />
                    </Form.Item>
                    <Form.Item name={['prometheus_source', 'timeout_seconds']} label="超时（秒）">
                      <InputNumber min={2} max={60} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item
                      name={['prometheus_source', 'verify_ssl']}
                      label="校验证书"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Space>
                </Card>

                <Card size="small" title="Loki Source（日志平台入口）">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      name={['loki_source', 'enabled']}
                      label="启用 Loki 入口（默认关闭）"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['loki_source', 'endpoint']} label="Loki API Endpoint">
                      <Input placeholder="https://loki.example.com/loki/api/v1/query_range" />
                    </Form.Item>
                    <Form.Item name={['loki_source', 'api_token']} label="Loki API Token">
                      <Input.Password placeholder="可选，启用后填写" />
                    </Form.Item>
                    <Form.Item name={['loki_source', 'timeout_seconds']} label="超时（秒）">
                      <InputNumber min={2} max={60} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item
                      name={['loki_source', 'verify_ssl']}
                      label="校验证书"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Space>
                </Card>

                <Card size="small" title="Grafana Source（监控看板入口）">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      name={['grafana_source', 'enabled']}
                      label="启用 Grafana 入口（默认关闭）"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['grafana_source', 'endpoint']} label="Grafana API Endpoint">
                      <Input placeholder="https://grafana.example.com/api/ds/query" />
                    </Form.Item>
                    <Form.Item name={['grafana_source', 'api_token']} label="Grafana API Token">
                      <Input.Password placeholder="可选，启用后填写" />
                    </Form.Item>
                    <Form.Item name={['grafana_source', 'timeout_seconds']} label="超时（秒）">
                      <InputNumber min={2} max={60} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item
                      name={['grafana_source', 'verify_ssl']}
                      label="校验证书"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Space>
                </Card>

                <Card size="small" title="APM Source（链路分析平台入口）">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      name={['apm_source', 'enabled']}
                      label="启用 APM 入口（默认关闭）"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['apm_source', 'endpoint']} label="APM API Endpoint">
                      <Input placeholder="https://apm.example.com/api/v1/traces" />
                    </Form.Item>
                    <Form.Item name={['apm_source', 'api_token']} label="APM API Token">
                      <Input.Password placeholder="可选，启用后填写" />
                    </Form.Item>
                    <Form.Item name={['apm_source', 'timeout_seconds']} label="超时（秒）">
                      <InputNumber min={2} max={60} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item
                      name={['apm_source', 'verify_ssl']}
                      label="校验证书"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Space>
                </Card>

                <Card size="small" title="Log Cloud Source（日志云平台入口）">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      name={['logcloud_source', 'enabled']}
                      label="启用日志云入口（默认关闭）"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['logcloud_source', 'endpoint']} label="日志云 API Endpoint">
                      <Input placeholder="https://logcloud.example.com/api/v1/search" />
                    </Form.Item>
                    <Form.Item name={['logcloud_source', 'api_token']} label="日志云 API Token">
                      <Input.Password placeholder="可选，启用后填写" />
                    </Form.Item>
                    <Form.Item name={['logcloud_source', 'timeout_seconds']} label="超时（秒）">
                      <InputNumber min={2} max={60} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item
                      name={['logcloud_source', 'verify_ssl']}
                      label="校验证书"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Space>
                </Card>

                <Card size="small" title="Alert Platform Source（监控告警平台入口）">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Form.Item
                      name={['alert_platform_source', 'enabled']}
                      label="启用告警平台入口（默认关闭）"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['alert_platform_source', 'endpoint']} label="告警平台 API Endpoint">
                      <Input placeholder="https://alert.example.com/api/v1/alerts" />
                    </Form.Item>
                    <Form.Item name={['alert_platform_source', 'api_token']} label="告警平台 API Token">
                      <Input.Password placeholder="可选，启用后填写" />
                    </Form.Item>
                    <Form.Item name={['alert_platform_source', 'timeout_seconds']} label="超时（秒）">
                      <InputNumber min={2} max={60} style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item
                      name={['alert_platform_source', 'verify_ssl']}
                      label="校验证书"
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Space>
                </Card>
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
