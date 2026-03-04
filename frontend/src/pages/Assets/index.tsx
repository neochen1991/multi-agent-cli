import React, { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { assetApi, incidentApi, type AssetFusion, type InterfaceLocateResult } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Title } = Typography;
const { TextArea } = Input;

type AssetPreviewRow = {
  key: string;
  asset_id: string;
  asset_type: string;
  service: string;
  summary: string;
};

const toAssetRows = (assets: Record<string, unknown>[], prefix: string): AssetPreviewRow[] => {
  return (assets || []).slice(0, 20).map((row, index) => {
    const id = String(row.id || row.asset_id || row.name || row.path || `${prefix}-${index + 1}`);
    const type = String(row.type || row.asset_type || row.category || '-');
    const service = String(row.service || row.service_name || row.domain || '-');
    const summary = String(row.summary || row.description || row.interface || row.table || row.path || '-');
    return {
      key: `${prefix}-${id}-${index}`,
      asset_id: id,
      asset_type: type,
      service,
      summary,
    };
  });
};

const normalizeSourceLabel = (item: unknown): string => {
  if (typeof item === 'string') return item;
  if (item && typeof item === 'object') {
    const row = item as Record<string, unknown>;
    return String(row.name || row.source || row.id || row.type || 'unknown');
  }
  return String(item || 'unknown');
};

const AssetsPage: React.FC = () => {
  const [incidentId, setIncidentId] = useState('');
  const [logContent, setLogContent] = useState('');
  const [symptom, setSymptom] = useState('');
  const [loading, setLoading] = useState(false);
  const [locateLoading, setLocateLoading] = useState(false);
  const [fusion, setFusion] = useState<AssetFusion | null>(null);
  const [locateResult, setLocateResult] = useState<InterfaceLocateResult | null>(null);
  const [resourceSources, setResourceSources] = useState<Record<string, unknown>>({});
  const [recentIncidentOptions, setRecentIncidentOptions] = useState<Array<{ label: string; value: string }>>([]);

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const [payload, incidents] = await Promise.all([assetApi.resources(), incidentApi.list(1, 30)]);
        setResourceSources(payload || {});
        const options = (incidents.items || []).map((item) => ({
          value: item.id,
          label: `${item.id} · ${item.title} · ${formatBeijingDateTime(item.created_at)}`,
        }));
        setRecentIncidentOptions(options);
      } catch {
        // ignore bootstrap errors; page keeps manual input workflow
      }
    };
    void bootstrap();
  }, []);

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

  const assetPreviewColumns: ColumnsType<AssetPreviewRow> = [
    { title: '资产ID', dataIndex: 'asset_id', key: 'asset_id' },
    { title: '类型', dataIndex: 'asset_type', key: 'asset_type', width: 120 },
    { title: '服务/领域', dataIndex: 'service', key: 'service', width: 180 },
    { title: '摘要', dataIndex: 'summary', key: 'summary', ellipsis: true },
  ];

  const enabledSources = Array.isArray(resourceSources.enabled_sources)
    ? (resourceSources.enabled_sources as unknown[]).map((item) => normalizeSourceLabel(item))
    : [];
  const optionalSources = Array.isArray(resourceSources.optional_external_sources)
    ? (resourceSources.optional_external_sources as unknown[]).map((item) => normalizeSourceLabel(item))
    : [];
  const runtimeRows = toAssetRows(fusion?.runtime_assets || [], 'runtime');
  const devRows = toAssetRows(fusion?.dev_assets || [], 'dev');
  const designRows = toAssetRows(fusion?.design_assets || [], 'design');

  return (
    <div className="assets-page">
      <Card className="module-card" style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginTop: 0, marginBottom: 8 }}>
          资产映射与图谱中心
        </Title>
        <Paragraph style={{ marginBottom: 0 }}>
          这个页面用于回答两个问题：1）这个报错归属哪个领域与责任田；2）该故障涉及哪些运行态、开发态、设计态资产。
        </Paragraph>
        <Space wrap style={{ marginTop: 8 }}>
          <Tag color="processing">模式：{String(resourceSources.mode || 'local-first')}</Tag>
          <Tag color={enabledSources.length > 0 ? 'success' : 'default'}>已启用数据源：{enabledSources.length}</Tag>
          <Tag color={optionalSources.length > 0 ? 'warning' : 'default'}>可选外部源：{optionalSources.length}</Tag>
        </Space>
        {enabledSources.length > 0 ? (
          <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
            当前启用：{enabledSources.join('、')}
          </Paragraph>
        ) : null}
      </Card>

      <Card className="module-card">
        <Tabs
          defaultActiveKey="mapping"
          items={[
            {
              key: 'mapping',
              label: '资产映射',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Paragraph style={{ marginBottom: 0 }}>
                    输入报错日志后，系统会定位领域、聚合根、责任团队，并返回代码和数据库关联点。
                  </Paragraph>
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
                  <Space wrap>
                    <Button type="primary" loading={locateLoading} onClick={locateByLog}>
                      定位领域与责任田
                    </Button>
                    <Button
                      onClick={() => {
                        setLogContent(`2026-02-20T14:01:38.124+08:00 ERROR upstream timeout, status=502, uri=/api/v1/orders, costMs=30211
2026-02-20T14:01:38.095+08:00 ERROR HikariPool-1 - Connection is not available, request timed out after 30000ms.`);
                        setSymptom('订单创建超时，502比例上升');
                      }}
                    >
                      填充示例日志
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
                    <Empty
                      description="暂无映射结果。输入日志并点击“定位领域与责任田”后，将显示责任团队、接口、代码和数据库映射信息。"
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                    />
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
              ),
            },
            {
              key: 'graph',
              label: '资产图谱',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Paragraph style={{ marginBottom: 0 }}>
                    资产图谱用于把同一故障下的运行态、代码态、设计态资产串联成关系图，帮助判断影响面和归责链路。
                  </Paragraph>
                  <Space wrap>
                    <Select
                      showSearch
                      allowClear
                      placeholder="选择最近 Incident"
                      style={{ minWidth: 420 }}
                      options={recentIncidentOptions}
                      value={incidentId || undefined}
                      onChange={(value) => setIncidentId(String(value || ''))}
                    />
                    <Input
                      placeholder="或手动输入 Incident ID"
                      value={incidentId}
                      style={{ width: 280 }}
                      onChange={(e) => setIncidentId(e.target.value)}
                    />
                    <Button type="primary" loading={loading} onClick={queryFusion}>
                      查询融合结果
                    </Button>
                  </Space>

                  {!fusion ? (
                    <Empty
                      description="暂无图谱结果。请选择 Incident 并查询后，可看到三态资产清单和它们之间的关系。"
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                    />
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
                        pagination={{ pageSize: 8 }}
                        locale={{ emptyText: '暂无关系数据' }}
                      />
                      <Table
                        style={{ marginTop: 12 }}
                        columns={assetPreviewColumns}
                        dataSource={runtimeRows}
                        pagination={false}
                        title={() => '运行态资产（节选）'}
                        locale={{ emptyText: '暂无运行态资产' }}
                      />
                      <Table
                        style={{ marginTop: 12 }}
                        columns={assetPreviewColumns}
                        dataSource={devRows}
                        pagination={false}
                        title={() => '开发态资产（节选）'}
                        locale={{ emptyText: '暂无开发态资产' }}
                      />
                      <Table
                        style={{ marginTop: 12 }}
                        columns={assetPreviewColumns}
                        dataSource={designRows}
                        pagination={false}
                        title={() => '设计态资产（节选）'}
                        locale={{ emptyText: '暂无设计态资产' }}
                      />
                    </>
                  )}
                </Space>
              ),
            },
            {
              key: 'guide',
              label: '使用说明',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Alert
                    type="info"
                    showIcon
                    message="建议流程：先做“资产映射”定位责任田，再看“资产图谱”判断影响面，最后回到辩论过程核对证据链。"
                  />
                  <Descriptions bordered column={1}>
                    <Descriptions.Item label="资产映射页回答什么问题">
                      某条报错日志属于哪个领域/聚合根/责任团队，以及对应代码文件和数据库表是什么。
                    </Descriptions.Item>
                    <Descriptions.Item label="资产图谱页回答什么问题">
                      故障涉及哪些跨层资产，哪些资产之间存在依赖或影响关系，应该优先验证哪条链路。
                    </Descriptions.Item>
                    <Descriptions.Item label="输入建议">
                      日志里尽量包含接口路径、状态码、traceId、异常类名，能显著提升映射命中率。
                    </Descriptions.Item>
                  </Descriptions>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default AssetsPage;
