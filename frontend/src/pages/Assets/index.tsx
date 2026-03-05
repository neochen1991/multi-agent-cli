import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { UploadProps } from 'antd';
import {
  assetApi,
  type InterfaceLocateResult,
  type ResponsibilityAssetRecord,
} from '@/services/api';

const { Paragraph, Title, Text } = Typography;
const { TextArea } = Input;

type ManualAssetForm = {
  asset_id?: string;
  feature: string;
  domain: string;
  aggregate: string;
  frontend_pages: string;
  api_interfaces: string;
  code_items: string;
  database_tables: string;
  dependency_services: string;
  monitor_items: string;
  owner_team: string;
  owner: string;
};

const splitListText = (value: string): string[] =>
  String(value || '')
    .split(/[,，;\n；、|]+/)
    .map((x) => x.trim())
    .filter(Boolean);

const joinListText = (items: string[]): string => (items || []).join('、');

const csvEscape = (value: unknown): string => {
  const text = String(value ?? '');
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
};

const AssetsPage: React.FC = () => {
  const [records, setRecords] = useState<ResponsibilityAssetRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [latestUpdatedAt, setLatestUpdatedAt] = useState('');
  const [storagePath, setStoragePath] = useState('');
  const [uploading, setUploading] = useState(false);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [filterText, setFilterText] = useState('');
  const [filterDomain, setFilterDomain] = useState('');
  const [filterAggregate, setFilterAggregate] = useState('');
  const [filterApi, setFilterApi] = useState('');
  const [schemaTips, setSchemaTips] = useState<string[]>([]);
  const [manualForm, setManualForm] = useState<ManualAssetForm>({
    asset_id: '',
    feature: '',
    domain: '',
    aggregate: '',
    frontend_pages: '',
    api_interfaces: '',
    code_items: '',
    database_tables: '',
    dependency_services: '',
    monitor_items: '',
    owner_team: '',
    owner: '',
  });
  const [editingAssetId, setEditingAssetId] = useState('');
  const [savingManual, setSavingManual] = useState(false);

  const [locateLoading, setLocateLoading] = useState(false);
  const [logContent, setLogContent] = useState('');
  const [symptom, setSymptom] = useState('');
  const [locateResult, setLocateResult] = useState<InterfaceLocateResult | null>(null);

  const loadAssets = async () => {
    setLoading(true);
    try {
      const data = await assetApi.listResponsibilityAssets({
        q: filterText || undefined,
        domain: filterDomain || undefined,
        aggregate: filterAggregate || undefined,
        api: filterApi || undefined,
      });
      setRecords(data.items || []);
      setTotal(Number(data.total || 0));
      if ((data.items || []).length > 0) {
        const latest = (data.items || [])
          .map((x) => String(x.updated_at || ''))
          .sort()
          .reverse()[0];
        setLatestUpdatedAt(latest || '');
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '加载责任田资产失败');
    } finally {
      setLoading(false);
    }
  };

  const loadAssetStats = async () => {
    try {
      const payload = await assetApi.resources();
      const summary =
        payload && typeof payload.responsibility_assets === 'object'
          ? (payload.responsibility_assets as Record<string, unknown>)
          : {};
      const ts = String(summary.latest_updated_at || '').trim();
      const path = String(summary.storage_path || '').trim();
      if (ts) setLatestUpdatedAt(ts);
      if (path) setStoragePath(path);
    } catch {
      // ignore
    }
  };

  const loadSchema = async () => {
    try {
      const data = await assetApi.responsibilitySchema();
      const tips = Array.isArray(data.tips) ? data.tips.map((x) => String(x)) : [];
      setSchemaTips(tips);
    } catch {
      setSchemaTips([]);
    }
  };

  useEffect(() => {
    void loadAssets();
    void loadSchema();
    void loadAssetStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const domainOptions = useMemo(() => {
    const seen = new Set<string>();
    const options: Array<{ label: string; value: string }> = [];
    for (const row of records) {
      const key = String(row.domain || '').trim();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      options.push({ label: key, value: key });
    }
    return options;
  }, [records]);

  const aggregateOptions = useMemo(() => {
    const seen = new Set<string>();
    const options: Array<{ label: string; value: string }> = [];
    for (const row of records) {
      const key = String(row.aggregate || '').trim();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      options.push({ label: key, value: key });
    }
    return options;
  }, [records]);

  const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
    setUploading(true);
    try {
      const result = await assetApi.uploadResponsibilityAssets(file as File, replaceExisting);
      message.success(`导入完成：导入 ${result.imported} 条，当前存量 ${result.stored} 条`);
      await loadAssets();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '导入失败');
    } finally {
      setUploading(false);
    }
    return false;
  };

  const handleSaveManual = async () => {
    if (!manualForm.domain.trim() || !manualForm.aggregate.trim() || !manualForm.api_interfaces.trim()) {
      message.warning('请至少填写：领域、聚合根、API 接口');
      return;
    }
    setSavingManual(true);
    try {
      await assetApi.upsertResponsibilityAsset({
        asset_id: manualForm.asset_id?.trim() || undefined,
        feature: manualForm.feature.trim(),
        domain: manualForm.domain.trim(),
        aggregate: manualForm.aggregate.trim(),
        frontend_pages: splitListText(manualForm.frontend_pages),
        api_interfaces: splitListText(manualForm.api_interfaces),
        code_items: splitListText(manualForm.code_items),
        database_tables: splitListText(manualForm.database_tables),
        dependency_services: splitListText(manualForm.dependency_services),
        monitor_items: splitListText(manualForm.monitor_items),
        owner_team: manualForm.owner_team.trim(),
        owner: manualForm.owner.trim(),
      });
      message.success('已保存责任田资产');
      setManualForm({
        asset_id: '',
        feature: '',
        domain: '',
        aggregate: '',
        frontend_pages: '',
        api_interfaces: '',
        code_items: '',
        database_tables: '',
        dependency_services: '',
        monitor_items: '',
        owner_team: '',
        owner: '',
      });
      setEditingAssetId('');
      await loadAssets();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '保存失败');
    } finally {
      setSavingManual(false);
    }
  };

  const resetManualForm = () => {
    setManualForm({
      asset_id: '',
      feature: '',
      domain: '',
      aggregate: '',
      frontend_pages: '',
      api_interfaces: '',
      code_items: '',
      database_tables: '',
      dependency_services: '',
      monitor_items: '',
      owner_team: '',
      owner: '',
    });
    setEditingAssetId('');
  };

  const startEdit = (row: ResponsibilityAssetRecord) => {
    setEditingAssetId(row.asset_id);
    setManualForm({
      asset_id: row.asset_id,
      feature: row.feature || '',
      domain: row.domain || '',
      aggregate: row.aggregate || '',
      frontend_pages: (row.frontend_pages || []).join(', '),
      api_interfaces: (row.api_interfaces || []).join(', '),
      code_items: (row.code_items || []).join(', '),
      database_tables: (row.database_tables || []).join(', '),
      dependency_services: (row.dependency_services || []).join(', '),
      monitor_items: (row.monitor_items || []).join(', '),
      owner_team: row.owner_team || '',
      owner: row.owner || '',
    });
  };

  const handleDelete = async (assetId: string) => {
    try {
      await assetApi.deleteResponsibilityAsset(assetId);
      message.success(`已删除 ${assetId}`);
      await loadAssets();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '删除失败');
    }
  };

  const downloadTemplate = () => {
    const headers = [
      '特性',
      '领域',
      '聚合根',
      '前端页面',
      'api接口',
      '代码清单',
      '数据库表',
      '依赖服务',
      '监控清单',
      '责任团队',
      '负责人',
    ];
    const sample = [
      '下单',
      'order',
      'OrderAggregate',
      '订单创建页,/order/create',
      'POST /api/v1/orders,GET /api/v1/orders/{id}',
      'OrderController#createOrder,OrderAppService#createOrder',
      't_order,t_order_item,t_inventory',
      'inventory-service,payment-service',
      'orders_5xx_rate,hikari_pending_threads,db_lock_wait',
      'order-domain-team',
      'alice',
    ];
    const csv = [headers, sample].map((row) => row.map(csvEscape).join(',')).join('\n');
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '责任田资产模板.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportCurrentRecords = () => {
    if (!records.length) {
      message.info('暂无可导出数据');
      return;
    }
    const headers = [
      'asset_id',
      'feature',
      'domain',
      'aggregate',
      'frontend_pages',
      'api_interfaces',
      'code_items',
      'database_tables',
      'dependency_services',
      'monitor_items',
      'owner_team',
      'owner',
      'updated_at',
    ];
    const rows = records.map((row) => [
      row.asset_id,
      row.feature,
      row.domain,
      row.aggregate,
      (row.frontend_pages || []).join(';'),
      (row.api_interfaces || []).join(';'),
      (row.code_items || []).join(';'),
      (row.database_tables || []).join(';'),
      (row.dependency_services || []).join(';'),
      (row.monitor_items || []).join(';'),
      row.owner_team,
      row.owner,
      row.updated_at,
    ]);
    const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(',')).join('\n');
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '责任田资产导出.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const locateByLog = async () => {
    if (!logContent.trim()) {
      message.error('请输入报错日志');
      return;
    }
    setLocateLoading(true);
    try {
      const result = await assetApi.locate(logContent.trim(), symptom.trim() || undefined);
      setLocateResult(result);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '定位失败');
    } finally {
      setLocateLoading(false);
    }
  };

  const columns: ColumnsType<ResponsibilityAssetRecord> = [
    { title: '特性', dataIndex: 'feature', key: 'feature', width: 140 },
    { title: '领域', dataIndex: 'domain', key: 'domain', width: 140 },
    { title: '聚合根', dataIndex: 'aggregate', key: 'aggregate', width: 160 },
    {
      title: 'API 接口',
      dataIndex: 'api_interfaces',
      key: 'api_interfaces',
      width: 280,
      render: (items: string[]) => <Text>{joinListText(items)}</Text>,
    },
    {
      title: '数据库表',
      dataIndex: 'database_tables',
      key: 'database_tables',
      width: 220,
      render: (items: string[]) => <Text>{joinListText(items)}</Text>,
    },
    {
      title: '依赖服务',
      dataIndex: 'dependency_services',
      key: 'dependency_services',
      width: 220,
      render: (items: string[]) => <Text>{joinListText(items)}</Text>,
    },
    {
      title: '监控清单',
      dataIndex: 'monitor_items',
      key: 'monitor_items',
      width: 240,
      render: (items: string[]) => <Text>{joinListText(items)}</Text>,
    },
    {
      title: '责任人',
      key: 'owner',
      width: 180,
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text>{row.owner_team || '-'}</Text>
          <Text type="secondary">{row.owner || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      fixed: 'right',
      render: (_, row) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => startEdit(row)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除这条责任田资产？"
            onConfirm={() => void handleDelete(row.asset_id)}
          >
            <Button type="link" danger size="small">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const locateColumns: ColumnsType<NonNullable<InterfaceLocateResult['code_artifacts']>[number]> = [
    { title: '代码路径', dataIndex: 'path', key: 'path' },
    { title: '符号', dataIndex: 'symbol', key: 'symbol', width: 340 },
  ];

  return (
    <div className="assets-page">
      <Card className="module-card" style={{ marginBottom: 16 }}>
        <Title level={4} style={{ marginTop: 0, marginBottom: 8 }}>
          责任田资产中心
        </Title>
        <Paragraph style={{ marginBottom: 8 }}>
          维护并使用责任田资产：特性、领域、聚合根、前端页面、API 接口、代码清单、数据库表、依赖服务、监控清单。
        </Paragraph>
        <Space wrap>
          <Tag color="processing">本地存储</Tag>
          <Tag color="success">当前记录：{total}</Tag>
        </Space>
      </Card>

      <Card className="module-card">
        <Tabs
          defaultActiveKey="saved"
          items={[
            {
              key: 'ownership',
              label: '资产维护',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Alert
                    type="info"
                    showIcon
                    message="上传责任田 Excel/CSV 后，系统会用于接口故障责任田定位；也可手工新增/维护单条记录。"
                  />
                  {schemaTips.length > 0 ? (
                    <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                      {schemaTips.join('；')}
                    </Paragraph>
                  ) : null}

                  <Space wrap>
                    <Upload
                      accept=".xlsx,.xlsm,.xltx,.xltm,.csv"
                      beforeUpload={beforeUpload}
                      showUploadList={false}
                      maxCount={1}
                    >
                      <Button type="primary" loading={uploading}>
                        上传责任田 Excel/CSV
                      </Button>
                    </Upload>
                    <Space>
                      <Switch checked={replaceExisting} onChange={setReplaceExisting} />
                      <Text>覆盖现有数据</Text>
                    </Space>
                    <Button onClick={downloadTemplate}>下载模板</Button>
                    <Button onClick={exportCurrentRecords}>导出当前数据</Button>
                    <Button
                      onClick={() => {
                        void loadAssets();
                        void loadAssetStats();
                      }}
                      loading={loading}
                    >
                      刷新
                    </Button>
                  </Space>

                  <Card size="small" title="手工维护责任田资产">
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      {editingAssetId ? (
                        <Alert
                          type="warning"
                          showIcon
                          message={`当前正在编辑：${editingAssetId}`}
                        />
                      ) : null}
                      <Space wrap>
                        <Input
                          placeholder="特性"
                          value={manualForm.feature}
                          onChange={(e) => setManualForm((p) => ({ ...p, feature: e.target.value }))}
                          style={{ width: 180 }}
                        />
                        <Input
                          placeholder="领域 *"
                          value={manualForm.domain}
                          onChange={(e) => setManualForm((p) => ({ ...p, domain: e.target.value }))}
                          style={{ width: 180 }}
                        />
                        <Input
                          placeholder="聚合根 *"
                          value={manualForm.aggregate}
                          onChange={(e) => setManualForm((p) => ({ ...p, aggregate: e.target.value }))}
                          style={{ width: 180 }}
                        />
                        <Input
                          placeholder="负责人团队"
                          value={manualForm.owner_team}
                          onChange={(e) => setManualForm((p) => ({ ...p, owner_team: e.target.value }))}
                          style={{ width: 180 }}
                        />
                        <Input
                          placeholder="负责人"
                          value={manualForm.owner}
                          onChange={(e) => setManualForm((p) => ({ ...p, owner: e.target.value }))}
                          style={{ width: 180 }}
                        />
                      </Space>
                      <Input
                        placeholder="前端页面（逗号分隔）"
                        value={manualForm.frontend_pages}
                        onChange={(e) => setManualForm((p) => ({ ...p, frontend_pages: e.target.value }))}
                      />
                      <Input
                        placeholder="API 接口 *（示例：POST /api/v1/orders，可多条逗号分隔）"
                        value={manualForm.api_interfaces}
                        onChange={(e) => setManualForm((p) => ({ ...p, api_interfaces: e.target.value }))}
                      />
                      <Input
                        placeholder="代码清单（逗号分隔）"
                        value={manualForm.code_items}
                        onChange={(e) => setManualForm((p) => ({ ...p, code_items: e.target.value }))}
                      />
                      <Input
                        placeholder="数据库表（逗号分隔）"
                        value={manualForm.database_tables}
                        onChange={(e) => setManualForm((p) => ({ ...p, database_tables: e.target.value }))}
                      />
                      <Input
                        placeholder="依赖服务（逗号分隔）"
                        value={manualForm.dependency_services}
                        onChange={(e) => setManualForm((p) => ({ ...p, dependency_services: e.target.value }))}
                      />
                      <Input
                        placeholder="监控清单（逗号分隔）"
                        value={manualForm.monitor_items}
                        onChange={(e) => setManualForm((p) => ({ ...p, monitor_items: e.target.value }))}
                      />
                      <Space>
                        <Button type="primary" loading={savingManual} onClick={() => void handleSaveManual()}>
                          {editingAssetId ? '更新' : '保存'}
                        </Button>
                        <Button onClick={resetManualForm}>
                          清空
                        </Button>
                      </Space>
                    </Space>
                  </Card>
                </Space>
              ),
            },
            {
              key: 'saved',
              label: '已保存资产',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Space wrap>
                    <Input
                      placeholder="全文搜索（特性/领域/聚合根/API）"
                      value={filterText}
                      onChange={(e) => setFilterText(e.target.value)}
                      style={{ width: 280 }}
                    />
                    <Select
                      allowClear
                      showSearch
                      placeholder="筛选领域"
                      value={filterDomain || undefined}
                      options={domainOptions}
                      style={{ width: 200 }}
                      onChange={(v) => setFilterDomain(String(v || ''))}
                    />
                    <Select
                      allowClear
                      showSearch
                      placeholder="筛选聚合根"
                      value={filterAggregate || undefined}
                      options={aggregateOptions}
                      style={{ width: 220 }}
                      onChange={(v) => setFilterAggregate(String(v || ''))}
                    />
                    <Input
                      placeholder="筛选 API 关键词"
                      value={filterApi}
                      onChange={(e) => setFilterApi(e.target.value)}
                      style={{ width: 220 }}
                    />
                    <Button type="primary" onClick={() => void loadAssets()} loading={loading}>
                      查询
                    </Button>
                  </Space>

                  <Card
                    size="small"
                    title={`已保存责任田资产（${total}）`}
                    extra={
                      <Space>
                        <Text type="secondary">
                          最新更新：{latestUpdatedAt || '-'}
                        </Text>
                      </Space>
                    }
                  >
                    {storagePath ? (
                      <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                        存储位置：{storagePath}
                      </Paragraph>
                    ) : null}
                    <Table
                      rowKey={(row) => row.asset_id}
                      loading={loading}
                      columns={columns}
                      dataSource={records}
                      scroll={{ x: 1800, y: '52vh' }}
                      pagination={{ pageSize: 20 }}
                      locale={{ emptyText: '暂无责任田资产，请先上传 Excel/CSV 或手工新增' }}
                    />
                  </Card>
                </Space>
              ),
            },
            {
              key: 'locate',
              label: '责任田定位',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Paragraph style={{ marginBottom: 0 }}>
                    输入故障日志后，系统优先命中你维护的责任田资产；未命中时回退到内置责任田知识库。
                  </Paragraph>
                  <TextArea
                    rows={8}
                    placeholder="粘贴接口报错日志，例如：ERROR POST /api/v1/orders failed ..."
                    value={logContent}
                    onChange={(e) => setLogContent(e.target.value)}
                  />
                  <Input
                    placeholder="故障现象（可选）"
                    value={symptom}
                    onChange={(e) => setSymptom(e.target.value)}
                  />
                  <Space wrap>
                    <Button type="primary" loading={locateLoading} onClick={() => void locateByLog()}>
                      定位责任田
                    </Button>
                    <Button
                      onClick={() => {
                        setLogContent(`2026-02-20 14:01:38 ERROR POST /api/v1/orders failed, status=502
2026-02-20 14:01:38 ERROR HikariPool-1 - Connection is not available, request timed out after 30000ms.`);
                        setSymptom('下单接口 502，数据库连接池耗尽');
                      }}
                    >
                      填充示例日志
                    </Button>
                  </Space>

                  {!locateResult ? (
                    <Empty description="暂无定位结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  ) : (
                    <>
                      <Alert
                        type={locateResult.matched ? 'success' : 'warning'}
                        showIcon
                        message={locateResult.reason}
                      />
                      <Descriptions bordered column={2}>
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
                            ? `${locateResult.matched_endpoint.method} ${locateResult.matched_endpoint.path}`
                            : '-'}
                        </Descriptions.Item>
                        <Descriptions.Item label="数据库表" span={2}>
                          {joinListText(locateResult.db_tables)}
                        </Descriptions.Item>
                      </Descriptions>
                      <Table
                        rowKey={(row, idx) => `${row.path}-${row.symbol}-${idx}`}
                        columns={locateColumns}
                        dataSource={locateResult.code_artifacts}
                        pagination={false}
                        locale={{ emptyText: '未返回关联代码' }}
                      />
                    </>
                  )}
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
