import React from 'react';
import { Card, Descriptions, Empty, Space, Tag } from 'antd';

export type MappingItem = {
  id: string;
  timeText: string;
  matched: string;
  domain: string;
  aggregate: string;
  ownerTeam: string;
  owner: string;
  confidence: string;
  reason: string;
};

type Props = {
  mappingItems: MappingItem[];
  mappingEmptyHint: string;
};

const AssetMappingPanel: React.FC<Props> = ({ mappingItems, mappingEmptyHint }) => {
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="责任田映射结果">
        {mappingItems.length === 0 ? (
          <Empty description={mappingEmptyHint} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {mappingItems.map((item) => (
              <Card key={item.id} size="small">
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="时间">{item.timeText}</Descriptions.Item>
                  <Descriptions.Item label="匹配状态">
                    <Tag color={item.matched === '命中' ? 'success' : 'warning'}>{item.matched}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="领域">{item.domain}</Descriptions.Item>
                  <Descriptions.Item label="聚合根">{item.aggregate}</Descriptions.Item>
                  <Descriptions.Item label="责任团队">{item.ownerTeam}</Descriptions.Item>
                  <Descriptions.Item label="责任人">{item.owner}</Descriptions.Item>
                  <Descriptions.Item label="置信度">{item.confidence}</Descriptions.Item>
                  <Descriptions.Item label="匹配原因">{item.reason}</Descriptions.Item>
                </Descriptions>
              </Card>
            ))}
          </Space>
        )}
      </Card>
    </Space>
  );
};

export default AssetMappingPanel;
