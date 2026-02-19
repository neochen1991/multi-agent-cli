import React, { useEffect, useState } from 'react';
import { Button, Card, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { incidentApi, type Incident } from '@/services/api';

const { Title } = Typography;

const statusColor: Record<string, string> = {
  pending: 'default',
  analyzing: 'processing',
  debating: 'blue',
  resolved: 'success',
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
    loadIncidents();
  }, []);

  const columns: ColumnsType<Incident> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 140 },
    { title: '标题', dataIndex: 'title', key: 'title' },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 110,
      render: (severity: string) =>
        severity ? <Tag color={severityColor[severity] || 'default'}>{severity.toUpperCase()}</Tag> : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string) => <Tag color={statusColor[status] || 'default'}>{status}</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss'),
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
          {(record.status === 'resolved' || record.status === 'closed') ? (
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
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Space style={{ justifyContent: 'space-between', width: '100%' }}>
            <Title level={4} style={{ margin: 0 }}>
              历史记录
            </Title>
            <Button onClick={loadIncidents} loading={loading}>
              刷新
            </Button>
          </Space>
          <Table
            columns={columns}
            dataSource={items}
            rowKey="id"
            loading={loading}
            pagination={{ pageSize: 10 }}
          />
        </Space>
      </Card>
    </div>
  );
};

export default HistoryPage;
