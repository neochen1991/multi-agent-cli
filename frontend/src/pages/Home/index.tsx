import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Row, Space, Statistic, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { incidentApi, type Incident } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Title, Paragraph, Text } = Typography;

const BEIJING_DAY_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const AGENT_MODEL_NAME = 'kimi-k2.5';

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
      setRecentIncidents(recent.slice(0, 8));
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
      { title: 'Incident ID', dataIndex: 'id', key: 'id', width: 130 },
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
        width: 240,
        render: (value: string) => formatBeijingDateTime(value),
      },
      {
        title: '操作',
        key: 'action',
        width: 130,
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
      <Card style={{ marginBottom: 24 }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Title level={2} style={{ margin: 0 }}>
            <RobotOutlined style={{ marginRight: 12, color: '#1677ff' }} />
            生产问题根因分析平台
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            基于 LangGraph 多 Agent 协同辩论，融合日志、代码、责任田资产，输出可执行根因结论与修复建议。
          </Paragraph>
          <Space>
            <Button type="primary" size="large" onClick={() => navigate('/incident')}>
              开始故障分析
            </Button>
            <Button size="large" onClick={() => navigate('/history')}>
              查看历史记录
            </Button>
            <Button size="large" onClick={() => navigate('/assets')}>
              资产定位
            </Button>
            <Button size="large" onClick={() => void loadDashboard()} loading={statsLoading}>
              刷新首页数据
            </Button>
          </Space>
          <Text type="secondary">{`总故障数：${stats.totalIncidents}（实时接口统计）`}</Text>
        </Space>
      </Card>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card hoverable loading={statsLoading} onClick={() => navigate('/history')}>
            <Statistic title="今日分析" value={stats.todayAnalyses} prefix={<AlertOutlined />} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable loading={statsLoading} onClick={() => navigate('/history')}>
            <Statistic title="已解决" value={stats.resolvedCount} prefix={<CheckCircleOutlined />} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable loading={statsLoading} onClick={() => navigate('/history')}>
            <Statistic title="平均耗时" value={stats.avgResolveMinutes} suffix="分钟" prefix={<ClockCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card hoverable loading={statsLoading} onClick={() => navigate('/history')}>
            <Statistic title="闭环率" value={stats.closureRate} suffix="%" precision={1} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={8}>
          <Card title="资产映射定位" hoverable onClick={() => navigate('/assets')}>
            <Paragraph style={{ marginBottom: 0 }}>
              基于接口与错误日志定位领域、聚合根、代码路径与数据库表，快速命中责任田。
            </Paragraph>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="多 Agent 辩论分析" hoverable onClick={() => navigate('/incident')}>
            <Paragraph style={{ marginBottom: 0 }}>
              主Agent调度 Log/Domain/Code/Critic/Rebuttal/Judge 多专家多轮协同，持续收敛根因。
            </Paragraph>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="报告与复盘沉淀" hoverable onClick={() => navigate('/history')}>
            <Paragraph style={{ marginBottom: 0 }}>
              输出结构化结论、影响评估与修复建议，并可在历史中回看每次分析过程。
            </Paragraph>
          </Card>
        </Col>
      </Row>

      <Card title="专家角色分工（点击可进入分析）" style={{ marginTop: 24 }}>
        <Row gutter={[16, 16]}>
          {[
            { name: 'ProblemAnalysisAgent', desc: '主Agent，任务分发与最终裁决协调', bg: '#f0f5ff', border: '#adc6ff' },
            { name: 'LogAgent', desc: '日志结构化分析专家', bg: '#f6ffed', border: '#b7eb8f' },
            { name: 'DomainAgent', desc: '领域映射与责任田专家', bg: '#e6f7ff', border: '#91d5ff' },
            { name: 'CodeAgent', desc: '代码与调用链分析专家', bg: '#fff7e6', border: '#ffd591' },
            { name: 'CriticAgent', desc: '反例质疑与漏洞发现专家', bg: '#fff1f0', border: '#ffa39e' },
            { name: 'RebuttalAgent', desc: '证据补强与反驳专家', bg: '#f9f0ff', border: '#d3adf7' },
            { name: 'JudgeAgent', desc: '收敛裁决与结论生成专家', bg: '#fff0f6', border: '#ffadd2' },
          ].map((agent) => (
            <Col span={8} key={agent.name}>
              <Card
                hoverable
                size="small"
                style={{ background: agent.bg, borderColor: agent.border }}
                onClick={() => navigate('/incident')}
              >
                <Space direction="vertical" size={2}>
                  <Text strong>{agent.name}</Text>
                  <Tag color="blue">{AGENT_MODEL_NAME}</Tag>
                  <Paragraph style={{ marginBottom: 0 }}>{agent.desc}</Paragraph>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card title="最近故障（实时）" style={{ marginTop: 24 }}>
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
