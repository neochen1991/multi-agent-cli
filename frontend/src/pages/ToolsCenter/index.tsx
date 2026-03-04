import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Row, Space, Typography, message } from 'antd';
import {
  debateApi,
  settingsApi,
  type ToolConnector,
  type ToolAuditResponse,
  type ToolRegistryItem,
  type ToolTrialRunResponse,
} from '@/services/api';
import ToolRegistryList from '@/components/tools/ToolRegistryList';
import ToolDetailPanel from '@/components/tools/ToolDetailPanel';
import ToolTrialRunner from '@/components/tools/ToolTrialRunner';
import ToolAuditPanel from '@/components/tools/ToolAuditPanel';

const { Text, Title } = Typography;

const normalize = (value: unknown): string =>
  String(value || '')
    .trim()
    .toLowerCase();

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

const ToolsCenterPage: React.FC = () => {
  const [registry, setRegistry] = useState<ToolRegistryItem[]>([]);
  const [connectors, setConnectors] = useState<ToolConnector[]>([]);
  const [selectedToolName, setSelectedToolName] = useState('');
  const [selectedTool, setSelectedTool] = useState<ToolRegistryItem | null>(null);
  const [selectedConnector, setSelectedConnector] = useState<string>('');
  const [sessionId, setSessionId] = useState('');
  const [audit, setAudit] = useState<ToolAuditResponse | null>(null);
  const [trialResult, setTrialResult] = useState<ToolTrialRunResponse | null>(null);
  const [connectorResult, setConnectorResult] = useState<Record<string, unknown> | null>(null);
  const [outputRefPreview, setOutputRefPreview] = useState<Record<string, unknown> | null>(null);
  const [loadingBase, setLoadingBase] = useState(false);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [loadingTrial, setLoadingTrial] = useState(false);
  const [loadingConnectorAction, setLoadingConnectorAction] = useState(false);

  const loadBase = async () => {
    setLoadingBase(true);
    try {
      const [items, links] = await Promise.all([settingsApi.getToolRegistry(), settingsApi.getToolConnectors()]);
      setRegistry(items || []);
      setConnectors(links || []);
      if (!selectedToolName && items.length > 0) {
        setSelectedToolName(items[0].tool_name);
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '工具中心加载失败');
    } finally {
      setLoadingBase(false);
    }
  };

  const loadToolDetail = async (toolName: string) => {
    if (!toolName) return;
    try {
      const detail = await settingsApi.getToolRegistryItem(toolName);
      setSelectedTool(detail);
      setTrialResult(null);
    } catch (e: any) {
      setSelectedTool(null);
      message.error(e?.response?.data?.detail || e?.message || '工具详情加载失败');
    }
  };

  const loadAudit = async () => {
    const id = sessionId.trim();
    if (!id) {
      message.warning('请输入会话ID');
      return;
    }
    setLoadingAudit(true);
    try {
      const result = await settingsApi.getToolAudit(id);
      setAudit(result);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '审计记录加载失败');
    } finally {
      setLoadingAudit(false);
    }
  };

  const runTrial = async (values: {
    use_tool?: boolean;
    task?: string;
    focus?: string;
    expected_output?: string;
    service_name?: string;
    trace_id?: string;
    exception_class?: string;
    error_message?: string;
    log_content?: string;
  }) => {
    if (!selectedToolName) {
      message.warning('请先选择工具');
      return;
    }
    setLoadingTrial(true);
    try {
      const result = await settingsApi.trialRunTool({
        tool_name: selectedToolName,
        use_tool: Boolean(values.use_tool),
        task: String(values.task || ''),
        focus: String(values.focus || ''),
        expected_output: String(values.expected_output || ''),
        incident_context: {
          service_name: String(values.service_name || ''),
          log_content: String(values.log_content || ''),
        },
        compact_context: {
          parsed_data: {
            trace_id: String(values.trace_id || ''),
            error_message: String(values.error_message || ''),
            exception_class: String(values.exception_class || ''),
          },
        },
      });
      setTrialResult(result);
      message.success('工具试跑完成');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '工具试跑失败');
    } finally {
      setLoadingTrial(false);
    }
  };

  useEffect(() => {
    void loadBase();
  }, []);

  useEffect(() => {
    if (!selectedToolName) return;
    void loadToolDetail(selectedToolName);
  }, [selectedToolName]);

  const connectorsForSelected = useMemo(() => {
    const target = normalize(selectedToolName);
    if (!target) return [];
    return connectors.filter((item) => {
      const tools = extractConnectorTools(item.tools).map((tool) => normalize(tool));
      return tools.includes(target);
    });
  }, [connectors, selectedToolName]);

  useEffect(() => {
    if (connectorsForSelected.length === 0) {
      setSelectedConnector('');
      return;
    }
    const exists = connectorsForSelected.some((item) => normalize(item.name) === normalize(selectedConnector));
    if (!exists) {
      setSelectedConnector(String(connectorsForSelected[0].name || ''));
    }
  }, [connectorsForSelected, selectedConnector]);

  const refreshConnectors = async () => {
    const links = await settingsApi.getToolConnectors();
    setConnectors(links || []);
  };

  const runConnectorAction = async (action: 'connect' | 'disconnect' | 'list-tools' | 'call-tool') => {
    if (!selectedConnector) {
      message.warning('当前工具没有可用连接器');
      return;
    }
    setLoadingConnectorAction(true);
    try {
      let result: Record<string, unknown> = {};
      if (action === 'connect') {
        result = (await settingsApi.connectToolConnector(selectedConnector)) as unknown as Record<string, unknown>;
      } else if (action === 'disconnect') {
        result = (await settingsApi.disconnectToolConnector(selectedConnector)) as unknown as Record<string, unknown>;
      } else if (action === 'list-tools') {
        result = await settingsApi.listConnectorTools(selectedConnector);
      } else {
        if (!selectedToolName) {
          message.warning('请先选择工具');
          return;
        }
        result = await settingsApi.callConnectorTool(selectedConnector, selectedToolName, {
          session_id: sessionId,
          trigger: 'tools-center',
        });
      }
      setConnectorResult(result);
      await refreshConnectors();
      message.success(`连接器操作完成：${action}`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || `连接器操作失败：${action}`);
    } finally {
      setLoadingConnectorAction(false);
    }
  };

  const openOutputRef = async (refId: string) => {
    const rid = String(refId || '').trim();
    if (!rid) return;
    try {
      const payload = await debateApi.getOutputRef(rid);
      setOutputRefPreview(payload || {});
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '输出引用加载失败');
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="module-card">
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            工具中心（OpenDerisk 风格）
          </Title>
          <Text type="secondary">支持工具列表、工具详情、参数试跑与会话级审计回放。</Text>
        </Space>
      </Card>

      <Row gutter={[12, 12]}>
        <Col xs={24} md={8}>
          <ToolRegistryList
            loading={loadingBase}
            items={registry}
            selectedToolName={selectedToolName}
            onSelect={setSelectedToolName}
          />
        </Col>
        <Col xs={24} md={16}>
          <ToolDetailPanel selectedTool={selectedTool} connectorsForSelected={connectorsForSelected} />
        </Col>
      </Row>

      <Card className="module-card" title="连接器控制台">
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Text type="secondary">
            当前工具：{selectedToolName || '-'} · 连接器：{selectedConnector || '无'}
          </Text>
          <Space wrap>
            <Button loading={loadingConnectorAction} onClick={() => void runConnectorAction('connect')}>
              连接
            </Button>
            <Button loading={loadingConnectorAction} onClick={() => void runConnectorAction('disconnect')}>
              断开
            </Button>
            <Button loading={loadingConnectorAction} onClick={() => void runConnectorAction('list-tools')}>
              查看工具集
            </Button>
            <Button type="primary" loading={loadingConnectorAction} onClick={() => void runConnectorAction('call-tool')}>
              调用当前工具
            </Button>
          </Space>
          <pre className="dialogue-content">{JSON.stringify(connectorResult || {}, null, 2)}</pre>
        </Space>
      </Card>

      <ToolTrialRunner
        selectedToolName={selectedToolName}
        loadingTrial={loadingTrial}
        trialResult={trialResult}
        onRun={runTrial}
      />

      <ToolAuditPanel
        sessionId={sessionId}
        onSessionIdChange={setSessionId}
        loading={loadingAudit}
        audit={audit}
        onLoad={loadAudit}
        onOpenRef={openOutputRef}
      />

      <Card className="module-card" title="输出引用查看">
        <pre className="dialogue-content">{JSON.stringify(outputRefPreview || {}, null, 2)}</pre>
      </Card>
    </Space>
  );
};

export default ToolsCenterPage;
