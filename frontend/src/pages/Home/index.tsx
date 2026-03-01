import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Row, Space, Statistic, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { incidentApi, type Incident } from '@/services/api';
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

const AGENT_ROLES: Array<{ name: string; desc: string; color: string }> = [
  { name: 'ProblemAnalysisAgent', desc: '主Agent，负责任务分发、过程协调与最终结论收敛。', color: 'blue' },
  { name: 'LogAgent', desc: '日志模式识别与异常链路定位。', color: 'geekblue' },
  { name: 'DomainAgent', desc: '领域与聚合根映射，责任田归属判断。', color: 'cyan' },
  { name: 'CodeAgent', desc: '代码路径与调用链分析，定位高风险实现。', color: 'orange' },
  { name: 'MetricsAgent', desc: '指标突变、容量瓶颈与资源异常分析。', color: 'green' },
  { name: 'ChangeAgent', desc: '变更窗口关联，识别故障与发布耦合。', color: 'gold' },
  { name: 'RunbookAgent', desc: '案例库检索与处置SOP建议。', color: 'lime' },
  { name: 'CriticAgent', desc: '反例审查，挑战当前假设和证据不足点。', color: 'magenta' },
  { name: 'RebuttalAgent', desc: '针对质疑补充证据并完成反驳。', color: 'purple' },
  { name: 'JudgeAgent', desc: '综合多方观点给出裁决与置信度。', color: 'volcano' },
  { name: 'VerificationAgent', desc: '输出验证计划与回归检查项。', color: 'processing' },
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

  useEffect(() => {
    void loadDashboard();
  }, []);

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
        width: 140,
        render: (_, record) => (
          <Button size="small" type="link" onClick={() => navigate(`/incident/${record.id}`)}>
            查看详情
          </Button>
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
            通过主 Agent 调度日志、代码、领域、指标与案例专家并行分析，沉淀可复核的证据链与可执行结论。
          </Paragraph>
          <Space wrap>
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => navigate('/incident')}>
              开始故障分析
            </Button>
            <Button onClick={() => navigate('/history')}>历史记录</Button>
            <Button onClick={() => navigate('/assets')}>资产定位</Button>
            <Button onClick={() => void loadDashboard()} loading={statsLoading}>
              刷新数据
            </Button>
          </Space>
          <Text type="secondary">数据基于北京时间实时统计，当前总故障：{stats.totalIncidents}</Text>
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

      <Card className="module-card" title="Agent 角色分工" style={{ marginTop: 16 }}>
        <Row gutter={[12, 12]}>
          {AGENT_ROLES.map((agent) => (
            <Col xs={24} sm={12} md={8} lg={6} key={agent.name}>
              <Card
                size="small"
                hoverable
                className="compact-card"
                onClick={() => navigate('/incident')}
              >
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                    <Text strong>{agent.name}</Text>
                    <Tag color={agent.color}>kimi-k2.5</Tag>
                  </Space>
                  <Text type="secondary">{agent.desc}</Text>
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
          locale={{ emptyText: '暂无故障记录，点击“开始故障分析”创建第一条' }}
        />
      </Card>
    </div>
  );
};

export default HomePage;
