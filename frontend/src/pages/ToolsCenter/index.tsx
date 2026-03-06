import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Row, Space, Tabs, Tag, Typography, message } from 'antd';
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

const { Paragraph, Text, Title } = Typography;

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

  const enabledTools = registry.filter((item) => item.enabled);
  const unhealthyConnectors = connectors.filter((item) => item.healthy === false || ['error', 'disconnected'].includes(String(item.status || '').toLowerCase()));
  const selectedToolEnabled = Boolean(selectedTool?.enabled);
  const sessionAuditLoaded = Boolean(audit?.items?.length);
  const disabledTools = Math.max(registry.length - enabledTools.length, 0);
  const healthyConnectors = Math.max(connectors.length - unhealthyConnectors.length, 0);

  const recommendation = useMemo(() => {
    if (unhealthyConnectors.length > 0) {
      return {
        tone: 'risk',
        title: '先看不稳定连接器',
        description: `当前有 ${unhealthyConnectors.length} 个连接器不健康或已断开，建议先进入“工具总览”确认映射，再到“连接与试跑”处理。`,
      };
    }
    if (!selectedToolName) {
      return {
        tone: 'watch',
        title: '先选择一个工具',
        description: '当前还没有选中工具，先在“工具总览”里确认工具归属、是否启用和连接器映射。',
      };
    }
    if (!trialResult) {
      return {
        tone: 'info',
        title: '先做一次参数试跑',
        description: '当你不确定工具当前能否返回可靠结果时，先跑一次试跑，比直接在真实 session 中碰运气更稳。',
      };
    }
    if (!sessionAuditLoaded) {
      return {
        tone: 'watch',
        title: '再看一次会话审计',
        description: '如果你要判断某次真实分析中的工具结果值不值得信任，接下来应该加载对应 session 的工具审计。',
      };
    }
    return {
      tone: 'healthy',
      title: '当前工具状态基本可用',
      description: '没有明显连接器风险。接下来按需要查看具体会话审计或完整输出引用即可。',
    };
  }, [sessionAuditLoaded, selectedToolName, trialResult, unhealthyConnectors.length]);

  const summaryCards = [
    {
      title: '工具总数',
      value: registry.length,
      hint: '系统当前注册的工具数量',
      tone: registry.length > 0 ? 'info' : 'watch',
    },
    {
      title: '已启用工具',
      value: enabledTools.length,
      hint: enabledTools.length > 0 ? '这些工具可以被 Agent 正常调用' : '当前没有已启用工具',
      tone: enabledTools.length > 0 ? 'healthy' : 'risk',
    },
    {
      title: '连接器总数',
      value: connectors.length,
      hint: '工具背后的外部连接器数量',
      tone: connectors.length > 0 ? 'info' : 'watch',
    },
    {
      title: '异常连接器',
      value: unhealthyConnectors.length,
      hint: unhealthyConnectors.length > 0 ? '优先修复这些连接器，再信任工具结果' : '当前没有明显异常连接器',
      tone: unhealthyConnectors.length > 0 ? 'risk' : 'healthy',
    },
    {
      title: '会话审计状态',
      value: sessionAuditLoaded ? '已加载' : '待查询',
      hint: sessionAuditLoaded ? '已经可以核对真实 session 的工具行为' : '输入 session_id 后才能判断某次分析中的工具是否可靠',
      tone: sessionAuditLoaded ? 'healthy' : 'info',
    },
    {
      title: '当前工具状态',
      value: selectedToolName || '未选择',
      hint: selectedToolName ? (selectedToolEnabled ? '当前选中的工具已启用' : '当前工具存在但未启用') : '先选一个工具再继续',
      tone: !selectedToolName ? 'watch' : selectedToolEnabled ? 'healthy' : 'risk',
    },
  ];

  const tabs = [
    {
      key: 'overview',
      label: '工具总览',
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={9}>
            <ToolRegistryList
              loading={loadingBase}
              items={registry}
              selectedToolName={selectedToolName}
              onSelect={setSelectedToolName}
            />
          </Col>
          <Col xs={24} lg={15}>
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <ToolDetailPanel selectedTool={selectedTool} connectorsForSelected={connectorsForSelected} />
              <Card className="module-card ops-section-card" size="small">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    连接器健康提示
                  </Title>
                  <Text type="secondary">先看哪些连接器没连通或状态异常，再决定是否继续信任当前工具输出。</Text>
                  <Space wrap>
                    {connectors.length === 0 ? <Tag>暂无连接器</Tag> : null}
                    {connectors.map((item) => {
                      const unhealthy = item.healthy === false || ['error', 'disconnected'].includes(String(item.status || '').toLowerCase());
                      return (
                        <Tag key={String(item.name || Math.random())} color={unhealthy ? 'red' : item.connected ? 'green' : 'default'}>
                          {String(item.name || '-')} · {String(item.status || (item.connected ? 'connected' : 'unknown'))}
                        </Tag>
                      );
                    })}
                  </Space>
                </Space>
              </Card>
              <Card className="module-card ops-section-card mini-chart-card" size="small">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    工具与连接器摘要
                  </Title>
                  <div className="mini-ratio-bar">
                    <div
                      className="mini-ratio-segment tone-healthy"
                      style={{ width: `${registry.length ? (enabledTools.length / registry.length) * 100 : 0}%` }}
                    />
                    <div
                      className="mini-ratio-segment tone-watch"
                      style={{ width: `${registry.length ? (disabledTools / registry.length) * 100 : 0}%` }}
                    />
                  </div>
                  <Text type="secondary">
                    已启用工具 {enabledTools.length} / 未启用工具 {disabledTools}
                  </Text>
                  <div className="mini-ratio-bar">
                    <div
                      className="mini-ratio-segment tone-healthy"
                      style={{ width: `${connectors.length ? (healthyConnectors / connectors.length) * 100 : 0}%` }}
                    />
                    <div
                      className="mini-ratio-segment tone-risk"
                      style={{ width: `${connectors.length ? (unhealthyConnectors.length / connectors.length) * 100 : 0}%` }}
                    />
                  </div>
                  <Text type="secondary">
                    健康连接器 {healthyConnectors} / 异常连接器 {unhealthyConnectors.length}
                  </Text>
                  <div className="mini-bar-list">
                    {[
                      { label: '参数试跑', value: trialResult ? '已完成' : '未试跑', tone: trialResult ? 'healthy' : 'watch' },
                      { label: '会话审计', value: sessionAuditLoaded ? '已加载' : '待查询', tone: sessionAuditLoaded ? 'healthy' : 'info' },
                    ].map((item) => (
                      <div key={item.label} className="mini-bar-row">
                        <div className="mini-bar-label-wrap">
                          <Text strong>{item.label}</Text>
                          <Text type="secondary">{item.value}</Text>
                        </div>
                        <div className={`mini-state-pill tone-${item.tone}`}>{item.value}</div>
                      </div>
                    ))}
                  </div>
                </Space>
              </Card>
            </Space>
          </Col>
        </Row>
      ),
    },
    {
      key: 'connect-run',
      label: '连接与试跑',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="module-card ops-action-card" size="small" title="连接器控制台">
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
        </Space>
      ),
    },
    {
      key: 'audit',
      label: '会话审计',
      children: (
        <ToolAuditPanel
          sessionId={sessionId}
          onSessionIdChange={setSessionId}
          loading={loadingAudit}
          audit={audit}
          onLoad={loadAudit}
          onOpenRef={openOutputRef}
        />
      ),
    },
    {
      key: 'output-ref',
      label: '输出引用',
      children: (
        <Card className="module-card ops-section-card" title="输出引用查看">
          <pre className="dialogue-content">{JSON.stringify(outputRefPreview || {}, null, 2)}</pre>
        </Card>
      ),
    },
  ];

  return (
    <div className="tools-page">
      <Card className="module-card ops-hero-card">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="blue">值班 SRE</Tag>
            <Tag color="default">平台操作</Tag>
          </Space>
          <div>
            <Title level={3} style={{ margin: 0 }}>
              工具管理
            </Title>
            <Paragraph className="ops-hero-description">
              这页先用来判断当前工具和连接器是否可信，再决定是否连接、试跑、查审计或查看完整输出。先判断健康，再做操作。
            </Paragraph>
          </div>
          <div className="ops-question-list">
            <Tag>当前哪些工具可用</Tag>
            <Tag>哪些连接器不稳定</Tag>
            <Tag>当前 session 的工具结果值不值得信任</Tag>
          </div>
        </Space>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {summaryCards.map((card) => (
          <Col xs={24} sm={12} xl={8} key={card.title}>
            <Card className={`module-card ops-summary-card tone-${card.tone}`} size="small">
              <Text type="secondary">{card.title}</Text>
              <Title level={5} style={{ margin: '4px 0 0' }}>
                {String(card.value)}
              </Title>
              <Text className="ops-summary-hint">{card.hint}</Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Card className={`module-card ops-recommend-card tone-${recommendation.tone}`} style={{ marginTop: 16 }}>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Text strong>处置建议</Text>
          <Title level={5} style={{ margin: 0 }}>
            {recommendation.title}
          </Title>
          <Text type="secondary">{recommendation.description}</Text>
        </Space>
      </Card>

      <div style={{ marginTop: 16 }}>
        <Tabs className="incident-workspace-tabs" items={tabs} />
      </div>
    </div>
  );
};

export default ToolsCenterPage;
