import React from 'react';
import { Card, Empty, List, Space, Tag, Typography } from 'antd';
import type { ToolConnector, ToolRegistryItem } from '@/services/api';

const { Text } = Typography;

const toJson = (value: unknown): string => {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value || '');
  }
};

const extractConnectorTools = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean);
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
};

type Props = {
  selectedTool: ToolRegistryItem | null;
  connectorsForSelected: ToolConnector[];
};

const ToolDetailPanel: React.FC<Props> = ({ selectedTool, connectorsForSelected }) => {
  return (
    <Card className="module-card" title="工具详情与连接器映射">
      {!selectedTool ? (
        <Empty description="请选择左侧工具查看详情" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="blue">{selectedTool.tool_name}</Tag>
            <Tag>{selectedTool.owner_agent}</Tag>
            <Tag color={selectedTool.enabled ? 'success' : 'default'}>{selectedTool.enabled ? 'enabled' : 'disabled'}</Tag>
          </Space>
          <Text type="secondary">输入参数定义：</Text>
          <pre className="dialogue-content">{toJson(selectedTool.input_schema || {})}</pre>
          <Text type="secondary">执行策略：</Text>
          <pre className="dialogue-content">{toJson(selectedTool.policy || {})}</pre>
          <Text type="secondary">连接器映射：</Text>
          {connectorsForSelected.length === 0 ? (
            <Text type="secondary">暂无连接器映射。</Text>
          ) : (
            <List
              size="small"
              dataSource={connectorsForSelected}
              renderItem={(row) => (
                <List.Item>
                  <Space direction="vertical" size={0}>
                    <Text>{String(row.name || '-')}</Text>
                    <Text type="secondary">
                      resource={String(row.resource || '-')} · tools={extractConnectorTools(row.tools).join(', ')}
                    </Text>
                  </Space>
                </List.Item>
              )}
            />
          )}
        </Space>
      )}
    </Card>
  );
};

export default ToolDetailPanel;
