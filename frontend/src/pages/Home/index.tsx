import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Input, Row, Select, Space, Statistic, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DeploymentUnitOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { debateApi, incidentApi, type Incident } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Text, Title } = Typography;

const BEIJING_DAY_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const statusColor: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  analyzing: 'processing',
  debating: 'blue',
  waiting: 'gold',
  retrying: 'orange',
  resolved: 'success',
  completed: 'success',
  failed: 'error',
  cancelled: 'default',
  closed: 'default',
};

const START_PATHS = [
  {
    key: '/incident',
    title: '新建分析',
    desc: '输入故障标题、日志或服务名，立即创建事件并启动分析。',
    action: '立即开始',
    icon: <PlayCircleOutlined />,
  },
  {
    key: '/history',
    title: '查看历史记录',
    desc: '查看历史故障状态，继续处理进行中的会话或阅读已完成结论。',
    action: '查看历史',
    icon: <AlertOutlined />,
  },
  {
    key: '/advanced',
    title: '打开高级区',
    desc: '治理、评测、回放和工具接入统一收敛到这里，普通用户通常不必先进入。',
    action: '进入高级',
    icon: <DeploymentUnitOutlined />,
  },
];

const AGENT_OVERVIEW = [
  {
    name: 'ProblemAnalysisAgent',
    role: '主 Agent',
    desc: '汇总故障上下文，发出任务命令并收敛最终根因结论。',
  },
  {
    name: 'LogAgent',
    role: '日志专家',
    desc: '对齐日志时间线、trace 线索与异常模式，产出首轮证据。',
  },
  {
    name: 'CodeAgent',
    role: '代码专家',
    desc: '从入口到调用链闭包定位风险点，关联 SQL 与下游依赖。',
  },
  {
    name: 'DomainAgent',
    role: '领域专家',
    desc: '定位责任田归属与领域约束，判断业务规则与边界偏差。',
  },
  {
    name: 'DatabaseAgent',
    role: '数据库专家',
    desc: '分析连接池、锁等待、索引与热点 SQL，判断数据面根因。',
  },
  {
    name: 'MetricsAgent',
    role: '指标专家',
    desc: '关联监控与 SLO 曲线，验证异常与业务影响范围。',
  },
  {
    name: 'ChangeAgent',
    role: '变更专家',
    desc: '关联发布/配置/依赖变更，评估变更引入的回归风险。',
  },
  {
    name: 'RunbookAgent',
    role: '运维专家',
    desc: '匹配应急手册与处置路径，补充应急动作建议。',
  },
  {
    name: 'JudgeAgent',
    role: '裁决 Agent',
    desc: '核验证据链一致性，输出可信结论与复盘建议。',
  },
];

type DashboardStats = {
  todayAnalyses: number;
  resolvedCount: number;
  avgResolveMinutes: number;
  closureRate: number;
  totalIncidents: number;
};

const parseDate = (value: unknown): Date | null => {
  if (value === null || value === undefined || value === '') return null;
  let normalized: string | number = value as string | number;
  if (typeof value === 'string') {
    const raw = value.trim();
    const hasTimezone = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw);
    if (!hasTimezone && /^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(raw)) {
      normalized = `${raw.replace(' ', 'T')}Z`;
    } else {
      normalized = raw;
    }
  }
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
};

const beijingDayKey = (value: unknown): string => {
  const date = parseDate(value);
  if (!date) return '';
  return BEIJING_DAY_FORMATTER.format(date);
};

const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const [statsLoading, setStatsLoading] = useState(false);
  const [stats, setStats] = useState<DashboardStats>({
    todayAnalyses: 0,
    resolvedCount: 0,
    avgResolveMinutes: 0,
    closureRate: 0,
    totalIncidents: 0,
  });
  const [recentIncidents, setRecentIncidents] = useState<Incident[]>([]);
  const [quickStartLoading, setQuickStartLoading] = useState(false);
  const [quickStartForm, setQuickStartForm] = useState({
    title: '',
    service_name: '',
    severity: 'high',
    log_content: '',
    mode: 'standard',
  });

  const loadDashboard = async () => {
    setStatsLoading(true);
    try {
      const [recentRes, resolvedRes, closedRes] = await Promise.all([
        incidentApi.list(1, 100),
        incidentApi.list(1, 100, { status: 'resolved' }),
        incidentApi.list(1, 100, { status: 'closed' }),
      ]);

      const recent = recentRes.items || [];
      const resolvedItems = [...(resolvedRes.items || []), ...(closedRes.items || [])];
      const todayKey = beijingDayKey(new Date());
      const todayAnalyses = recent.filter((item) => beijingDayKey(item.created_at) === todayKey).length;
      const resolvedCount = (resolvedRes.total || 0) + (closedRes.total || 0);
      const durations = resolvedItems
        .map((item) => {
          const start = parseDate(item.created_at);
          const end = parseDate(item.resolved_at || item.updated_at);
          if (!start || !end) return 0;
          const diff = (end.getTime() - start.getTime()) / 60000;
          return diff > 0 ? diff : 0;
        })
        .filter((value) => value > 0);
      const avgResolveMinutes = durations.length
        ? Math.round(durations.reduce((sum, item) => sum + item, 0) / durations.length)
        : 0;
      const totalIncidents = Number(recentRes.total || 0);
      const closureRate = totalIncidents > 0 ? Number(((resolvedCount / totalIncidents) * 100).toFixed(1)) : 0;

      setStats({
        todayAnalyses,
        resolvedCount,
        avgResolveMinutes,
        closureRate,
        totalIncidents,
      });
      setRecentIncidents(recent.slice(0, 10));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '首页数据加载失败');
    } finally {
      setStatsLoading(false);
    }
  };

  const runAutoInvestigate = async (incident: Incident) => {
    try {
      message.loading({ content: `已提交自动调查：${incident.id}`, key: `auto-${incident.id}`, duration: 0 });
      const started = await incidentApi.autoInvestigate(incident.id, 1);
      let finalStatus = 'pending';
      for (let i = 0; i < 40; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const task = await debateApi.getTask(started.task_id);
        finalStatus = String(task.status || 'pending');
        if (finalStatus === 'completed') {
          break;
        }
        if (finalStatus === 'failed') {
          throw new Error(String(task.error || '自动调查任务失败'));
        }
      }
      message.success({ content: `自动调查完成：${incident.id}`, key: `auto-${incident.id}` });
      await loadDashboard();
      navigate(`/incident/${incident.id}`);
    } catch (e: any) {
      message.error({
        content: e?.response?.data?.detail || e?.message || `自动调查失败：${incident.id}`,
        key: `auto-${incident.id}`,
      });
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, []);

  const quickStartAnalysis = async () => {
    const title = String(quickStartForm.title || '').trim();
    if (!title) {
      message.warning('请先输入故障标题');
      return;
    }
    setQuickStartLoading(true);
    try {
      const incident = await incidentApi.create({
        title,
        severity: quickStartForm.severity,
        service_name: String(quickStartForm.service_name || '').trim(),
        log_content: String(quickStartForm.log_content || '').trim(),
      });
      const mode = String(quickStartForm.mode || 'standard') as 'standard' | 'quick' | 'background';
      const session = await debateApi.createSession(incident.id, { maxRounds: 1, mode });
      message.success(`会话已创建：${session.id}`);
      void loadDashboard();
      navigate(`/incident/${incident.id}?view=analysis&session_id=${session.id}&auto_start=1&mode=${mode}`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '快速启动分析失败');
    } finally {
      setQuickStartLoading(false);
    }
  };

  const recentColumns: ColumnsType<Incident> = useMemo(
    () => [
      { title: 'Incident ID', dataIndex: 'id', key: 'id', width: 150 },
      { title: '标题', dataIndex: 'title', key: 'title' },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 120,
        render: (status: string) => <Tag color={statusColor[status] || 'default'}>{status}</Tag>,
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 250,
        render: (value: string) => formatBeijingDateTime(value),
      },
      {
        title: '操作',
        key: 'action',
        width: 220,
        render: (_, record) => (
          <Space size={4}>
            <Button size="small" type="link" onClick={() => navigate(`/incident/${record.id}`)}>
              查看详情
            </Button>
            <Button size="small" type="link" onClick={() => void runAutoInvestigate(record)}>
              一键自动调查
            </Button>
          </Space>
        ),
      },
    ],
    [navigate],
  );

  return (
    <div className="home-page">
      <Card className="module-card home-hero-card">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Tag color="processing" style={{ width: 'fit-content' }}>
            生产环境智能排障
          </Tag>
          <Title level={3} style={{ margin: 0 }}>
            多 Agent 协作式根因分析平台
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            先进入“故障分析”创建分析任务，再到“历史记录”跟踪状态、进入详情页查看证据链和结论。治理、评测、回放等后台能力统一收敛到“高级”。
          </Paragraph>
          <Space wrap>
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => navigate('/incident')}>
              故障分析
            </Button>
            <Button onClick={() => navigate('/v2')}>切换到新版工作台</Button>
            <Button onClick={() => navigate('/history')}>历史记录</Button>
            <Button onClick={() => navigate('/assets')}>维护责任田</Button>
            <Button onClick={() => void loadDashboard()} loading={statsLoading}>
              刷新数据
            </Button>
          </Space>
          <Text type="secondary">推荐新手路径：故障分析 {'->'} 历史记录 {'->'} 故障详情。当前总故障：{stats.totalIncidents}</Text>
        </Space>
      </Card>

      <Card className="module-card" title="快速启动分析" style={{ marginTop: 16 }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Row gutter={[12, 12]}>
            <Col xs={24} md={8}>
              <Input
                placeholder="故障标题（必填）"
                value={quickStartForm.title}
                onChange={(e) => setQuickStartForm((prev) => ({ ...prev, title: e.target.value }))}
              />
            </Col>
            <Col xs={24} md={6}>
              <Input
                placeholder="服务名（可选）"
                value={quickStartForm.service_name}
                onChange={(e) => setQuickStartForm((prev) => ({ ...prev, service_name: e.target.value }))}
              />
            </Col>
            <Col xs={24} md={4}>
              <Select
                value={quickStartForm.severity}
                style={{ width: '100%' }}
                options={[
                  { label: 'Critical', value: 'critical' },
                  { label: 'High', value: 'high' },
                  { label: 'Medium', value: 'medium' },
                  { label: 'Low', value: 'low' },
                ]}
                onChange={(value) => setQuickStartForm((prev) => ({ ...prev, severity: value }))}
              />
            </Col>
            <Col xs={24} md={4}>
              <Select
                value={quickStartForm.mode}
                style={{ width: '100%' }}
                options={[
                  { label: 'Standard（强模型，完整分析）', value: 'standard' },
                  { label: 'Quick（弱模型友好，快速收敛）', value: 'quick' },
                  { label: 'Background（后台运行方式）', value: 'background' },
                ]}
                onChange={(value) => setQuickStartForm((prev) => ({ ...prev, mode: value }))}
              />
            </Col>
            <Col xs={24} md={24} lg={4}>
              <Button
                type="primary"
                className="quick-start-submit-btn"
                loading={quickStartLoading}
                onClick={() => void quickStartAnalysis()}
                style={{ width: '100%' }}
              >
                创建并启动分析
              </Button>
            </Col>
          </Row>
          <Input.TextArea
            rows={4}
            placeholder="可选：粘贴关键日志/堆栈，进入详情页后会自动开始分析"
            value={quickStartForm.log_content}
            onChange={(e) => setQuickStartForm((prev) => ({ ...prev, log_content: e.target.value }))}
          />
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card" loading={statsLoading}>
            <Statistic title="今日分析" value={stats.todayAnalyses} prefix={<AlertOutlined />} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card" loading={statsLoading}>
            <Statistic title="已解决" value={stats.resolvedCount} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card" loading={statsLoading}>
            <Statistic title="平均耗时" value={stats.avgResolveMinutes} suffix="分钟" prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card" loading={statsLoading}>
            <Statistic title="闭环率" value={stats.closureRate} suffix="%" precision={1} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
      </Row>

      <Card className="module-card" title="Agent 角色速览" style={{ marginTop: 16 }}>
        <Row gutter={[12, 12]}>
          {AGENT_OVERVIEW.map((agent) => (
            <Col xs={24} md={12} lg={8} key={agent.name}>
              <Card size="small" className="compact-card">
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Text strong>{agent.name}</Text>
                    <Tag color={agent.role === '主 Agent' ? 'processing' : 'default'}>{agent.role}</Tag>
                  </Space>
                  <Text type="secondary">{agent.desc}</Text>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card className="module-card" title="新手上手路径" style={{ marginTop: 16 }}>
        <Row gutter={[12, 12]}>
          {START_PATHS.map((path) => (
            <Col xs={24} md={8} key={path.key}>
              <Card
                size="small"
                hoverable
                className="compact-card quick-path-card"
                onClick={() => navigate(path.key)}
              >
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Space>
                      <div className="quick-path-icon">{path.icon}</div>
                      <Text strong>{path.title}</Text>
                    </Space>
                    <Tag color="blue">{path.action}</Tag>
                  </Space>
                  <Text type="secondary">{path.desc}</Text>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card className="module-card" title="最近故障" style={{ marginTop: 16 }}>
        <Table
          rowKey="id"
          columns={recentColumns}
          dataSource={recentIncidents}
          loading={statsLoading}
          pagination={false}
          locale={{ emptyText: '暂无故障记录，点击“新建分析”创建第一条' }}
        />
      </Card>
    </div>
  );
};

export default HomePage;
