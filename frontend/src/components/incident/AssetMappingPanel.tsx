import React, { useMemo } from 'react';
import { Card, Col, Descriptions, Empty, Row, Space, Statistic, Tag, Typography } from 'antd';

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

const { Text } = Typography;

const AssetMappingPanel: React.FC<Props> = ({ mappingItems, mappingEmptyHint }) => {
  const summary = useMemo(() => {
    const total = mappingItems.length;
    const hit = mappingItems.filter((item) => item.matched === '命中').length;
    const miss = Math.max(0, total - hit);
    const uniqueTeams = new Set(
      mappingItems
        .map((item) => item.ownerTeam)
        .filter((value) => value && value !== '-'),
    ).size;
    const hitRate = total > 0 ? Number(((hit / total) * 100).toFixed(1)) : 0;
    return { total, hit, miss, uniqueTeams, hitRate };
  }, [mappingItems]);

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="module-card" title="责任田映射结果" extra={<Tag color="blue">资产阶段</Tag>}>
        <Row gutter={[12, 12]}>
          <Col xs={12} md={6}>
            <Statistic title="映射记录" value={summary.total} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="命中数" value={summary.hit} valueStyle={{ color: '#1677ff' }} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="命中率" value={summary.hitRate} suffix="%" precision={1} />
          </Col>
          <Col xs={12} md={6}>
            <Statistic title="涉及团队" value={summary.uniqueTeams} />
          </Col>
        </Row>
      </Card>

      <Card className="module-card" title="映射明细">
        {mappingItems.length === 0 ? (
          <Empty
            description={
              <Space direction="vertical" size={2}>
                <Text>{mappingEmptyHint}</Text>
                <Text type="secondary">建议补充接口 URL、traceId、报错堆栈后再次分析。</Text>
              </Space>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {mappingItems.map((item) => (
              <Card key={item.id} size="small" className="asset-map-item-card">
                <Descriptions column={2} size="small" styles={{ label: { width: 96 } }}>
                  <Descriptions.Item label="时间">{item.timeText}</Descriptions.Item>
                  <Descriptions.Item label="匹配状态">
                    <Tag color={item.matched === '命中' ? 'success' : 'warning'}>{item.matched}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="领域">{item.domain}</Descriptions.Item>
                  <Descriptions.Item label="聚合根">{item.aggregate}</Descriptions.Item>
                  <Descriptions.Item label="责任团队">{item.ownerTeam}</Descriptions.Item>
                  <Descriptions.Item label="责任人">{item.owner}</Descriptions.Item>
                  <Descriptions.Item label="置信度">{item.confidence}</Descriptions.Item>
                  <Descriptions.Item label="映射依据">{item.reason}</Descriptions.Item>
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
