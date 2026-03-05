import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Collapse, Form, Input, InputNumber, Select, Space, Switch, Typography, message } from 'antd';
import { authApi, settingsApi, type AgentToolingConfig } from '@/services/api';

const { Paragraph, Text, Title } = Typography;
const { Panel } = Collapse;

const REMOTE_SOURCE_META = [
  { key: 'telemetry_source', title: 'Telemetry Source（遥测平台入口）', endpointPlaceholder: 'https://telemetry.example.com/api/v1/snapshot' },
  { key: 'cmdb_source', title: 'CMDB Source（资产平台入口）', endpointPlaceholder: 'https://cmdb.example.com/api/v1/services' },
  { key: 'prometheus_source', title: 'Prometheus Source（指标平台入口）', endpointPlaceholder: 'https://prometheus.example.com/api/v1/query' },
  { key: 'loki_source', title: 'Loki Source（日志平台入口）', endpointPlaceholder: 'https://loki.example.com/loki/api/v1/query_range' },
  { key: 'grafana_source', title: 'Grafana Source（监控看板入口）', endpointPlaceholder: 'https://grafana.example.com/api/ds/query' },
  { key: 'apm_source', title: 'APM Source（链路分析平台入口）', endpointPlaceholder: 'https://apm.example.com/api/v1/traces' },
  { key: 'logcloud_source', title: 'Log Cloud Source（日志云平台入口）', endpointPlaceholder: 'https://logcloud.example.com/api/v1/search' },
  { key: 'alert_platform_source', title: 'Alert Platform Source（监控告警平台入口）', endpointPlaceholder: 'https://alert.example.com/api/v1/alerts' },
] as const;

const AGENT_OPTIONS = [
  { label: 'ProblemAnalysisAgent', value: 'ProblemAnalysisAgent' },
  { label: 'LogAgent', value: 'LogAgent' },
  { label: 'DomainAgent', value: 'DomainAgent' },
  { label: 'CodeAgent', value: 'CodeAgent' },
  { label: 'DatabaseAgent', value: 'DatabaseAgent' },
  { label: 'MetricsAgent', value: 'MetricsAgent' },
  { label: 'ChangeAgent', value: 'ChangeAgent' },
  { label: 'RunbookAgent', value: 'RunbookAgent' },
  { label: 'RuleSuggestionAgent', value: 'RuleSuggestionAgent' },
  { label: 'CriticAgent', value: 'CriticAgent' },
  { label: 'RebuttalAgent', value: 'RebuttalAgent' },
  { label: 'JudgeAgent', value: 'JudgeAgent' },
  { label: 'VerificationAgent', value: 'VerificationAgent' },
];

const renderPanelHeader = (title: string, summary: string) => (
  <div className="settings-collapse-header">
    <span>{title}</span>
    <Text type="secondary">{summary}</Text>
  </div>
);

const SettingsPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [toolingLoading, setToolingLoading] = useState(false);
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('');
  const [tooling, setTooling] = useState<AgentToolingConfig | null>(null);
  const [toolingForm] = Form.useForm<AgentToolingConfig>();
  const token = useMemo(() => localStorage.getItem('sre_token') || '', []);
  const watchedTooling = Form.useWatch([], toolingForm) as Partial<AgentToolingConfig> | undefined;
  const toolingView = watchedTooling || tooling || {};

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
          skills: res.skills || {
            enabled: true,
            skills_dir: 'backend/skills',
            max_skills: 3,
            max_skill_chars: 1600,
            allowed_agents: [],
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

  const localToolsEnabled = [
    toolingView.code_repo?.enabled,
    toolingView.log_file?.enabled,
    toolingView.domain_excel?.enabled,
    toolingView.database?.enabled,
  ].filter(Boolean).length;
  const remoteSourceEnabled = REMOTE_SOURCE_META.filter((item) => Boolean((toolingView as any)[item.key]?.enabled)).length;

  return (
    <div className="settings-page">
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Card className="module-card" title="账号与运行时">
          <Collapse className="settings-collapse" defaultActiveKey={['runtime', 'auth']} ghost>
            <Panel key="runtime" header={renderPanelHeader('系统运行时', 'LangGraph + kimi-k2.5')}>
              <Title level={4} style={{ marginTop: 0, marginBottom: 8 }}>
                系统设置
              </Title>
              <Paragraph style={{ marginBottom: 8 }}>
                当前前后端统一使用火山引擎 OpenAI 兼容接口，模型为 <Text code>kimi-k2.5</Text>。
              </Paragraph>
              <Text>LLM Runtime：LangGraph Multi-Agent</Text>
              <br />
              <Text>LLM Base URL：https://ark.cn-beijing.volces.com/api/coding</Text>
            </Panel>
            <Panel key="auth" header={renderPanelHeader('登录凭证', token ? '已保存 Token' : '未登录')}>
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
            </Panel>
          </Collapse>
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
            <Collapse className="settings-collapse" defaultActiveKey={['local-tools', 'skills']} ghost>
              <Panel
                key="local-tools"
                header={renderPanelHeader('本地工具能力', `已启用 ${localToolsEnabled}/4`)}
              >
                <Collapse className="settings-sub-collapse" defaultActiveKey={['code_repo']} size="small" ghost>
                  <Panel
                    key="code_repo"
                    header={renderPanelHeader('CodeAgent - Git 代码仓检索', toolingView.code_repo?.enabled ? '已启用' : '已关闭')}
                  >
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
                  </Panel>

                  <Panel
                    key="log_file"
                    header={renderPanelHeader('LogAgent - 本地日志文件读取', toolingView.log_file?.enabled ? '已启用' : '已关闭')}
                  >
                    <Form.Item name={['log_file', 'enabled']} label="启用日志文件工具" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                    <Form.Item name={['log_file', 'file_path']} label="日志文件路径">
                      <Input placeholder="/var/log/app/app.log" />
                    </Form.Item>
                    <Form.Item name={['log_file', 'max_lines']} label="最多读取行数">
                      <InputNumber min={50} max={5000} style={{ width: 180 }} />
                    </Form.Item>
                  </Panel>

                  <Panel
                    key="domain_excel"
                    header={renderPanelHeader('DomainAgent - 责任田 Excel 查询', toolingView.domain_excel?.enabled ? '已启用' : '已关闭')}
                  >
                    <Form.Item name={['domain_excel', 'enabled']} label="启用责任田文档工具" valuePropName="checked">
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
                  </Panel>

                  <Panel
                    key="database"
                    header={renderPanelHeader('DatabaseAgent - 数据库取证', toolingView.database?.enabled ? '已启用' : '已关闭')}
                  >
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
                  </Panel>
                </Collapse>
              </Panel>

              <Panel
                key="skills"
                header={renderPanelHeader('Agent Skill Router', toolingView.skills?.enabled ? '已启用' : '已关闭')}
              >
                <Form.Item name={['skills', 'enabled']} label="启用 Skill 路由" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name={['skills', 'skills_dir']} label="Skill 目录">
                  <Input placeholder="backend/skills" />
                </Form.Item>
                <Form.Item name={['skills', 'max_skills']} label="单次最大 Skill 数">
                  <InputNumber min={1} max={10} style={{ width: 180 }} />
                </Form.Item>
                <Form.Item name={['skills', 'max_skill_chars']} label="单个 Skill 最大字符数">
                  <InputNumber min={200} max={8000} style={{ width: 220 }} />
                </Form.Item>
                <Form.Item name={['skills', 'allowed_agents']} label="允许调用 Skill 的 Agent（为空表示全部）">
                  <Select mode="multiple" allowClear placeholder="全部 Agent 可用" options={AGENT_OPTIONS} />
                </Form.Item>
              </Panel>

              <Panel
                key="remote"
                header={renderPanelHeader('远程数据源入口（默认关闭）', `已启用 ${remoteSourceEnabled}/${REMOTE_SOURCE_META.length}`)}
              >
                <Paragraph type="secondary" style={{ marginTop: 0 }}>
                  该组用于预留接入监控、日志、APM 与 CMDB 平台。关闭时不影响本地文件模式。
                </Paragraph>
                <Collapse className="settings-sub-collapse" size="small" ghost>
                  {REMOTE_SOURCE_META.map((source) => {
                    const enabled = Boolean((toolingView as any)[source.key]?.enabled);
                    return (
                      <Panel
                        key={source.key}
                        header={renderPanelHeader(source.title, enabled ? '已启用' : '已关闭')}
                      >
                        <Form.Item
                          name={[source.key, 'enabled']}
                          label="启用数据源入口（默认关闭）"
                          valuePropName="checked"
                        >
                          <Switch />
                        </Form.Item>
                        <Form.Item name={[source.key, 'endpoint']} label="API Endpoint">
                          <Input placeholder={source.endpointPlaceholder} />
                        </Form.Item>
                        <Form.Item name={[source.key, 'api_token']} label="API Token">
                          <Input.Password placeholder="可选，启用后填写" />
                        </Form.Item>
                        <Form.Item name={[source.key, 'timeout_seconds']} label="超时（秒）">
                          <InputNumber min={2} max={60} style={{ width: 180 }} />
                        </Form.Item>
                        <Form.Item name={[source.key, 'verify_ssl']} label="校验证书" valuePropName="checked">
                          <Switch />
                        </Form.Item>
                      </Panel>
                    );
                  })}
                </Collapse>
              </Panel>
            </Collapse>

            <Space style={{ marginTop: 16 }}>
              <Button type="primary" htmlType="submit" loading={toolingLoading}>
                保存工具配置
              </Button>
              <Button
                loading={toolingLoading}
                onClick={() => {
                  if (tooling) {
                    toolingForm.setFieldsValue(tooling);
                  }
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
