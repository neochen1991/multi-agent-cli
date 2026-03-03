import React, { useEffect, useState } from 'react';
import { Button, Card, Empty, Input, List, Space, Table, Tag, Typography, message } from 'antd';
import { settingsApi, type ToolRegistryItem, type ToolAuditResponse } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Text, Title } = Typography;

const ToolsCenterPage: React.FC = () => {
  const [registry, setRegistry] = useState<ToolRegistryItem[]>([]);
  const [connectors, setConnectors] = useState<Array<Record<string, unknown>>>([]);
  const [sessionId, setSessionId] = useState('');
  const [audit, setAudit] = useState<ToolAuditResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadBase = async () => {
    try {
      const [items, links] = await Promise.all([settingsApi.getToolRegistry(), settingsApi.getToolConnectors()]);
      setRegistry(items || []);
      setConnectors(links || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '工具中心加载失败');
    }
  };

  const loadAudit = async () => {
    const id = sessionId.trim();
    if (!id) {
      message.warning('请输入会话ID');
      return;
    }
    setLoading(true);
    try {
      const result = await settingsApi.getToolAudit(id);
      setAudit(result);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '审计记录加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadBase();
  }, []);

  return (
    <div>
      <Card className="module-card">
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            工具中心
          </Title>
          <Text type="secondary">查看工具注册、连接器映射与会话级工具调用审计。</Text>
        </Space>
      </Card>

      <Card className="module-card" title="工具注册中心" style={{ marginTop: 16 }}>
        <Table
          rowKey="tool_name"
          dataSource={registry}
          pagination={false}
          columns={[
            { title: '工具', dataIndex: 'tool_name', key: 'tool_name', width: 220 },
            { title: '分类', dataIndex: 'category', key: 'category', width: 140 },
            { title: '所属Agent', dataIndex: 'owner_agent', key: 'owner_agent', width: 180 },
            {
              title: '状态',
              dataIndex: 'enabled',
              key: 'enabled',
              width: 120,
              render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? 'enabled' : 'disabled'}</Tag>,
            },
            {
              title: '策略',
              key: 'policy',
              render: (_: unknown, row: ToolRegistryItem) => (
                <Text type="secondary">timeout={String((row.policy || {}).timeout_seconds || '-')}s</Text>
              ),
            },
          ]}
        />
      </Card>

      <Card className="module-card" title="连接器协议" style={{ marginTop: 16 }}>
        <List
          size="small"
          dataSource={connectors}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={0}>
                <Text>{String(item.name || '')}</Text>
                <Text type="secondary">
                  resource={String(item.resource || '')}, tools={String((item.tools || []) as any)}
                </Text>
              </Space>
            </List.Item>
          )}
        />
      </Card>

      <Card className="module-card" title="工具调用审计" style={{ marginTop: 16 }}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Input
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            placeholder="输入会话ID"
            style={{ width: 320 }}
          />
          <Button type="primary" loading={loading} onClick={() => void loadAudit()}>
            查询审计
          </Button>
        </Space>
        {!audit || !audit.items?.length ? (
          <Empty description="暂无工具审计记录" />
        ) : (
          <Table
            rowKey={(row: any) => `${row.seq}-${row.event_type}`}
            dataSource={audit.items}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: '序号', dataIndex: 'seq', key: 'seq', width: 80 },
              { title: 'Agent', dataIndex: 'agent_name', key: 'agent_name', width: 180 },
              { title: '事件', dataIndex: 'event_type', key: 'event_type', width: 220 },
              {
                title: '时间',
                dataIndex: 'timestamp',
                key: 'timestamp',
                width: 220,
                render: (v: string) => formatBeijingDateTime(v),
              },
              {
                title: '详情',
                key: 'detail',
                render: (_: unknown, row: any) => <Text type="secondary">{String((row.payload || {}).message || '').slice(0, 160)}</Text>,
              },
            ]}
          />
        )}
      </Card>
    </div>
  );
};

export default ToolsCenterPage;

