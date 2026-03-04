import React from 'react';
import { Button, Card, Empty, Input, Space, Table, Typography } from 'antd';
import type { ToolAuditResponse } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Text } = Typography;

type Props = {
  sessionId: string;
  onSessionIdChange: (value: string) => void;
  loading: boolean;
  audit: ToolAuditResponse | null;
  onLoad: () => Promise<void>;
  onOpenRef?: (refId: string) => Promise<void>;
};

const ToolAuditPanel: React.FC<Props> = ({ sessionId, onSessionIdChange, loading, audit, onLoad, onOpenRef }) => {
  return (
    <Card className="module-card" title="会话级工具调用审计">
      <Space wrap style={{ marginBottom: 12 }}>
        <Input
          value={sessionId}
          onChange={(e) => onSessionIdChange(e.target.value)}
          placeholder="输入会话ID（deb_xxx）"
          style={{ width: 320 }}
        />
        <Button type="primary" loading={loading} onClick={() => void onLoad()}>
          查询审计
        </Button>
      </Space>
      {!audit || !audit.items?.length ? (
        <Empty description="暂无工具审计记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Table
          rowKey={(row: any) => `${row.seq}-${row.event_type}`}
          dataSource={audit.items}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: '序号', dataIndex: 'seq', key: 'seq', width: 80 },
            { title: 'Agent', dataIndex: 'agent_name', key: 'agent_name', width: 180 },
            { title: '工具事件', dataIndex: 'event_type', key: 'event_type', width: 220 },
            {
              title: '状态',
              key: 'status',
              width: 120,
              render: (_: unknown, row: any) => <Text>{String((row.payload || {}).status || '-')}</Text>,
            },
            {
              title: '耗时(ms)',
              key: 'duration_ms',
              width: 120,
              render: (_: unknown, row: any) => <Text>{String((row.payload || {}).duration_ms || '-')}</Text>,
            },
            {
              title: '时间',
              dataIndex: 'timestamp',
              key: 'timestamp',
              width: 220,
              render: (v: string) => formatBeijingDateTime(v),
            },
            {
              title: '请求/响应',
              key: 'detail',
              render: (_: unknown, row: any) => (
                <Space direction="vertical" size={2}>
                  <Text type="secondary">
                    request={String(JSON.stringify((row.payload || {}).request || {})).slice(0, 120) || '{}'}
                  </Text>
                  <Text type="secondary">
                    response={String(JSON.stringify((row.payload || {}).response || {})).slice(0, 120) || '{}'}
                  </Text>
                  {String((row.payload || {}).error || '').trim() ? (
                    <Text type="danger">{String((row.payload || {}).error || '').slice(0, 120)}</Text>
                  ) : null}
                  {String((row.payload || {}).ref_id || '').trim() ? (
                    <Button
                      type="link"
                      size="small"
                      style={{ paddingInline: 0 }}
                      onClick={() => void onOpenRef?.(String((row.payload || {}).ref_id || '').trim())}
                    >
                      查看完整输出
                    </Button>
                  ) : null}
                </Space>
              ),
            },
          ]}
        />
      )}
    </Card>
  );
};

export default ToolAuditPanel;
