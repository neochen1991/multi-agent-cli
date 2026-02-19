import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Input,
  Progress,
  Select,
  Space,
  Steps,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd';
import { LinkOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  assetApi,
  buildDebateWsUrl,
  debateApi,
  incidentApi,
  reportApi,
  type AssetFusion,
  type DebateDetail,
  type DebateResult,
  type Report,
} from '@/services/api';

const { TextArea } = Input;
const { Paragraph, Text } = Typography;

type EventRecord = {
  id: string;
  timeText: string;
  kind: string;
  text: string;
  data?: unknown;
};

const IncidentPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { incidentId: routeIncidentId } = useParams();
  const [currentStep, setCurrentStep] = useState(0);
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [incidentForm, setIncidentForm] = useState({
    title: '',
    description: '',
    severity: 'medium',
    service_name: '',
    environment: 'production',
    log_content: '',
  });
  const [incidentId, setIncidentId] = useState<string>('');
  const [sessionId, setSessionId] = useState<string>('');
  const [sessionDetail, setSessionDetail] = useState<DebateDetail | null>(null);
  const [debateResult, setDebateResult] = useState<DebateResult | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [shareUrl, setShareUrl] = useState<string>('');
  const [fusion, setFusion] = useState<AssetFusion | null>(null);
  const [eventRecords, setEventRecords] = useState<EventRecord[]>([]);
  const [running, setRunning] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pollingRef = useRef(false);
  const runningRef = useRef(false);

  const steps = useMemo(
    () => [
      { title: '输入故障信息', description: '创建 Incident 与 Session' },
      { title: '资产与辩论', description: 'WebSocket 实时执行' },
      { title: '辩论结果', description: '轮次、置信度、结论' },
      { title: '报告与图谱', description: '报告输出与资产融合' },
    ],
    [],
  );

  const appendEvent = (kind: string, text: string, data?: unknown) => {
    const dataRecord = asRecord(data);
    const eventTsRaw = String(dataRecord.timestamp || '').trim();
    const eventTs = eventTsRaw ? new Date(eventTsRaw) : null;
    const displayTime =
      eventTs && !Number.isNaN(eventTs.getTime())
        ? eventTs.toLocaleString()
        : new Date().toLocaleString();
    const record: EventRecord = {
      id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
      timeText: displayTime,
      kind,
      text,
      data,
    };
    setEventRecords((prev) => [record, ...prev].slice(0, 300));
  };

  const asRecord = (value: unknown): Record<string, unknown> => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return {};
    }
    return value as Record<string, unknown>;
  };

  const toDisplayText = (value: unknown): string => {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  };

  const extractSessionError = (detail: DebateDetail | null): string => {
    const context = (detail?.context || {}) as Record<string, unknown>;
    const direct = String(context.last_error || '').trim();
    if (direct) return direct;
    const eventLog = context.event_log;
    if (!Array.isArray(eventLog)) return '';
    for (let i = eventLog.length - 1; i >= 0; i -= 1) {
      const row = asRecord(eventLog[i]);
      const event = asRecord(row.event);
      if (String(event.type || '') === 'session_failed') {
        const err = String(event.error || '').trim();
        if (err) return err;
      }
    }
    return '';
  };

  const firstTextValue = (data: Record<string, unknown>, keys: string[]): string => {
    for (const key of keys) {
      const raw = data[key];
      if (raw === null || raw === undefined) continue;
      const text = String(raw).trim();
      if (text) return text;
    }
    return '';
  };

  const formatEventText = (kind: string, data?: Record<string, unknown>) => {
    const phase = String(data?.phase || '');
    const stage = String(data?.stage || '');
    const model = String(data?.model || '');
    const latency = typeof data?.latency_ms === 'number' ? `${data.latency_ms}ms` : '';
    const agent = String(data?.agent_name || '');
    const error = String(data?.error || '');
    switch (kind) {
      case 'opencode_call_started':
      case 'autogen_call_started':
        return `AutoGen请求开始 [${phase || stage || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'opencode_call_completed':
      case 'autogen_call_completed':
        return `AutoGen请求完成 [${phase || stage || '-'}] ${agent || ''} ${model || ''} ${latency}`.trim();
      case 'opencode_call_failed':
      case 'autogen_call_failed':
        return `AutoGen请求失败 [${phase || stage || '-'}] ${agent || ''} ${model || ''} ${error}`.trim();
      case 'llm_call_started':
        return `辩论LLM开始 [${phase || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'llm_call_completed':
        return `辩论LLM完成 [${phase || '-'}] ${agent || ''} ${model || ''} ${latency}`.trim();
      case 'llm_call_failed':
        return `辩论LLM失败 [${phase || '-'}] ${agent || ''} ${error}`.trim();
      case 'llm_http_request':
        return `LLM请求参数 [${phase || stage || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'llm_http_response':
        return `LLM响应参数 [${phase || stage || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'llm_http_error':
        return `LLM响应异常 [${phase || stage || '-'}] ${agent || ''} ${error || String(data?.status_code || '')}`.trim();
      case 'llm_prompt_started':
      case 'llm_cli_command_started':
        return `LLM请求开始 [${phase || stage || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'llm_cli_stream_event':
        return `LLM流式事件 [${phase || stage || '-'}] ${String(data?.event_type || '-')}`.trim();
      case 'llm_cli_command_completed':
      case 'llm_prompt_completed':
        return `LLM请求完成 [${phase || stage || '-'}] ${latency || `rc=${String(data?.return_code ?? '-')}`}`.trim();
      case 'llm_prompt_failed':
      case 'llm_cli_command_failed':
        return `LLM请求失败 [${phase || stage || '-'}] ${error}`.trim();
      case 'asset_interface_mapping_completed':
        return `责任田映射完成 domain=${String(data?.domain || '-')} aggregate=${String(data?.aggregate || '-')}`;
      case 'session_failed':
        return `会话失败 ${error}`.trim();
      default:
        return `事件: ${kind}`;
    }
  };

  const formatEventDetail = (row: EventRecord) => {
    const data = asRecord(row.data);
    const phase = firstTextValue(data, ['phase']);
    const stage = firstTextValue(data, ['stage']);
    const model = firstTextValue(data, ['model']);
    const agent = firstTextValue(data, ['agent_name']);
    const session = firstTextValue(data, ['session_id', 'llm_session_id', 'opencode_session_id']);
    const endpoint = firstTextValue(data, ['endpoint']);
    const target = firstTextValue(data, ['target']);
    const latency =
      typeof data.latency_ms === 'number' ? `${Number(data.latency_ms).toFixed(2)} ms` : '';
    const round =
      typeof data.round_number === 'number' ? String(data.round_number) : firstTextValue(data, ['round_number']);
    const confidence =
      typeof data.confidence === 'number' ? `${(Number(data.confidence) * 100).toFixed(1)}%` : '';
    const parsedFlag = typeof data.parsed === 'boolean' ? (data.parsed ? '成功' : '失败') : '';
    const usage = asRecord(data.usage);
    const totalTokens =
      typeof usage.total_tokens === 'number' ? String(usage.total_tokens) : '';
    const matchedFlag = typeof data.matched === 'boolean' ? (data.matched ? '命中' : '未命中') : '';
    const domain = firstTextValue(data, ['domain']);
    const aggregate = firstTextValue(data, ['aggregate']);
    const ownerTeam = firstTextValue(data, ['owner_team']);
    const prompt = firstTextValue(data, ['prompt_preview', 'input_message', 'prompt', 'command']);
    const output = firstTextValue(data, [
      'response_preview',
      'output_preview',
      'content_preview',
      'text_preview',
      'event_preview',
      'stderr_preview',
    ]);
    const requestPayload = data.request_payload;
    const responsePayload = data.response_payload;
    const error = firstTextValue(data, ['error', 'message']);
    const outputJson = data.output_json;
    const hasFriendlyBlocks = Boolean(
      phase ||
        stage ||
        model ||
        agent ||
        session ||
        endpoint ||
        target ||
        latency ||
        round ||
        confidence ||
        prompt ||
        output ||
        requestPayload !== undefined ||
        responsePayload !== undefined ||
        error ||
        outputJson !== undefined,
    );

    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space wrap>
          <Tag color="blue">{row.kind}</Tag>
          {phase && <Tag>阶段: {phase}</Tag>}
          {stage && <Tag>步骤: {stage}</Tag>}
          {agent && <Tag color="geekblue">Agent: {agent}</Tag>}
          {model && <Tag color="purple">模型: {model}</Tag>}
          {session && <Tag>会话: {session}</Tag>}
          {endpoint && <Tag color="cyan">端点: {endpoint}</Tag>}
          {round && <Tag>轮次: {round}</Tag>}
          {target && <Tag>目标: {target}</Tag>}
          {latency && <Tag color="processing">耗时: {latency}</Tag>}
          {confidence && <Tag color="green">置信度: {confidence}</Tag>}
          {parsedFlag && <Tag color={parsedFlag === '成功' ? 'success' : 'error'}>解析: {parsedFlag}</Tag>}
          {totalTokens && <Tag color="purple">Tokens: {totalTokens}</Tag>}
          {matchedFlag && <Tag color={matchedFlag === '命中' ? 'success' : 'warning'}>映射: {matchedFlag}</Tag>}
          {domain && <Tag>领域: {domain}</Tag>}
          {aggregate && <Tag>聚合根: {aggregate}</Tag>}
          {ownerTeam && <Tag>责任团队: {ownerTeam}</Tag>}
        </Space>
        {prompt && (
          <>
            <Text type="secondary">模型输入</Text>
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{prompt}</pre>
          </>
        )}
        {requestPayload !== undefined && (
          <>
            <Text type="secondary">LLM请求参数</Text>
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{toDisplayText(requestPayload)}</pre>
          </>
        )}
        {output && (
          <>
            <Text type="secondary">模型输出</Text>
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{output}</pre>
          </>
        )}
        {responsePayload !== undefined && (
          <>
            <Text type="secondary">LLM响应参数</Text>
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{toDisplayText(responsePayload)}</pre>
          </>
        )}
        {outputJson !== undefined && (
          <>
            <Text type="secondary">结构化输出</Text>
            <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{toDisplayText(outputJson)}</pre>
          </>
        )}
        {error && <Alert type="error" showIcon message={error} />}
        {!hasFriendlyBlocks && (
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{toDisplayText(data)}</pre>
        )}
      </Space>
    );
  };

  const inferStepForEvent = (row: EventRecord): number => {
    const data = (row.data || {}) as Record<string, unknown>;
    const phase = String(data.phase || '').toLowerCase();
    const stage = String(data.stage || '').toLowerCase();
    const kind = row.kind.toLowerCase();

    if (phase.includes('report') || stage.includes('report') || kind.includes('report')) {
      return 3;
    }
    if (phase.includes('asset') || stage.includes('asset')) {
      return 1;
    }
    if (
      phase.includes('debating') ||
      phase.includes('failed') ||
      phase === 'analysis' ||
      phase.includes('critique') ||
      phase.includes('rebuttal') ||
      phase.includes('judgment') ||
      stage.includes('debate') ||
      kind.startsWith('llm_call_') ||
      kind.startsWith('llm_prompt_') ||
      kind.startsWith('round_') ||
      kind === 'agent_round' ||
      kind === 'session_failed' ||
      kind === 'error'
    ) {
      return 2;
    }
    return 1;
  };

  const advanceStep = (nextStep: number) => {
    setCurrentStep((prev) => (nextStep > prev ? nextStep : prev));
    setActiveStep((prev) => (nextStep > prev ? nextStep : prev));
  };

  const loadSessionArtifacts = async (sid: string, iid: string) => {
    const [detail, result, rpt, fusing] = await Promise.all([
      debateApi.get(sid),
      debateApi.getResult(sid).catch(() => null),
      reportApi.get(iid).catch(() => null),
      assetApi.fusion(iid).catch(() => null),
    ]);
    setSessionDetail(detail);
    setDebateResult(result);
    setReport(rpt);
    setFusion(fusing);

    const persisted = (detail.context as Record<string, unknown> | undefined)?.event_log;
    if (Array.isArray(persisted)) {
      setEventRecords((prev) => {
        if (prev.length > 0) return prev;
        return persisted
          .slice(0, 300)
          .map((item, idx) => {
            const row = (item || {}) as Record<string, unknown>;
            const event = (row.event || {}) as Record<string, unknown>;
            const ts = typeof row.timestamp === 'string' ? row.timestamp : '';
            const kind = typeof event.type === 'string' ? event.type : 'event';
            return {
              id: `persisted_${idx}_${ts || kind}`,
              timeText: ts ? new Date(ts).toLocaleTimeString() : '--:--:--',
              kind,
              text: formatEventText(kind, event),
              data: event,
            } as EventRecord;
          })
          .reverse();
      });
    }
    return detail;
  };

  const createIncidentAndSession = async () => {
    if (!incidentForm.title.trim()) {
      message.error('请填写故障标题');
      return;
    }
    setLoading(true);
    try {
      const incident = await incidentApi.create({
        title: incidentForm.title,
        description: incidentForm.description,
        severity: incidentForm.severity,
        log_content: incidentForm.log_content,
        service_name: incidentForm.service_name,
        environment: incidentForm.environment,
      });
      const session = await debateApi.createSession(incident.id);
      setIncidentId(incident.id);
      setSessionId(session.id);
      advanceStep(1);
      appendEvent('session_created_local', `会话已创建 ${session.id}`, { session_id: session.id });
      message.success('故障会话创建成功');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '创建失败');
    } finally {
      setLoading(false);
    }
  };

  const initSessionForExistingIncident = async () => {
    if (!incidentId) return;
    setLoading(true);
    try {
      const session = await debateApi.createSession(incidentId);
      setSessionId(session.id);
      appendEvent('session_created_local', `会话已创建 ${session.id}`, { session_id: session.id });
      advanceStep(1);
      message.success('已初始化辩论会话');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '初始化会话失败');
    } finally {
      setLoading(false);
    }
  };

  const pollResultUntilReady = async (sid: string, iid: string) => {
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      const maxAttempts = 60;
      for (let i = 0; i < maxAttempts; i += 1) {
        const [detail, result] = await Promise.all([
          debateApi.get(sid).catch(() => null),
          debateApi.getResult(sid).catch(() => null),
        ]);
        if (detail) {
          setSessionDetail(detail);
        }
        if (result) {
          appendEvent('result_polled', '后台任务已完成，正在刷新结果');
          setDebateResult(result);
          await loadSessionArtifacts(sid, iid);
          advanceStep(3);
          setRunning(false);
          return;
        }
        const status = String(detail?.status || '').toLowerCase();
        if (status === 'failed') {
          const error = extractSessionError(detail);
          appendEvent(
            'session_failed',
            `会话执行失败${error ? `: ${error}` : ''}`,
            { type: 'session_failed', phase: 'failed', status: 'failed', error },
          );
          advanceStep(2);
          setRunning(false);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 5000));
      }
      appendEvent('result_timeout', '等待结果超时，请稍后点击“辩论结果”查看最新状态');
    } finally {
      pollingRef.current = false;
      setRunning(false);
    }
  };

  const startRealtimeDebate = async () => {
    if (!sessionId || !incidentId) return;
    setRunning(true);
    appendEvent('start', '开始实时辩论');

    try {
      const ws = new WebSocket(buildDebateWsUrl(sessionId));
      wsRef.current = ws;

      ws.onopen = () => {
        appendEvent('ws_open', 'WebSocket 已连接');
      };

      ws.onmessage = async (event) => {
        try {
          const payload = JSON.parse(event.data) as { type: string; data?: any; message?: string };
          if (payload.type === 'event') {
            const type = payload.data?.type || 'event';
            appendEvent(type, formatEventText(type, payload.data || {}), payload.data);
            if (type === 'session_failed') {
              setRunning(false);
              advanceStep(2);
              await loadSessionArtifacts(sessionId, incidentId).catch(() => undefined);
              return;
            }
            const eventPhase = String(payload.data?.phase || '').toLowerCase();
            if (
              (type === 'autogen_call_started' || type === 'opencode_call_started') &&
              eventPhase.includes('asset')
            ) {
              advanceStep(1);
            }
            if (type === 'agent_round' || type === 'round_started' || type === 'llm_call_started') {
              advanceStep(2);
            }
            if (
              (type === 'autogen_call_started' || type === 'opencode_call_started') &&
              eventPhase.includes('report')
            ) {
              advanceStep(3);
            }
            return;
          }
          if (payload.type === 'snapshot') {
            appendEvent('snapshot', `快照: ${payload.data?.status || 'unknown'}`, payload.data);
            if (String(payload.data?.status || '').toLowerCase() === 'failed') {
              setRunning(false);
              advanceStep(2);
            }
            return;
          }
          if (payload.type === 'result') {
            appendEvent('result', '辩论完成，正在加载报告', payload.data);
            if (payload.data) {
              setDebateResult((prev) => ({
                ...(prev || {
                  session_id: payload.data.session_id,
                  incident_id: payload.data.incident_id,
                  root_cause: payload.data.root_cause || '-',
                  confidence: payload.data.confidence || 0,
                  created_at: payload.data.created_at,
                }),
                root_cause: payload.data.root_cause || prev?.root_cause || '-',
                confidence: payload.data.confidence ?? prev?.confidence ?? 0,
              }));
            }
            await loadSessionArtifacts(sessionId, incidentId);
            advanceStep(3);
            setRunning(false);
            return;
          }
          if (payload.type === 'error') {
            appendEvent('error', `错误: ${payload.message || 'unknown'}`, payload);
            setRunning(false);
            await loadSessionArtifacts(sessionId, incidentId).catch(() => undefined);
            advanceStep(2);
          }
        } catch {
          appendEvent('unknown_payload', '收到非结构化消息');
        }
      };

      ws.onerror = async () => {
        appendEvent('ws_error', 'WebSocket 连接异常，改为后台轮询结果');
        await pollResultUntilReady(sessionId, incidentId);
      };

      ws.onclose = () => {
        appendEvent('ws_close', 'WebSocket 已关闭');
        if (runningRef.current) {
          void pollResultUntilReady(sessionId, incidentId);
        }
      };
    } catch (e: any) {
      message.error(e?.message || '启动失败');
      setRunning(false);
    }
  };

  const regenerateReport = async () => {
    if (!incidentId) return;
    setLoading(true);
    try {
      const rpt = await reportApi.regenerate(incidentId);
      setReport(rpt);
      message.success('报告已重新生成');
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || '报告重新生成失败';
      message.error(detail);
    } finally {
      setLoading(false);
    }
  };

  const generateShareLink = async () => {
    if (!incidentId) return;
    setLoading(true);
    try {
      const share = await reportApi.share(incidentId);
      setShareUrl(share.share_url);
      message.success('分享链接已生成');
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || '生成分享链接失败';
      message.error(detail);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const iid = routeIncidentId || searchParams.get('incident_id');
    const preferredView = (searchParams.get('view') || '').toLowerCase();
    if (!iid) return;
    setIncidentId(iid);
    incidentApi
      .get(iid)
      .then(async (incident) => {
        setIncidentForm((prev) => ({
          ...prev,
          title: incident.title || '',
          description: incident.description || '',
          severity: incident.severity || 'medium',
          service_name: incident.service_name || '',
        }));
        if (incident.debate_session_id) {
          setSessionId(incident.debate_session_id);
          const detail = await loadSessionArtifacts(incident.debate_session_id, iid);
          const status = detail?.status || '';
          if (preferredView === 'report') {
            advanceStep(3);
          } else if (preferredView === 'analysis') {
            advanceStep(1);
          } else if (status === 'completed') {
            advanceStep(3);
          } else {
            advanceStep(1);
          }
        } else if (preferredView === 'analysis') {
          advanceStep(0);
        }
      })
      .catch(() => undefined);
  }, [searchParams, routeIncidentId]);

  useEffect(() => {
    runningRef.current = running;
  }, [running]);

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const stageEvents =
    activeStep === 0 ? [] : eventRecords.filter((row) => inferStepForEvent(row) === activeStep);

  const roundCollapseItems = (sessionDetail?.rounds || []).map((round) => ({
    key: `${round.round_number}_${round.agent_name}_${round.phase}`,
    label: `${round.round_number}. ${round.agent_name} (${round.phase}) - ${(round.confidence * 100).toFixed(1)}%`,
    children: (
      <Space direction="vertical" style={{ width: '100%' }}>
        <Text type="secondary">模型：{String(round.model?.name || 'kimi-k2.5')}</Text>
        <Text type="secondary">输入片段：</Text>
        <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{round.input_message || '无'}</pre>
        <Text type="secondary">输出内容：</Text>
        <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
          {JSON.stringify(round.output_content || {}, null, 2)}
        </pre>
      </Space>
    ),
  }));

  return (
    <div className="incident-page">
      <Card>
        <Steps current={currentStep} items={steps} onChange={(idx) => setActiveStep(idx)} />
        <Space style={{ marginTop: 16 }}>
          <Button onClick={() => setActiveStep(0)}>输入故障信息</Button>
          <Button onClick={() => setActiveStep(1)}>
            资产与辩论
          </Button>
          <Button onClick={() => setActiveStep(2)}>
            辩论结果
          </Button>
          <Button onClick={() => setActiveStep(3)}>
            报告与图谱
          </Button>
          <Tag color="processing">当前查看：{steps[activeStep]?.title}</Tag>
        </Space>
      </Card>

      <div style={{ marginTop: 24 }}>
        {activeStep === 0 && (
          <Card title="故障输入">
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Input
                placeholder="故障标题 *"
                value={incidentForm.title}
                onChange={(e) => setIncidentForm((s) => ({ ...s, title: e.target.value }))}
              />
              <Input
                placeholder="故障描述"
                value={incidentForm.description}
                onChange={(e) => setIncidentForm((s) => ({ ...s, description: e.target.value }))}
              />
              <Space style={{ width: '100%' }}>
                <Select
                  value={incidentForm.severity}
                  style={{ width: 180 }}
                  onChange={(value) => setIncidentForm((s) => ({ ...s, severity: value }))}
                  options={[
                    { label: 'Critical', value: 'critical' },
                    { label: 'High', value: 'high' },
                    { label: 'Medium', value: 'medium' },
                    { label: 'Low', value: 'low' },
                  ]}
                />
                <Input
                  placeholder="服务名（可选）"
                  value={incidentForm.service_name}
                  onChange={(e) => setIncidentForm((s) => ({ ...s, service_name: e.target.value }))}
                />
              </Space>
              <TextArea
                rows={10}
                className="log-input-area"
                placeholder="粘贴日志内容"
                value={incidentForm.log_content}
                onChange={(e) => setIncidentForm((s) => ({ ...s, log_content: e.target.value }))}
              />
              {!incidentId && (
                <Button type="primary" loading={loading} onClick={createIncidentAndSession}>
                  创建故障并初始化辩论会话
                </Button>
              )}
              {incidentId && !sessionId && (
                <Button loading={loading} onClick={initSessionForExistingIncident}>
                  使用当前故障初始化会话
                </Button>
              )}
            </Space>
          </Card>
        )}

        {activeStep === 1 && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="会话信息">
              <Descriptions column={2}>
                <Descriptions.Item label="Incident ID">{incidentId || '-'}</Descriptions.Item>
                <Descriptions.Item label="Session ID">{sessionId || '-'}</Descriptions.Item>
                <Descriptions.Item label="实时状态">
                  {running ? <Tag color="processing">运行中</Tag> : <Tag>待启动/已完成</Tag>}
                </Descriptions.Item>
              </Descriptions>
              <Button type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={startRealtimeDebate}>
                启动实时辩论
              </Button>
            </Card>

            <Card title="资产与辩论过程记录">
              {stageEvents.length === 0 ? (
                <Text type="secondary">尚无过程记录</Text>
              ) : (
                <Timeline
                  items={stageEvents.map((row) => ({
                    children: `${row.timeText} [${row.kind}] ${row.text}`,
                  }))}
                />
              )}
            </Card>

            <Card title="事件明细">
              {stageEvents.length === 0 ? (
                <Text type="secondary">暂无明细</Text>
              ) : (
                <Collapse
                  items={stageEvents.map((row) => ({
                    key: row.id,
                    label: `${row.timeText} [${row.kind}] ${row.text}`,
                    children: formatEventDetail(row),
                  }))}
                />
              )}
            </Card>
          </Space>
        )}

        {activeStep === 2 && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="分析过程记录">
              {stageEvents.length === 0 ? (
                <Text type="secondary">尚无过程记录</Text>
              ) : (
                <Timeline
                  items={stageEvents.map((row) => ({
                    children: `${row.timeText} [${row.kind}] ${row.text}`,
                  }))}
                />
              )}
            </Card>

            <Card title="辩论结论">
              {debateResult ? (
                <>
                  <Paragraph>
                    <Text strong>根因：</Text>
                    {debateResult.root_cause || '-'}
                  </Paragraph>
                  <Paragraph>
                    <Text strong>置信度：</Text>
                    {(debateResult.confidence * 100).toFixed(1)}%
                  </Paragraph>
                  <Progress percent={Number((debateResult.confidence * 100).toFixed(1))} />
                </>
              ) : sessionDetail?.status === 'failed' ? (
                <Alert
                  type="error"
                  showIcon
                  message={`辩论失败：${extractSessionError(sessionDetail) || '请查看过程记录中的错误详情'}`}
                />
              ) : (
                <Alert type="info" message="辩论执行中，请等待结果" />
              )}
            </Card>

            <Card title="辩论轮次过程（可展开查看每轮输入输出）">
              {roundCollapseItems.length === 0 ? (
                <Text type="secondary">暂无轮次数据</Text>
              ) : (
                <Collapse items={roundCollapseItems} />
              )}
            </Card>

            <Card title="事件明细">
              {stageEvents.length === 0 ? (
                <Text type="secondary">暂无明细</Text>
              ) : (
                <Collapse
                  items={stageEvents.map((row) => ({
                    key: row.id,
                    label: `${row.timeText} [${row.kind}] ${row.text}`,
                    children: formatEventDetail(row),
                  }))}
                />
              )}
            </Card>
          </Space>
        )}

        {activeStep === 3 && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="报告阶段过程记录">
              {stageEvents.length === 0 ? (
                <Text type="secondary">尚无过程记录</Text>
              ) : (
                <Timeline
                  items={stageEvents.map((row) => ({
                    children: `${row.timeText} [${row.kind}] ${row.text}`,
                  }))}
                />
              )}
            </Card>

            <Card title="报告阶段事件明细">
              {stageEvents.length === 0 ? (
                <Text type="secondary">暂无明细</Text>
              ) : (
                <Collapse
                  items={stageEvents.map((row) => ({
                    key: row.id,
                    label: `${row.timeText} [${row.kind}] ${row.text}`,
                    children: formatEventDetail(row),
                  }))}
                />
              )}
            </Card>

            <Card
              title="分析报告"
              extra={
                <Space>
                  <Button icon={<ReloadOutlined />} loading={loading} onClick={regenerateReport}>
                    重新生成
                  </Button>
                  <Button icon={<LinkOutlined />} loading={loading} onClick={generateShareLink}>
                    生成分享链接
                  </Button>
                </Space>
              }
            >
              {shareUrl && <Alert type="success" message={`分享地址：${shareUrl}`} showIcon style={{ marginBottom: 12 }} />}
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{report?.content || '暂无报告'}</pre>
            </Card>
            <Card title="资产融合结果">
              {fusion ? (
                <Descriptions column={2}>
                  <Descriptions.Item label="运行态资产">{fusion.runtime_assets.length}</Descriptions.Item>
                  <Descriptions.Item label="开发态资产">{fusion.dev_assets.length}</Descriptions.Item>
                  <Descriptions.Item label="设计态资产">{fusion.design_assets.length}</Descriptions.Item>
                  <Descriptions.Item label="关联关系">{fusion.relationships.length}</Descriptions.Item>
                </Descriptions>
              ) : (
                <Text type="secondary">暂无融合结果</Text>
              )}
            </Card>
          </Space>
        )}
      </div>
    </div>
  );
};

export default IncidentPage;
