import React, { useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Empty,
  Input,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { assetApi, type AssetFusion, type InterfaceLocateResult } from '@/services/api';

const { Paragraph, Title } = Typography;
const { TextArea } = Input;

const AssetsPage: React.FC = () => {
  const [incidentId, setIncidentId] = useState('');
  const [logContent, setLogContent] = useState('');
  const [symptom, setSymptom] = useState('');
  const [loading, setLoading] = useState(false);
  const [locateLoading, setLocateLoading] = useState(false);
  const [fusion, setFusion] = useState<AssetFusion | null>(null);
  const [locateResult, setLocateResult] = useState<InterfaceLocateResult | null>(null);

  const queryFusion = async () => {
    if (!incidentId.trim()) {
      message.error('请输入 Incident ID');
      return;
    }
    setLoading(true);
    try {
      const result = await assetApi.fusion(incidentId.trim());
      setFusion(result);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '查询失败');
    } finally {
      setLoading(false);
    }
  };

  const locateByLog = async () => {
    if (!logContent.trim()) {
      message.error('请输入接口报错日志');
      return;
    }
    setLocateLoading(true);
    try {
      const result = await assetApi.locate(logContent.trim(), symptom.trim() || undefined);
      setLocateResult(result);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '定位失败');
    } finally {
      setLocateLoading(false);
    }
  };

  const relationColumns: ColumnsType<AssetFusion['relationships'][number]> = [
    { title: '源ID', dataIndex: 'source_id', key: 'source_id' },
    { title: '源类型', dataIndex: 'source_type', key: 'source_type', width: 120 },
    { title: '关系', dataIndex: 'relation', key: 'relation', width: 180 },
    { title: '目标ID', dataIndex: 'target_id', key: 'target_id' },
    { title: '目标类型', dataIndex: 'target_type', key: 'target_type', width: 120 },
  ];

  const locateColumns: ColumnsType<NonNullable<InterfaceLocateResult['code_artifacts']>[number]> = [
    { title: '代码路径', dataIndex: 'path', key: 'path' },
    { title: '符号', dataIndex: 'symbol', key: 'symbol', width: 320 },
  ];

  const caseColumns: ColumnsType<NonNullable<InterfaceLocateResult['similar_cases']>[number]> = [
    { title: '案例ID', dataIndex: 'id', key: 'id', width: 140 },
    { title: '标题', dataIndex: 'title', key: 'title' },
    { title: '接口', dataIndex: 'api_endpoint', key: 'api_endpoint', width: 240 },
  ];

  return (
    <div className="assets-page">
      <Card className="module-card" style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginTop: 0, marginBottom: 8 }}>
          资产定位
        </Title>
        <Paragraph style={{ marginBottom: 0 }}>
          输入接口报错日志后，系统会映射到领域、聚合根、责任团队，并给出代码与数据库关联资产。
        </Paragraph>
      </Card>

      <Card className="module-card" title="接口日志定位（领域-聚合根）" style={{ marginBottom: 16 }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <TextArea
            rows={8}
            placeholder="粘贴接口报错日志，例如：ERROR POST /api/v1/orders failed ..."
            value={logContent}
            onChange={(e) => setLogContent(e.target.value)}
          />
          <Input
            placeholder="故障现象（可选），例如：下单失败、支付确认失败"
            value={symptom}
            onChange={(e) => setSymptom(e.target.value)}
          />
          <Space>
            <Button type="primary" loading={locateLoading} onClick={locateByLog}>
              定位领域与责任田
            </Button>
            <Button
              onClick={() => {
                setLogContent('');
                setSymptom('');
                setLocateResult(null);
              }}
            >
              清空
            </Button>
          </Space>

          {!locateResult ? (
            <Empty description="输入日志并点击“定位领域与责任田”后展示结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <>
              <Alert type={locateResult.matched ? 'success' : 'warning'} message={locateResult.reason} showIcon />
              <Descriptions bordered column={2} style={{ marginTop: 8 }}>
                <Descriptions.Item label="匹配状态">
                  <Tag color={locateResult.matched ? 'success' : 'warning'}>
                    {locateResult.matched ? '已命中' : '未命中'}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="置信度">{(locateResult.confidence * 100).toFixed(1)}%</Descriptions.Item>
                <Descriptions.Item label="领域">{locateResult.domain || '-'}</Descriptions.Item>
                <Descriptions.Item label="聚合根">{locateResult.aggregate || '-'}</Descriptions.Item>
                <Descriptions.Item label="责任团队">{locateResult.owner_team || '-'}</Descriptions.Item>
                <Descriptions.Item label="负责人">{locateResult.owner || '-'}</Descriptions.Item>
                <Descriptions.Item label="命中接口" span={2}>
                  {locateResult.matched_endpoint
                    ? `${locateResult.matched_endpoint.method} ${locateResult.matched_endpoint.path} (${locateResult.matched_endpoint.interface || '-'})`
                    : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="数据库表" span={2}>
                  {locateResult.db_tables.join(', ') || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="设计文档引用" span={2}>
                  {locateResult.design_ref
                    ? `${locateResult.design_ref.doc} / ${locateResult.design_ref.section}`
                    : '-'}
                </Descriptions.Item>
              </Descriptions>

              {!locateResult.matched && locateResult.guidance?.length > 0 && (
                <Alert
                  type="info"
                  showIcon
                  message={`补充建议：${locateResult.guidance.join('；')}`}
                  style={{ marginTop: 12 }}
                />
              )}

              <Table
                style={{ marginTop: 12 }}
                rowKey={(row, index) => `${row.path}-${row.symbol}-${index}`}
                columns={locateColumns}
                dataSource={locateResult.code_artifacts}
                pagination={false}
                locale={{ emptyText: '未返回关联代码' }}
              />
              <Table
                style={{ marginTop: 12 }}
                rowKey={(row) => row.id}
                columns={caseColumns}
                dataSource={locateResult.similar_cases}
                pagination={false}
                locale={{ emptyText: '未命中相似案例' }}
              />
            </>
          )}
        </Space>
      </Card>

      <Card className="module-card" title="三态资产融合图谱">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Input
              placeholder="输入 Incident ID"
              value={incidentId}
              style={{ width: 320 }}
              onChange={(e) => setIncidentId(e.target.value)}
            />
            <Button type="primary" loading={loading} onClick={queryFusion}>
              查询融合结果
            </Button>
          </Space>

          {!fusion ? (
            <Empty description="输入 Incident ID 后可查看融合图谱结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <>
              <Descriptions bordered column={2}>
                <Descriptions.Item label="Incident">{fusion.incident_id}</Descriptions.Item>
                <Descriptions.Item label="Debate Session">{fusion.debate_session_id}</Descriptions.Item>
                <Descriptions.Item label="运行态资产">{fusion.runtime_assets.length}</Descriptions.Item>
                <Descriptions.Item label="开发态资产">{fusion.dev_assets.length}</Descriptions.Item>
                <Descriptions.Item label="设计态资产">{fusion.design_assets.length}</Descriptions.Item>
                <Descriptions.Item label="关联关系">{fusion.relationships.length}</Descriptions.Item>
              </Descriptions>
              <Divider style={{ margin: '8px 0' }} />
              <Table
                rowKey={(row, index) => `${row.source_id}-${row.target_id}-${index}`}
                columns={relationColumns}
                dataSource={fusion.relationships}
                pagination={{ pageSize: 10 }}
                locale={{ emptyText: '暂无关系数据' }}
              />
            </>
          )}
        </Space>
      </Card>
    </div>
  );
};

export default AssetsPage;
