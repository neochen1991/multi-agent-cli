import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { settingsApi, type AgentMCPBindingConfig, type MCPProbeResult, type MCPServerConfig } from '@/services/api';

const { Paragraph, Text, Title } = Typography;

type MCPFormValues = MCPServerConfig;

const AGENT_OPTIONS = [
  'ProblemAnalysisAgent',
  'LogAgent',
  'MetricsAgent',
  'DatabaseAgent',
  'DomainAgent',
  'CodeAgent',
  'ChangeAgent',
  'ImpactAnalysisAgent',
  'RunbookAgent',
  'RuleSuggestionAgent',
];

const splitTextList = (value?: string): string[] =>
  String(value || '')
    .split(/[,，;\n；、|]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const McpCenterPage: React.FC = () => {
  const [form] = Form.useForm<MCPFormValues>();
  const [servers, setServers] = useState<MCPServerConfig[]>([]);
  const [bindings, setBindings] = useState<AgentMCPBindingConfig>({ enabled: true, bindings: {} });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [bindingSaving, setBindingSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState('');
  const [commandListText, setCommandListText] = useState('[]');
  const [probeOpen, setProbeOpen] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<MCPProbeResult | null>(null);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [serverRes, bindingRes] = await Promise.all([
        settingsApi.listMCPServers(),
        settingsApi.getMCPBindings(),
      ]);
      setServers(serverRes || []);
      setBindings(bindingRes || { enabled: true, bindings: {} });
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载 MCP 配置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  const serverOptions = useMemo(
    () => servers.map((item) => ({ label: `${item.name} (${item.id})`, value: item.id })),
    [servers],
  );

  const openCreate = () => {
    setEditingId('');
    form.resetFields();
    form.setFieldsValue({
      id: '',
      name: '',
      enabled: true,
      type: 'remote',
      transport: 'http',
      protocol_mode: 'gateway',
      endpoint: '',
      command: '',
      command_list: [],
      args: [],
      env: {},
      api_token: '',
      timeout_seconds: 12,
      capabilities: ['logs', 'metrics'],
      tool_paths: { logs: '/logs/search', metrics: '/metrics/query' },
      metadata: {},
    });
    setCommandListText('[]');
    setModalOpen(true);
  };

  const openEdit = (row: MCPServerConfig) => {
    setEditingId(row.id);
    form.setFieldsValue({
      ...row,
      protocol_mode: row.protocol_mode || 'gateway',
      capabilities: Array.isArray(row.capabilities) ? row.capabilities : [],
    });
    setCommandListText(JSON.stringify(row.command_list || []));
    setModalOpen(true);
  };

  const saveServer = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      let parsedCommandList: string[] = [];
      try {
        const parsed = JSON.parse(String(commandListText || '[]'));
        if (Array.isArray(parsed)) {
          parsedCommandList = parsed.map((item) => String(item));
        }
      } catch {
        parsedCommandList = [];
      }
      const payload: MCPServerConfig = {
        ...values,
        id: String(values.id || editingId || '').trim(),
        name: String(values.name || '').trim(),
        type: String(values.type || 'remote').trim() || 'remote',
        protocol_mode: String(values.protocol_mode || 'gateway').trim() || 'gateway',
        endpoint: String(values.endpoint || '').trim(),
        command: String(values.command || '').trim(),
        command_list: parsedCommandList,
        capabilities: values.capabilities || [],
      };
      await settingsApi.upsertMCPServer(payload);
      message.success('MCP 服务配置已保存');
      setModalOpen(false);
      await loadAll();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const deleteServer = async (serverId: string) => {
    try {
      await settingsApi.deleteMCPServer(serverId);
      message.success('MCP 服务已删除');
      await loadAll();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '删除失败');
    }
  };

  const probeServer = async (serverId: string) => {
    setProbing(true);
    setProbeResult(null);
    setProbeOpen(true);
    try {
      const result = await settingsApi.probeMCPServer(serverId);
      setProbeResult(result);
      if (result.ok) {
        message.success('MCP 服务探测成功');
      } else {
        message.warning('MCP 服务探测完成，但未命中可用结果');
      }
    } catch (error: any) {
      const msg = error?.response?.data?.detail || error?.message || '探测失败';
      setProbeResult({ ok: false, server_id: serverId, error: msg, audit_log: [] });
      message.error(msg);
    } finally {
      setProbing(false);
    }
  };

  const updateBindingForAgent = (agentName: string, serverIds: string[]) => {
    setBindings((prev) => ({
      ...prev,
      bindings: {
        ...(prev.bindings || {}),
        [agentName]: serverIds,
      },
    }));
  };

  const saveBindings = async () => {
    setBindingSaving(true);
    try {
      await settingsApi.updateMCPBindings(bindings);
      message.success('Agent MCP 绑定已更新');
      await loadAll();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '绑定保存失败');
    } finally {
      setBindingSaving(false);
    }
  };

  const columns: ColumnsType<MCPServerConfig> = [
    {
      title: '名称',
      key: 'name',
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.name}</Text>
          <Text type="secondary">{row.id}</Text>
        </Space>
      ),
    },
    {
      title: '传输',
      dataIndex: 'transport',
      key: 'transport',
      width: 90,
      render: (value: string) => <Tag>{String(value || 'http').toUpperCase()}</Tag>,
    },
    {
      title: '模式',
      dataIndex: 'protocol_mode',
      key: 'protocol_mode',
      width: 130,
      render: (value: string) => (
        <Tag color={String(value || 'gateway').toLowerCase() === 'mcp' ? 'geekblue' : 'default'}>
          {String(value || 'gateway').toLowerCase() === 'mcp' ? 'MCP' : 'Gateway'}
        </Tag>
      ),
    },
    {
      title: '端点/命令',
      key: 'endpoint',
      render: (_, row) => <Text>{row.endpoint || row.command || '-'}</Text>,
    },
    {
      title: '能力',
      dataIndex: 'capabilities',
      key: 'capabilities',
      width: 220,
      render: (caps: string[]) => (
        <Space wrap size={[4, 4]}>
          {(caps || []).map((cap) => (
            <Tag key={cap}>{cap}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 100,
      render: (enabled: boolean) => <Tag color={enabled ? 'success' : 'default'}>{enabled ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 240,
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => void probeServer(row.id)}>
            测试
          </Button>
          <Button size="small" onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Button size="small" danger onClick={() => void deleteServer(row.id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Title level={3} style={{ margin: 0 }}>MCP 服务配置中心</Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            在这里配置 MCP 服务（类似 Claude Code / OpenCode 的 MCP 入口），并把服务绑定到具体专家 Agent。
          </Paragraph>
          <Space>
            <Button type="primary" onClick={openCreate}>
              新增 MCP 服务
            </Button>
            <Button onClick={() => void loadAll()} loading={loading}>
              刷新
            </Button>
          </Space>
        </Space>
      </Card>

      <Card title="MCP 服务列表">
        <Table<MCPServerConfig>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={servers}
          pagination={{ pageSize: 8, showSizeChanger: false }}
        />
      </Card>

      <Card title="Agent 绑定">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space>
            <Text>启用 MCP 绑定</Text>
            <Switch
              checked={Boolean(bindings.enabled)}
              onChange={(checked) => {
                setBindings((prev) => ({ ...prev, enabled: checked }));
              }}
            />
          </Space>
          {AGENT_OPTIONS.map((agentName) => (
            <div key={agentName} style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <Text style={{ width: 220 }}>{agentName}</Text>
              <Select
                mode="multiple"
                style={{ minWidth: 460 }}
                placeholder="选择该 Agent 可调用的 MCP 服务"
                options={serverOptions}
                value={(bindings.bindings || {})[agentName] || []}
                onChange={(values) => {
                  updateBindingForAgent(agentName, values);
                }}
              />
            </div>
          ))}
          <Space>
            <Button type="primary" loading={bindingSaving} onClick={() => void saveBindings()}>
              保存绑定
            </Button>
          </Space>
        </Space>
      </Card>

      <Modal
        title={editingId ? '编辑 MCP 服务' : '新增 MCP 服务'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void saveServer()}
        confirmLoading={saving}
        width={760}
      >
        <Form<MCPFormValues> form={form} layout="vertical">
          <Form.Item label="服务 ID（可选）" name="id">
            <Input placeholder="留空自动生成，如 mcp_logs_prod" />
          </Form.Item>
          <Form.Item label="服务名称" name="name" rules={[{ required: true, message: '请输入服务名称' }]}>
            <Input placeholder="例如：生产日志 MCP" />
          </Form.Item>
          <Space align="start" wrap style={{ width: '100%' }}>
            <Form.Item label="启用" name="enabled" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item label="传输协议" name="transport">
              <Select
                style={{ width: 140 }}
                options={[
                  { label: 'HTTP', value: 'http' },
                  { label: 'SSE', value: 'sse' },
                  { label: 'STDIO', value: 'stdio' },
                ]}
              />
            </Form.Item>
            <Form.Item label="调用模式" name="protocol_mode">
              <Select
                style={{ width: 180 }}
                options={[
                  { label: '网关模式（HTTP GET）', value: 'gateway' },
                  { label: '标准 MCP（JSON-RPC）', value: 'mcp' },
                  { label: '本地模式（STDIO MCP）', value: 'local' },
                ]}
                onChange={(mode) => {
                  if (mode === 'local') {
                    form.setFieldValue('type', 'local');
                    form.setFieldValue('transport', 'stdio');
                  }
                }}
              />
            </Form.Item>
            <Form.Item label="服务类型" name="type">
              <Select
                style={{ width: 140 }}
                options={[
                  { label: 'Remote', value: 'remote' },
                  { label: 'Local', value: 'local' },
                ]}
              />
            </Form.Item>
            <Form.Item label="超时(秒)" name="timeout_seconds">
              <InputNumber min={2} max={120} style={{ width: 120 }} />
            </Form.Item>
          </Space>
          <Form.Item label="Endpoint（http/sse）" name="endpoint">
            <Input placeholder="http://mcp-gateway.internal:8080" />
          </Form.Item>
          <Form.Item label="命令（stdio）" name="command">
            <Input placeholder="npx @modelcontextprotocol/server-filesystem" />
          </Form.Item>
          <Form.Item label="命令数组（JSON，可选）">
            <Input
              placeholder='["python","-m","my_mcp_server"]'
              value={commandListText}
              onChange={(e) => {
                // 中文注释：命令数组允许“半输入”状态，保存时再统一做 JSON 解析。
                setCommandListText(String(e.target.value || ''));
              }}
            />
          </Form.Item>
          <Form.Item label="能力（逗号分隔）">
            <Input
              placeholder="logs,metrics,alerts,traces"
              value={String((form.getFieldValue('capabilities') || []).join(','))}
              onChange={(e) => {
                form.setFieldValue('capabilities', splitTextList(e.target.value));
              }}
            />
          </Form.Item>
          <Form.Item label="API Token" name="api_token">
            <Input.Password placeholder="可选：Bearer token" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="MCP 服务探测结果"
        open={probeOpen}
        onCancel={() => setProbeOpen(false)}
        onOk={() => setProbeOpen(false)}
        confirmLoading={probing}
        width={820}
      >
        {probeResult ? (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Alert
              type={probeResult.ok ? 'success' : 'warning'}
              message={probeResult.ok ? '探测成功' : '探测未通过'}
              description={`server=${probeResult.server_name || probeResult.server_id}，items=${probeResult.items_count || 0}${probeResult.error ? `，error=${probeResult.error}` : ''}`}
              showIcon
            />
            <Card size="small" title="审计日志">
              <pre style={{ margin: 0, maxHeight: 260, overflow: 'auto' }}>
                {JSON.stringify(probeResult.audit_log || [], null, 2)}
              </pre>
            </Card>
            <Card size="small" title="返回样本">
              <pre style={{ margin: 0, maxHeight: 260, overflow: 'auto' }}>
                {JSON.stringify(probeResult.items || [], null, 2)}
              </pre>
            </Card>
          </Space>
        ) : (
          <Text type="secondary">探测中...</Text>
        )}
      </Modal>
    </Space>
  );
};

export default McpCenterPage;
