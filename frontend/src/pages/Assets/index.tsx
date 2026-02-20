import React, { useState } from 'react';
import { Alert, Button, Card, Descriptions, Divider, Input, Space, Table, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { assetApi, type AssetFusion, type InterfaceLocateResult } from '@/services/api';

const { Title, Text } = Typography;
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

  const columns: ColumnsType<AssetFusion['relationships'][number]> = [
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

  return (
    <div className="assets-page">
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            资产图谱
          </Title>
          <Space>
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

          <Divider style={{ margin: '8px 0' }} />

          <Title level={5} style={{ margin: 0 }}>
            接口日志定位（领域-聚合根）
          </Title>
          <TextArea
            rows={6}
            placeholder="粘贴接口报错日志，例如：ERROR POST /api/v1/orders failed with NullPointerException ..."
            value={logContent}
            onChange={(e) => setLogContent(e.target.value)}
          />
          <Input
            placeholder="故障现象（可选），例如：下单失败、支付确认失败"
            value={symptom}
            onChange={(e) => setSymptom(e.target.value)}
          />
          <Button type="primary" loading={locateLoading} onClick={locateByLog}>
            定位领域与责任田
          </Button>

          {!fusion && <Text type="secondary">输入 Incident ID 后可查看三态资产融合图谱。</Text>}

          {fusion && (
            <>
              <Descriptions bordered column={2}>
                <Descriptions.Item label="Incident">{fusion.incident_id}</Descriptions.Item>
                <Descriptions.Item label="Debate Session">{fusion.debate_session_id}</Descriptions.Item>
                <Descriptions.Item label="运行态资产">{fusion.runtime_assets.length}</Descriptions.Item>
                <Descriptions.Item label="开发态资产">{fusion.dev_assets.length}</Descriptions.Item>
                <Descriptions.Item label="设计态资产">{fusion.design_assets.length}</Descriptions.Item>
                <Descriptions.Item label="关联关系">{fusion.relationships.length}</Descriptions.Item>
              </Descriptions>
              <Table
                rowKey={(row, index) => `${row.source_id}-${row.target_id}-${index}`}
                columns={columns}
                dataSource={fusion.relationships}
                pagination={{ pageSize: 10 }}
              />
            </>
          )}

          {locateResult && (
            <>
              <Divider />
              <Alert
                type={locateResult.matched ? 'success' : 'warning'}
                message={locateResult.reason}
                showIcon
              />
              <Descriptions bordered column={2} style={{ marginTop: 16 }}>
                <Descriptions.Item label="匹配状态">
                  {locateResult.matched ? '已命中' : '未命中'}
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
                  style={{ marginTop: 12 }}
                  type="info"
                  showIcon
                  message={`补充建议：${locateResult.guidance.join('；')}`}
                />
              )}

              <Table
                style={{ marginTop: 16 }}
                rowKey={(row, index) => `${row.path}-${row.symbol}-${index}`}
                columns={locateColumns}
                dataSource={locateResult.code_artifacts}
                pagination={false}
              />

              <Table
                style={{ marginTop: 16 }}
                rowKey={(row) => row.id}
                columns={caseColumns}
                dataSource={locateResult.similar_cases}
                pagination={false}
              />
            </>
          )}
        </Space>
      </Card>
    </div>
  );
};

export default AssetsPage;
