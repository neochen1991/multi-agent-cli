import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Row, Space, Statistic, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import { incidentApi, type Incident } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Title } = Typography;

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

const severityColor: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'gold',
  low: 'green',
};

const HistoryPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<Incident[]>([]);

  const loadIncidents = async () => {
    setLoading(true);
    try {
      const data = await incidentApi.list(1, 50);
      setItems(data.items || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载历史失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadIncidents();
  }, []);

  useEffect(() => {
    const hasActive = items.some((item) =>
      ['pending', 'running', 'analyzing', 'debating', 'waiting', 'retrying'].includes(item.status),
    );
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      void loadIncidents();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [items]);

  const summary = useMemo(() => {
    const running = items.filter((item) => ['pending', 'running', 'analyzing', 'debating', 'waiting', 'retrying'].includes(item.status)).length;
    const completed = items.filter((item) => ['resolved', 'completed', 'closed'].includes(item.status)).length;
    const failed = items.filter((item) => item.status === 'failed').length;
    return { total: items.length, running, completed, failed };
  }, [items]);

  const columns: ColumnsType<Incident> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 160 },
    { title: '标题', dataIndex: 'title', key: 'title' },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 120,
      render: (severity: string) =>
        severity ? <Tag color={severityColor[severity] || 'default'}>{severity.toUpperCase()}</Tag> : '-',
    },
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
      width: 240,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/incident/${record.id}`)}>
            详情
          </Button>
          {(record.status === 'resolved' || record.status === 'closed' || record.status === 'completed') ? (
            <Button size="small" type="primary" onClick={() => navigate(`/incident/${record.id}?view=report`)}>
              查看报告
            </Button>
          ) : (
            <Button size="small" type="primary" onClick={() => navigate(`/incident/${record.id}?view=analysis`)}>
              继续分析
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className="history-page">
      <Card className="module-card" style={{ marginBottom: 16 }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            历史记录
          </Title>
          <Button onClick={() => void loadIncidents()} loading={loading}>
            刷新
          </Button>
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="总任务" value={summary.total} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="进行中" value={summary.running} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="已完成" value={summary.completed} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="失败" value={summary.failed} valueStyle={{ color: '#cf1322' }} />
          </Card>
        </Col>
      </Row>

      <Card className="module-card">
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: '暂无历史记录，请先在故障分析页创建任务。' }}
        />
      </Card>
    </div>
  );
};

export default HistoryPage;
