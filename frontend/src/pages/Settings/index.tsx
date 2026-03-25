import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Collapse, Divider, Form, Input, InputNumber, Select, Space, Switch, Typography, message } from 'antd';
import {
  authApi,
  getDefaultMaxRoundsForDepthMode,
  getStoredAnalysisDepthMode,
  setStoredAnalysisDepthMode,
  settingsApi,
  type AgentToolingConfig,
  type AnalysisDepthMode,
} from '@/services/api';

const { Paragraph, Text, Title } = Typography;
const { Panel } = Collapse;

const normalizePath = (value?: string) => String(value || '').trim();

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
  // 分析深度模式是纯前端偏好，用于初始化新会话的默认轮次和分析强度。
  const [analysisDepthMode, setAnalysisDepthMode] = useState<AnalysisDepthMode>(() => getStoredAnalysisDepthMode());
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
          skills: {
            enabled: true,
            skills_dir: 'backend/skills',
            extensions_enabled: true,
            extensions_dir: 'backend/extensions/skills',
            max_skills: 3,
            max_skill_chars: 1600,
            allowed_agents: [],
            ...(res.skills || {}),
          },
          tool_plugins: {
            enabled: true,
            plugins_dir: 'backend/extensions/tools',
            max_calls: 3,
            default_timeout_seconds: 60,
            allowed_tools: [],
            ...(res.tool_plugins || {}),
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
  const localRepoPath = normalizePath(toolingView.code_repo?.local_repo_path);
  const logPath = normalizePath(toolingView.log_file?.file_path);
  const domainPath = normalizePath(toolingView.domain_excel?.excel_path);
  const databasePath = normalizePath(toolingView.database?.db_path);
  const scenarioRoot = useMemo(() => {
    const candidates = [localRepoPath, logPath, domainPath, databasePath].filter(Boolean);
    const hit = candidates.find((item) => item.includes('/mock_data/order_timeout_scenario/'));
    if (!hit) return '';
    const marker = '/mock_data/order_timeout_scenario/';
    const index = hit.indexOf(marker);
    return index >= 0 ? `${hit.slice(0, index)}${marker.slice(0, -1)}` : '';
  }, [databasePath, domainPath, localRepoPath, logPath]);
  const metricsWindowPath = scenarioRoot ? `${scenarioRoot}/metrics/order_metrics_window.csv` : '';
  const metricsDocPath = scenarioRoot ? `${scenarioRoot}/metrics/order_metrics_reference.md` : '';
  const scenarioBindings = [
    {
      agent: 'ProblemAnalysisAgent',
      source: '责任田映射 + 日志摘要 + 各专家反馈',
      detail: '负责收拢问题、分发任务、汇总结论，不直接绑定单个外部文件。',
    },
    {
      agent: 'CodeAgent / ChangeAgent',
      source: localRepoPath || '未配置本地代码仓',
      detail: '共享同一个 monorepo，本场景用于跨模块追踪 order-service / inventory-service / payment-service 调用链与变更。',
    },
    {
      agent: 'LogAgent',
      source: logPath || '未配置日志文件',
      detail: '读取聚合日志与异常时间窗，重建请求时序、错误峰值和上下游放大链路。',
    },
    {
      agent: 'DomainAgent',
      source: domainPath || '未配置责任田文档',
      detail: '从责任田 CSV 命中订单、库存、支付三条资产映射，并补充依赖服务与监控项。',
    },
    {
      agent: 'DatabaseAgent',
      source: databasePath || '未配置数据库快照',
      detail: '读取 SQLite 快照中的业务表、慢 SQL、会话状态与锁等待，模拟 PostgreSQL 取证过程。',
    },
    {
      agent: 'MetricsAgent',
      source: metricsWindowPath || '依赖 incident / 日志文本抽取指标',
      detail: metricsWindowPath
        ? `当前 mock 还提供了分钟级指标窗口 ${metricsWindowPath}，但运行时主要从日志与 incident 文本中抽取关键指标信号。`
        : '当前实现优先从 incident 与日志文本中抽取指标信号，远程遥测入口保持关闭。',
    },
    {
      agent: 'RunbookAgent',
      source: metricsDocPath || '未额外配置本地 runbook 资料',
      detail: metricsDocPath
        ? `本场景额外提供指标与数据库参考文档，可作为后续扩展本地 runbook/case library 的基础材料。`
        : '当前未单独配置本地案例库，仍以系统内置能力和责任田信息为主。',
    },
  ];

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
                当前前后端统一使用 DashScope Coding OpenAI 兼容接口，模型为 <Text code>kimi-k2.5</Text>。
              </Paragraph>
              <Text>LLM Runtime：LangGraph Multi-Agent</Text>
              <br />
              <Text>LLM Base URL：https://coding.dashscope.aliyuncs.com/v1</Text>
              <Divider style={{ margin: '16px 0' }} />
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Text strong>分析深度模式</Text>
                <Select<AnalysisDepthMode>
                  value={analysisDepthMode}
                  style={{ width: 260 }}
                  onChange={(value) => {
                    // 设置页切换后立即落本地存储，Incident 页新建会话时直接读取。
                    setAnalysisDepthMode(value);
                    setStoredAnalysisDepthMode(value);
                    message.success(`分析深度已切换为 ${value}`);
                  }}
                  options={[
                    { label: 'Quick（默认 1 轮，适合快速止血）', value: 'quick' },
                    { label: 'Standard（默认 2 轮，适合常规排障）', value: 'standard' },
                    { label: 'Deep（默认 4 轮，适合复杂根因追问）', value: 'deep' },
                  ]}
                />
                <Text type="secondary">
                  当前模式默认辩论轮次：{getDefaultMaxRoundsForDepthMode(analysisDepthMode)}。Incident 页新建会话时会自动带上这个深度偏好。
                </Text>
              </Space>
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
                key="agent-bindings"
                header={renderPanelHeader('Agent 场景绑定', scenarioRoot ? '已绑定 mock 单仓多服务场景' : '显示当前配置来源')}
              >
                <Paragraph type="secondary" style={{ marginTop: 0 }}>
                  这里直接说明当前设置页里的本地路径分别会被哪些 Agent 使用，避免只看到文件路径但不知道对应哪个分析链路。
                </Paragraph>
                {scenarioRoot && (
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="当前已切到 mock 单仓多服务事故场景"
                    description={`场景目录：${scenarioRoot}`}
                  />
                )}
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {scenarioBindings.map((binding) => (
                    <Card
                      key={binding.agent}
                      size="small"
                      className="ops-summary-card"
                      title={binding.agent}
                      extra={<Text type="secondary">数据源</Text>}
                    >
                      <Paragraph style={{ marginBottom: 8 }}>
                        <Text code>{binding.source}</Text>
                      </Paragraph>
                      <Text type="secondary">{binding.detail}</Text>
                    </Card>
                  ))}
                </Space>
              </Panel>

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
                    <Paragraph type="secondary">
                      `CodeAgent` 与 `ChangeAgent` 共用这一路径。本次 mock 场景建议指向单仓多服务 monorepo。
                    </Paragraph>
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
                    <Paragraph type="secondary">
                      `LogAgent` 建议读取聚合后的事故时间窗日志，而不是只读单条报错摘录。
                    </Paragraph>
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
                    <Paragraph type="secondary">
                      `DomainAgent` 会从这里读取责任田映射，字段必须与接口、代码类、数据库表、监控项保持一致。
                    </Paragraph>
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
                    <Paragraph type="secondary">
                      当前 mock 场景下 `DatabaseAgent` 实际读取 SQLite 快照；如果切到 PostgreSQL，再填写 DSN。
                    </Paragraph>
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
                <Form.Item name={['skills', 'extensions_enabled']} label="启用扩展 Skill 目录" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name={['skills', 'extensions_dir']} label="扩展 Skill 目录">
                  <Input placeholder="backend/extensions/skills" />
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
                key="tool-plugins"
                header={renderPanelHeader('Agent Tool Plugins', toolingView.tool_plugins?.enabled ? '已启用' : '已关闭')}
              >
                <Form.Item name={['tool_plugins', 'enabled']} label="启用扩展 Tool 插件" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item name={['tool_plugins', 'plugins_dir']} label="插件目录">
                  <Input placeholder="backend/extensions/tools" />
                </Form.Item>
                <Form.Item name={['tool_plugins', 'max_calls']} label="单轮最大插件调用次数">
                  <InputNumber min={1} max={20} style={{ width: 180 }} />
                </Form.Item>
                <Form.Item name={['tool_plugins', 'default_timeout_seconds']} label="插件默认超时（秒）">
                  <InputNumber min={5} max={600} style={{ width: 220 }} />
                </Form.Item>
                <Form.Item name={['tool_plugins', 'allowed_tools']} label="允许调用的插件工具（为空表示全部）">
                  <Select mode="tags" allowClear placeholder="例如 design_spec_alignment" />
                </Form.Item>
              </Panel>

              <Panel
                key="remote"
                header={renderPanelHeader('远程数据源入口（默认关闭）', `已启用 ${remoteSourceEnabled}/${REMOTE_SOURCE_META.length}`)}
              >
                <Paragraph type="secondary" style={{ marginTop: 0 }}>
                  该组用于预留接入监控、日志、APM 与 CMDB 平台。关闭时不影响本地文件模式。
                </Paragraph>
                <Paragraph type="secondary" style={{ marginTop: 0 }}>
                  当前 mock 场景里 `MetricsAgent` 主要依赖日志与 incident 文本抽取指标信号，因此这些远程入口默认保持关闭。
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
