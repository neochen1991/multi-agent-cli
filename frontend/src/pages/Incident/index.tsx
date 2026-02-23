import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
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
import { formatBeijingDateTime, formatBeijingTime } from '@/utils/dateTime';

const { TextArea } = Input;
const { Paragraph, Text } = Typography;

type EventRecord = {
  id: string;
  timeText: string;
  kind: string;
  text: string;
  data?: unknown;
};

type DialogueMessage = {
  id: string;
  timeText: string;
  agentName: string;
  side: 'agent' | 'system';
  phase: string;
  eventType: string;
  traceId: string;
  latencyMs?: number;
  status: 'streaming' | 'done' | 'error';
  summary: string;
  detail: string;
};

const IncidentPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { incidentId: routeIncidentId } = useParams();
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
  const [streamedMessageText, setStreamedMessageText] = useState<Record<string, string>>({});
  const [expandedDialogueIds, setExpandedDialogueIds] = useState<Record<string, boolean>>({});
  const [eventFilterAgent, setEventFilterAgent] = useState<string>('all');
  const [eventFilterPhase, setEventFilterPhase] = useState<string>('all');
  const [eventFilterType, setEventFilterType] = useState<string>('all');
  const [eventSearchText, setEventSearchText] = useState<string>('');
  const [running, setRunning] = useState(false);
  const [debateMaxRounds, setDebateMaxRounds] = useState<number>(1);
  const wsRef = useRef<WebSocket | null>(null);
  const pollingRef = useRef(false);
  const runningRef = useRef(false);
  const streamTimersRef = useRef<Record<string, number>>({});
  const seenEventIdsRef = useRef<Set<string>>(new Set());

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
    const eventId = String(dataRecord.event_id || '').trim();
    if (eventId) {
      if (seenEventIdsRef.current.has(eventId)) {
        return;
      }
      seenEventIdsRef.current.add(eventId);
    }
    const eventTsRaw = String(dataRecord.timestamp || '').trim();
    const displayTime =
      eventTsRaw
        ? formatBeijingDateTime(eventTsRaw)
        : formatBeijingDateTime(new Date());
    const record: EventRecord = {
      id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
      timeText: displayTime,
      kind,
      text,
      data,
    };
    setEventRecords((prev) => {
      if (kind === 'llm_stream_delta') {
        const streamId = String(dataRecord.stream_id || '').trim();
        if (streamId) {
          const idx = prev.findIndex((row) => {
            if (row.kind !== 'llm_stream_delta') return false;
            const rowData = asRecord(row.data);
            return String(rowData.stream_id || '').trim() === streamId;
          });
          if (idx >= 0) {
            const current = prev[idx];
            const currentData = asRecord(current.data);
            const mergedData = {
              ...currentData,
              ...dataRecord,
              delta: `${String(currentData.delta || '')}${String(dataRecord.delta || '')}`,
            };
            const mergedRow: EventRecord = {
              ...current,
              timeText: displayTime,
              text: formatEventText(kind, mergedData),
              data: mergedData,
            };
            const next = [...prev];
            next[idx] = mergedRow;
            return next.slice(0, 300);
          }
        }
      }
      return [record, ...prev].slice(0, 300);
    });
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

  const normalizeInlineText = (value: string): string =>
    value
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1 ($2)')
      .trim();

  const normalizeMarkdownText = (value: string): string =>
    value
      .replace(/\r/g, '')
      .split('\n')
      .map((line) => line.replace(/^\s{0,3}#{1,6}\s+/, '').replace(/^\s*[-*]\s+/, '• '))
      .join('\n');

  const buildDialogueMessage = (row: EventRecord): DialogueMessage | null => {
    const data = asRecord(row.data);
    const kind = row.kind;
    const phase = String(data.phase || '');
    const agentRaw = firstTextValue(data, ['agent_name', 'agent']) || '';
    const agentName = agentRaw || 'System';
    const prompt = firstTextValue(data, ['prompt_preview', 'input_message', 'prompt', 'command']);
    const output = firstTextValue(data, [
      'response_preview',
      'output_preview',
      'content_preview',
      'text_preview',
      'event_preview',
      'stderr_preview',
    ]);
    const outputJson = data.output_json;
    const messageText = row.text || '';

    const isRequestKind =
      kind === 'llm_prompt_started' ||
      kind === 'autogen_call_started' ||
      kind === 'llm_stream_delta';
    const isResponseKind =
      kind === 'llm_prompt_completed' ||
      kind === 'llm_cli_command_completed' ||
      kind === 'autogen_call_completed' ||
      kind === 'agent_round';
    const isErrorKind =
      kind === 'autogen_call_failed' ||
      kind === 'llm_prompt_failed' ||
      kind === 'llm_cli_command_failed' ||
      kind === 'session_failed';

    const side: 'agent' | 'system' = agentRaw ? 'agent' : 'system';
    let status: 'streaming' | 'done' | 'error' = 'done';
    let summary = normalizeInlineText(messageText || kind);
    let detail = '';

    if (kind === 'llm_stream_delta') {
      status = 'streaming';
      summary = `${agentName} 正在输出`;
      detail = normalizeMarkdownText(firstTextValue(data, ['delta']) || '...');
    } else if (
      kind === 'autogen_call_completed' &&
      ['analysis', 'critique', 'rebuttal', 'judgment'].includes(phase)
    ) {
      // 辩论阶段优先展示 agent_round，避免 completed 与 round 双重重复
      return null;
    } else if (isRequestKind) {
      status = 'streaming';
      summary = `${agentName} 开始分析`;
      detail = normalizeMarkdownText(prompt || messageText || '正在调用模型，请稍候...');
    } else if (isResponseKind) {
      status = 'done';
      summary = `${agentName} 输出结论`;
      if (typeof outputJson !== 'undefined') {
        detail = normalizeMarkdownText(toDisplayText(outputJson));
      } else {
        detail = normalizeMarkdownText(output || messageText || '已完成该轮分析');
      }
    } else if (isErrorKind) {
      status = 'error';
      summary = `${agentName} 分析异常`;
      detail = normalizeMarkdownText(firstTextValue(data, ['error', 'message']) || messageText);
    } else if (kind === 'asset_interface_mapping_completed') {
      const matched = typeof data.matched === 'boolean' ? (data.matched ? '命中' : '未命中') : '未知';
      const domain = firstTextValue(data, ['domain']) || '-';
      const aggregate = firstTextValue(data, ['aggregate']) || '-';
      const ownerTeam = firstTextValue(data, ['owner_team']) || '-';
      const confidence =
        typeof data.confidence === 'number' ? `${(Number(data.confidence) * 100).toFixed(1)}%` : '-';
      status = 'done';
      summary = `责任田映射${matched}`;
      detail = normalizeMarkdownText(
        [
          `命中状态: ${matched}`,
          `领域: ${domain}`,
          `聚合根: ${aggregate}`,
          `责任团队: ${ownerTeam}`,
          `置信度: ${confidence}`,
        ].join('\n'),
      );
    } else if (kind === 'asset_collection_completed' || kind === 'runtime_assets_collected') {
      status = 'done';
      summary = normalizeInlineText(messageText || '资产采集完成');
      detail = normalizeMarkdownText(toDisplayText(data) || messageText || '资产采集阶段已完成');
    } else if (kind === 'phase_changed' || kind === 'snapshot' || kind === 'session_started' || kind === 'ws_ack' || kind === 'ws_control') {
      summary = normalizeInlineText(messageText || '状态更新');
      detail = normalizeMarkdownText(messageText || '');
    } else {
      return null;
    }

    return {
      id: row.id,
      timeText: row.timeText,
      agentName,
      side,
      phase,
      eventType: kind,
      traceId: firstTextValue(data, ['trace_id']) || '-',
      latencyMs: typeof data.latency_ms === 'number' ? Number(data.latency_ms) : undefined,
      status,
      summary,
      detail,
    };
  };

  const formatEventText = (kind: string, data?: Record<string, unknown>) => {
    const phase = String(data?.phase || '');
    const stage = String(data?.stage || '');
    const model = String(data?.model || '');
    const latency = typeof data?.latency_ms === 'number' ? `${data.latency_ms}ms` : '';
    const agent = String(data?.agent_name || '');
    const error = String(data?.error || '');
    switch (kind) {
      case 'autogen_call_started':
        return `AutoGen请求开始 [${phase || stage || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'autogen_call_completed':
        return `AutoGen请求完成 [${phase || stage || '-'}] ${agent || ''} ${model || ''} ${latency}`.trim();
      case 'autogen_call_timeout':
        return `AutoGen请求超时，已自动降级继续 [${phase || stage || '-'}] ${agent || ''}`.trim();
      case 'autogen_call_failed':
        if (error.toLowerCase().includes('timeout')) {
          return `AutoGen请求超时，已自动降级继续 [${phase || stage || '-'}] ${agent || ''}`.trim();
        }
        return `AutoGen请求异常，已自动降级继续 [${phase || stage || '-'}] ${agent || ''} ${model || ''} ${error}`.trim();
      case 'llm_call_started':
        return `辩论LLM开始 [${phase || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'llm_call_completed':
        return `辩论LLM完成 [${phase || '-'}] ${agent || ''} ${model || ''} ${latency}`.trim();
      case 'llm_call_timeout':
        return `辩论LLM超时，已自动降级继续 [${phase || '-'}] ${agent || ''}`.trim();
      case 'llm_call_failed':
        if (error.toLowerCase().includes('timeout')) {
          return `辩论LLM超时，已自动降级继续 [${phase || '-'}] ${agent || ''}`.trim();
        }
        return `辩论LLM异常，已自动降级继续 [${phase || '-'}] ${agent || ''} ${error}`.trim();
      case 'llm_http_request':
        return `LLM请求参数 [${phase || stage || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'llm_http_response':
        return `LLM响应参数 [${phase || stage || '-'}] ${agent || ''} ${model || ''}`.trim();
      case 'llm_http_error':
        if (error.toLowerCase().includes('timeout')) {
          return `LLM响应超时 [${phase || stage || '-'}] ${agent || ''}，系统将自动降级`.trim();
        }
        return `LLM响应异常 [${phase || stage || '-'}] ${agent || ''} ${error || String(data?.status_code || '')}`.trim();
      case 'llm_stream_delta':
        return `LLM流式输出 [${phase || stage || '-'}] ${agent || ''} chunk=${String(data?.chunk_index || '-')}/${String(data?.chunk_total || '-')}`.trim();
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
      case 'agent_round_skipped':
        return `Agent轮次已降级 [${phase || '-'}] ${agent || ''} ${String(data?.reason || '')}`.trim();
      case 'session_failed':
        return `会话失败 ${error}`.trim();
      case 'ws_ack':
        return `控制指令确认 ${String(data?.message || '')}`.trim();
      case 'ws_control':
        return `控制指令 ${String(data?.action || '-')}`.trim();
      default:
        return `事件: ${kind}`;
    }
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
    const config = ((detail.context as Record<string, unknown> | undefined) || {})
      .debate_config as Record<string, unknown> | undefined;
    const maxRoundsRaw = config?.max_rounds;
    if (typeof maxRoundsRaw === 'number' && Number.isFinite(maxRoundsRaw)) {
      setDebateMaxRounds(Math.max(1, Math.min(8, Math.trunc(maxRoundsRaw))));
    }

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
              timeText: ts ? formatBeijingTime(ts) : '--:--:--',
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
      const session = await debateApi.createSession(incident.id, { maxRounds: debateMaxRounds });
      seenEventIdsRef.current.clear();
      setEventRecords([]);
      setStreamedMessageText({});
      setExpandedDialogueIds({});
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
      const session = await debateApi.createSession(incidentId, { maxRounds: debateMaxRounds });
      seenEventIdsRef.current.clear();
      setEventRecords([]);
      setStreamedMessageText({});
      setExpandedDialogueIds({});
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
              type === 'autogen_call_started' &&
              eventPhase.includes('asset')
            ) {
              advanceStep(1);
            }
            if (type === 'agent_round' || type === 'round_started' || type === 'llm_call_started') {
              advanceStep(2);
            }
            if (
              type === 'autogen_call_started' &&
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
          if (payload.type === 'ack') {
            appendEvent('ws_ack', `控制指令已确认: ${payload.message || '-'}`, payload);
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

  const sendWsControl = async (action: 'cancel' | 'resume') => {
    if (!sessionId) return;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(action);
      appendEvent(
        'ws_control',
        action === 'cancel' ? '已发送取消指令' : '已发送恢复指令',
        { type: 'ws_control', action },
      );
      return;
    }

    if (action === 'cancel') {
      try {
        const res = await debateApi.cancel(sessionId);
        if (res.cancelled) {
          appendEvent('session_cancelled', '会话已取消', {
            type: 'session_cancelled',
            phase: 'cancelled',
            status: 'cancelled',
          });
          setRunning(false);
          message.success('会话已取消');
        } else {
          message.info('当前无可取消的运行任务');
        }
      } catch (e: any) {
        message.error(e?.response?.data?.detail || e?.message || '取消失败');
      }
      return;
    }
    void startRealtimeDebate();
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
    seenEventIdsRef.current.clear();
    setEventRecords([]);
    setStreamedMessageText({});
    setExpandedDialogueIds({});
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
      Object.values(streamTimersRef.current).forEach((timerId) => window.clearInterval(timerId));
      streamTimersRef.current = {};
    };
  }, []);

  const stageEvents =
    activeStep === 0 ? [] : eventRecords.filter((row) => inferStepForEvent(row) === activeStep);

  const dialogueMessages = useMemo(
    () =>
      stageEvents
        .slice()
        .reverse()
        .map((row) => buildDialogueMessage(row))
        .filter((item): item is DialogueMessage => Boolean(item)),
    [stageEvents],
  );

  const filteredDialogueMessages = useMemo(() => {
    const q = eventSearchText.trim().toLowerCase();
    return dialogueMessages.filter((msg) => {
      if (eventFilterAgent !== 'all' && msg.agentName !== eventFilterAgent) return false;
      if (eventFilterPhase !== 'all' && (msg.phase || '-') !== eventFilterPhase) return false;
      if (eventFilterType !== 'all' && msg.eventType !== eventFilterType) return false;
      if (!q) return true;
      const haystack = `${msg.summary}\n${msg.detail}\n${msg.eventType}\n${msg.traceId}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [dialogueMessages, eventFilterAgent, eventFilterPhase, eventFilterType, eventSearchText]);

  const filteredStageEvents = useMemo(() => {
    const includeIds = new Set(filteredDialogueMessages.map((item) => item.id));
    return stageEvents.filter((row) => includeIds.has(row.id));
  }, [stageEvents, filteredDialogueMessages]);

  const eventFilterOptions = useMemo(() => {
    const agentSet = new Set<string>();
    const phaseSet = new Set<string>();
    const typeSet = new Set<string>();
    dialogueMessages.forEach((item) => {
      if (item.agentName) agentSet.add(item.agentName);
      phaseSet.add(item.phase || '-');
      typeSet.add(item.eventType);
    });
    return {
      agents: ['all', ...Array.from(agentSet).sort()],
      phases: ['all', ...Array.from(phaseSet).sort()],
      types: ['all', ...Array.from(typeSet).sort()],
    };
  }, [dialogueMessages]);

  useEffect(() => {
    const currentIds = new Set(filteredDialogueMessages.map((item) => item.id));
    setStreamedMessageText((prev) => {
      const next: Record<string, string> = {};
      for (const [key, value] of Object.entries(prev)) {
        if (currentIds.has(key)) next[key] = value;
      }
      return next;
    });

    Object.entries(streamTimersRef.current).forEach(([id, timerId]) => {
      if (!currentIds.has(id)) {
        window.clearInterval(timerId);
        delete streamTimersRef.current[id];
      }
    });

    filteredDialogueMessages.forEach((message, index) => {
      const isRecent = index >= Math.max(0, filteredDialogueMessages.length - 8);
      if (!isRecent) {
        setStreamedMessageText((prev) =>
          prev[message.id] === message.detail ? prev : { ...prev, [message.id]: message.detail },
        );
        return;
      }
      if (streamTimersRef.current[message.id]) return;
      setStreamedMessageText((prev) => {
        if (typeof prev[message.id] === 'string' && prev[message.id].length > 0) return prev;
        return { ...prev, [message.id]: '' };
      });

      const content = message.detail || '';
      if (!content) {
        setStreamedMessageText((prev) => ({ ...prev, [message.id]: '' }));
        return;
      }

      streamTimersRef.current[message.id] = window.setInterval(() => {
        setStreamedMessageText((prev) => {
          const current = prev[message.id] || '';
          if (current.length >= content.length) {
            const timerId = streamTimersRef.current[message.id];
            if (timerId) {
              window.clearInterval(timerId);
              delete streamTimersRef.current[message.id];
            }
            return prev;
          }
          const step = Math.max(2, Math.ceil(content.length / 120));
          const nextText = content.slice(0, current.length + step);
          return { ...prev, [message.id]: nextText };
        });
      }, 18);
    });
  }, [filteredDialogueMessages]);

  const reportSections = useMemo(() => {
    const content = report?.content || '';
    if (!content.trim()) return [];
    const lines = content.replace(/\r/g, '').split('\n');
    const sections: Array<{ title: string; lines: string[] }> = [];
    let currentTitle = '报告概览';
    let currentLines: string[] = [];
    const pushCurrent = () => {
      if (currentLines.length === 0) return;
      sections.push({ title: currentTitle, lines: [...currentLines] });
      currentLines = [];
    };
    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      if (/^#\s+/.test(line)) continue;
      const sectionMatch = /^##\s+(.+)$/.exec(line.trim());
      if (sectionMatch) {
        pushCurrent();
        currentTitle = normalizeInlineText(sectionMatch[1]);
        continue;
      }
      if (line.trim() === '---') continue;
      currentLines.push(line);
    }
    pushCurrent();
    if (sections.length === 0) {
      return [{ title: '报告详情', lines }];
    }
    return sections;
  }, [report?.content]);

  const renderReportSectionBody = (lines: string[]) => {
    const blocks: React.ReactNode[] = [];
    let listBuffer: string[] = [];
    const flushList = () => {
      if (listBuffer.length === 0) return;
      blocks.push(
        <ul key={`list_${blocks.length}`} style={{ paddingInlineStart: 18, marginBottom: 12 }}>
          {listBuffer.map((item, index) => (
            <li key={`${item}_${index}`} style={{ marginBottom: 6 }}>
              {normalizeInlineText(item)}
            </li>
          ))}
        </ul>,
      );
      listBuffer = [];
    };

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        flushList();
        continue;
      }
      const listMatch = /^[-*]\s+(.+)$/.exec(trimmed) || /^\d+\.\s+(.+)$/.exec(trimmed);
      if (listMatch) {
        listBuffer.push(listMatch[1]);
        continue;
      }
      flushList();
      const text = normalizeInlineText(trimmed.replace(/^###\s+/, ''));
      blocks.push(
        <Paragraph key={`p_${blocks.length}`} style={{ marginBottom: 10 }}>
          {text}
        </Paragraph>,
      );
    }
    flushList();
    if (blocks.length === 0) {
      return <Text type="secondary">暂无内容</Text>;
    }
    return <>{blocks}</>;
  };

  const buildCompactDetail = (value: string): string => {
    const normalized = normalizeMarkdownText(value || '');
    const lines = normalized
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    if (lines.length === 0) return '';
    const compact = lines.slice(0, 3).join('\n');
    if (compact.length > 220) {
      return `${compact.slice(0, 220).trim()}...`;
    }
    if (lines.length > 3) return `${compact}\n...`;
    return compact;
  };

  const renderDialogueStream = () => {
    if (filteredDialogueMessages.length === 0) {
      return <Empty description="暂无匹配的事件明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    }
    return (
      <div className="dialogue-stream">
        {filteredDialogueMessages.map((msg) => {
          const renderedText = streamedMessageText[msg.id] ?? '';
          const fullText = msg.status === 'streaming' ? renderedText : msg.detail;
          const compactText = buildCompactDetail(fullText || msg.detail);
          const showCursor =
            msg.status === 'streaming' && renderedText.length < (msg.detail || '').length;
          const isExpanded = Boolean(expandedDialogueIds[msg.id]);
          const canExpand = (msg.detail || '').length > 220 || (msg.detail || '').split('\n').length > 3;
          return (
            <div
              key={msg.id}
              className={`dialogue-row ${msg.side === 'agent' ? 'dialogue-row-agent' : 'dialogue-row-system'}`}
            >
              <Avatar size="small" className="dialogue-avatar">
                {msg.agentName.slice(0, 1).toUpperCase()}
              </Avatar>
              <div className={`dialogue-bubble dialogue-bubble-${msg.status}`}>
                <div className="dialogue-meta">
                  <Text strong>{msg.agentName}</Text>
                  {msg.phase && <Tag style={{ marginLeft: 8 }}>{msg.phase}</Tag>}
                  <Tag style={{ marginLeft: 8 }}>{msg.eventType}</Tag>
                  {msg.latencyMs ? <Tag color="blue">{`${msg.latencyMs}ms`}</Tag> : null}
                  {msg.traceId && msg.traceId !== '-' ? <Tag>{`trace:${msg.traceId}`}</Tag> : null}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    {msg.timeText}
                  </Text>
                </div>
                <Paragraph style={{ marginBottom: 8 }}>{msg.summary}</Paragraph>
                {isExpanded ? (
                  <pre className="dialogue-content">
                    {fullText}
                    {showCursor ? <span className="dialogue-cursor">▋</span> : ''}
                  </pre>
                ) : (
                  <pre className="dialogue-content dialogue-content-compact">
                    {compactText || '暂无关键信息'}
                    {showCursor ? <span className="dialogue-cursor">▋</span> : ''}
                  </pre>
                )}
                {canExpand && (
                  <Button
                    type="link"
                    size="small"
                    style={{ paddingInline: 0, marginTop: 6 }}
                    onClick={() =>
                      setExpandedDialogueIds((prev) => ({
                        ...prev,
                        [msg.id]: !prev[msg.id],
                      }))
                    }
                  >
                    {isExpanded ? '收起详情' : '展开详情'}
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderEventFilters = () => (
    <Space wrap style={{ marginBottom: 12 }}>
      <Select
        style={{ width: 180 }}
        value={eventFilterAgent}
        onChange={setEventFilterAgent}
        options={eventFilterOptions.agents.map((value) => ({
          label: value === 'all' ? '全部Agent' : value,
          value,
        }))}
      />
      <Select
        style={{ width: 180 }}
        value={eventFilterPhase}
        onChange={setEventFilterPhase}
        options={eventFilterOptions.phases.map((value) => ({
          label: value === 'all' ? '全部阶段' : value,
          value,
        }))}
      />
      <Select
        style={{ width: 220 }}
        value={eventFilterType}
        onChange={setEventFilterType}
        options={eventFilterOptions.types.map((value) => ({
          label: value === 'all' ? '全部事件类型' : value,
          value,
        }))}
      />
      <Input
        allowClear
        style={{ width: 260 }}
        value={eventSearchText}
        placeholder="搜索摘要/细节/trace_id"
        onChange={(e) => setEventSearchText(e.target.value)}
      />
      <Button
        onClick={() => {
          setEventFilterAgent('all');
          setEventFilterPhase('all');
          setEventFilterType('all');
          setEventSearchText('');
        }}
      >
        重置筛选
      </Button>
    </Space>
  );

  const switchToStep = async (nextStep: number) => {
    if (nextStep > 0 && !incidentId) {
      message.warning('请先创建故障并初始化会话');
      return;
    }
    setActiveStep(nextStep);
    if (nextStep === 3 && incidentId && sessionId) {
      setLoading(true);
      try {
        await loadSessionArtifacts(sessionId, incidentId);
      } finally {
        setLoading(false);
      }
    }
  };

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
        <Steps
          type="navigation"
          current={activeStep}
          items={steps}
          onChange={(idx) => {
            void switchToStep(idx);
          }}
        />
        <Space style={{ marginTop: 16 }}>
          <Button type={activeStep === 0 ? 'primary' : 'default'} onClick={() => void switchToStep(0)}>
            输入故障信息
          </Button>
          <Button type={activeStep === 1 ? 'primary' : 'default'} onClick={() => void switchToStep(1)}>
            资产与辩论
          </Button>
          <Button type={activeStep === 2 ? 'primary' : 'default'} onClick={() => void switchToStep(2)}>
            辩论结果
          </Button>
          <Button type={activeStep === 3 ? 'primary' : 'default'} onClick={() => void switchToStep(3)}>
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
                <Select
                  value={debateMaxRounds}
                  style={{ width: 140 }}
                  onChange={(value) => setDebateMaxRounds(value)}
                  options={[
                    { label: '辩论1轮', value: 1 },
                    { label: '辩论2轮', value: 2 },
                    { label: '辩论3轮', value: 3 },
                    { label: '辩论4轮', value: 4 },
                    { label: '辩论5轮', value: 5 },
                    { label: '辩论6轮', value: 6 },
                  ]}
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
                <Descriptions.Item label="辩论轮数">{debateMaxRounds}</Descriptions.Item>
              </Descriptions>
              <Button type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={startRealtimeDebate}>
                启动实时辩论
              </Button>
              <Space style={{ marginLeft: 12 }}>
                <Button danger onClick={() => void sendWsControl('cancel')}>
                  取消分析
                </Button>
                <Button onClick={() => void sendWsControl('resume')}>恢复分析</Button>
              </Space>
            </Card>

            <Card title="事件明细（流式对话）">
              {renderEventFilters()}
              {renderDialogueStream()}
            </Card>

            <Card title="资产与辩论过程记录">
              {filteredStageEvents.length === 0 ? (
                <Text type="secondary">尚无过程记录</Text>
              ) : (
                <Timeline
                  items={filteredStageEvents.map((row) => ({
                    children: `${row.timeText} [${row.kind}] ${row.text}${String((asRecord(row.data).trace_id || '')) ? ` trace=${String(asRecord(row.data).trace_id || '')}` : ''}`,
                  }))}
                />
              )}
            </Card>
          </Space>
        )}

        {activeStep === 2 && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="事件明细（流式对话）">
              {renderEventFilters()}
              {renderDialogueStream()}
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

            <Card title="分析过程记录">
              {filteredStageEvents.length === 0 ? (
                <Text type="secondary">尚无过程记录</Text>
              ) : (
                <Timeline
                  items={filteredStageEvents.map((row) => ({
                    children: `${row.timeText} [${row.kind}] ${row.text}${String((asRecord(row.data).trace_id || '')) ? ` trace=${String(asRecord(row.data).trace_id || '')}` : ''}`,
                  }))}
                />
              )}
            </Card>
          </Space>
        )}

        {activeStep === 3 && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Card title="事件明细（流式对话）">
              {renderEventFilters()}
              {renderDialogueStream()}
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
              {shareUrl && (
                <Alert type="success" message={`分享地址：${shareUrl}`} showIcon style={{ marginBottom: 12 }} />
              )}
              {!report?.content ? (
                <Empty description="暂无报告" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Card size="small" title="报告摘要">
                    <Descriptions column={2} size="small">
                      <Descriptions.Item label="根因摘要">
                        {debateResult?.root_cause || '待生成'}
                      </Descriptions.Item>
                      <Descriptions.Item label="置信度">
                        {debateResult ? `${(debateResult.confidence * 100).toFixed(1)}%` : '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="影响服务">
                        {(debateResult?.impact_analysis?.affected_services || []).join(', ') || '-'}
                      </Descriptions.Item>
                      <Descriptions.Item label="风险等级">
                        {debateResult?.risk_assessment?.risk_level || '-'}
                      </Descriptions.Item>
                    </Descriptions>
                  </Card>
                  <Descriptions column={2} size="small">
                    <Descriptions.Item label="报告ID">{report.report_id}</Descriptions.Item>
                    <Descriptions.Item label="生成时间">
                      {formatBeijingDateTime(report.generated_at)}
                    </Descriptions.Item>
                    <Descriptions.Item label="格式">{report.format}</Descriptions.Item>
                    <Descriptions.Item label="关联会话">{report.debate_session_id || '-'}</Descriptions.Item>
                  </Descriptions>
                  {reportSections.map((section, index) => (
                    <Card key={`${section.title}_${index}`} size="small" title={section.title}>
                      {renderReportSectionBody(section.lines)}
                    </Card>
                  ))}
                </Space>
              )}
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

            <Card title="报告阶段过程记录">
              {filteredStageEvents.length === 0 ? (
                <Text type="secondary">尚无过程记录</Text>
              ) : (
                <Timeline
                  items={filteredStageEvents.map((row) => ({
                    children: `${row.timeText} [${row.kind}] ${row.text}${String((asRecord(row.data).trace_id || '')) ? ` trace=${String(asRecord(row.data).trace_id || '')}` : ''}`,
                  }))}
                />
              )}
            </Card>
          </Space>
        )}
      </div>
    </div>
  );
};

export default IncidentPage;
