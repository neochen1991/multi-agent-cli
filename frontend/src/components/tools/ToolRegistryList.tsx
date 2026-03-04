import React from 'react';
import { Card, Empty, List, Space, Tag, Typography } from 'antd';
import type { ToolRegistryItem } from '@/services/api';

const { Text } = Typography;

type Props = {
  loading: boolean;
  items: ToolRegistryItem[];
  selectedToolName: string;
  onSelect: (toolName: string) => void;
};

const ToolRegistryList: React.FC<Props> = ({ loading, items, selectedToolName, onSelect }) => {
  return (
    <Card className="module-card" title="工具列表" loading={loading}>
      {items.length === 0 ? (
        <Empty description="暂无工具注册信息" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => {
            const selected = item.tool_name === selectedToolName;
            return (
              <List.Item
                onClick={() => onSelect(item.tool_name)}
                style={{
                  cursor: 'pointer',
                  borderRadius: 8,
                  paddingInline: 10,
                  background: selected ? '#eef4ff' : undefined,
                  border: selected ? '1px solid #cfe0ff' : '1px solid transparent',
                }}
              >
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <Space wrap>
                    <Text strong>{item.tool_name}</Text>
                    <Tag color={item.enabled ? 'success' : 'default'}>{item.enabled ? 'enabled' : 'disabled'}</Tag>
                  </Space>
                  <Text type="secondary">owner={item.owner_agent} · category={item.category}</Text>
                </Space>
              </List.Item>
            );
          }}
        />
      )}
    </Card>
  );
};

export default ToolRegistryList;
