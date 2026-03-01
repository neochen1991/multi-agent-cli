import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Avatar,
  Button,
  Card,
  Empty,
  Input,
  Select,
  Space,
  Steps,
  Tag,
  Typography,
  message,
} from 'antd';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  buildDebateWsUrl,
  debateApi,
  incidentApi,
  reportApi,
  type DebateDetail,
  type DebateResult,
  type Report,
} from '@/services/api';
import { formatBeijingDateTime, formatBeijingTime } from '@/utils/dateTime';
import AssetMappingPanel from '@/components/incident/AssetMappingPanel';
import DebateProcessPanel from '@/components/incident/DebateProcessPanel';
import DebateResultPanel from '@/components/incident/DebateResultPanel';

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
  eventTsMs?: number;
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
  const [reportResult, setReportResult] = useState<Report | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
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
  const assetMappingReadyRef = useRef(false);
  const streamTimersRef = useRef<Record<string, number>>({});
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const seenEventFingerprintsRef = useRef<Set<string>>(new Set());

  const steps = useMemo(
    () => [
      { title: '输入故障信息', description: '创建 Incident 与 Session' },
      { title: '资产映射', description: '责任田映射结果' },
      { title: '辩论过程', description: '所有 Agent 实时辩论' },
      { title: '辩论结果', description: '主Agent最终结论' },
    ],
    [],
  );

  const appendEvent = (kind: string, text: string, data?: unknown) => {
    const dataRecord = asRecord(data);
    const eventId = String(dataRecord.event_id || '').trim();
    const fingerprint = [
      kind,
      String(dataRecord.phase || ''),
      String(dataRecord.agent_name || dataRecord.agent || ''),
      String(dataRecord.round_number || ''),
      String(dataRecord.loop_round || ''),
      String(dataRecord.timestamp || ''),
      String(text || ''),
    ].join('|');
    if (eventId) {
      if (seenEventIdsRef.current.has(eventId)) {
        return;
      }
      seenEventIdsRef.current.add(eventId);
    } else if (fingerprint && seenEventFingerprintsRef.current.has(fingerprint)) {
      return;
    } else if (fingerprint) {
      seenEventFingerprintsRef.current.add(fingerprint);
    }
    const eventTsRaw = String(dataRecord.timestamp || '').trim();
    const displayTime =
      eventTsRaw
        ? formatBeijingDateTime(eventTsRaw)
        : formatBeijingDateTime(new Date());
    const record: EventRecord = {
      id: eventId || `${Date.now()}_${Math.random().toString(16).slice(2)}`,
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

  const formatToolDataPreview = (
    toolName: string,
    preview: Record<string, unknown>,
    truncate = true,
  ): string => {
    if (!preview || Object.keys(preview).length === 0) return '无数据摘要';
    if (toolName === 'local_log_reader') {
      const filePath = String(preview.file_path || '-');
      const lineCount = String(preview.line_count || '-');
      const keywords = Array.isArray(preview.keywords) ? preview.keywords.map(String).join(', ') : '-';
      const excerpt = String(preview.excerpt || '').trim();
      const excerptText = truncate
        ? `${excerpt.slice(0, 180)}${excerpt.length > 180 ? '...' : ''}`
        : excerpt;
      return [
        `日志文件：${filePath}`,
        `采样行数：${lineCount}`,
        `关键词：${keywords || '-'}`,
        excerpt ? `日志片段：${excerptText}` : '',
      ]
        .filter(Boolean)
        .join('\n');
    }
    if (toolName === 'domain_excel_lookup') {
      const excelPath = String(preview.excel_path || '-');
      const rowCount = String(preview.row_count || '-');
      const matches = Array.isArray(preview.matches) ? preview.matches : [];
      const owners = matches
        .map((item) => asRecord(item))
        .map((item) => `${String(item.domain || '-')}/${String(item.aggregate || '-')} -> ${String(item.owner_team || '-')}/${String(item.owner || '-')}`)
        .slice(0, truncate ? 3 : 10);
      return [
        `责任田文件：${excelPath}`,
        `扫描行数：${rowCount}`,
        `命中条数：${matches.length}`,
        owners.length ? `命中摘要：${owners.join('；')}` : '',
      ]
        .filter(Boolean)
        .join('\n');
    }
    if (toolName === 'git_repo_search') {
      const repoPath = String(preview.repo_path || '-');
      const keywords = Array.isArray(preview.keywords) ? preview.keywords.map(String).join(', ') : '-';
      const hits = Array.isArray(preview.hits) ? preview.hits : [];
      const topHits = hits
        .map((item) => asRecord(item))
        .map((item) => `${String(item.file || '-')}:${String(item.line || '-')} [${String(item.keyword || '-')}]`)
        .slice(0, truncate ? 3 : 10);
      return [
        `代码仓目录：${repoPath}`,
        `检索关键词：${keywords || '-'}`,
        `命中片段：${hits.length} 条`,
        topHits.length ? `命中示例：${topHits.join('；')}` : '',
      ]
        .filter(Boolean)
        .join('\n');
    }
    if (toolName === 'git_change_window') {
      const repoPath = String(preview.repo_path || '-');
      const changes = Array.isArray(preview.changes) ? preview.changes : [];
      const top = changes
        .map((item) => asRecord(item))
        .map(
          (item) =>
            `${String(item.commit || '-')}: ${String(item.subject || '-')}${
              item.time ? ` (${String(item.time)})` : ''
            }`,
        )
        .slice(0, truncate ? 3 : 10);
      return [
        `代码仓目录：${repoPath}`,
        `变更条数：${changes.length}`,
        top.length ? `变更示例：${top.join('；')}` : '',
      ]
        .filter(Boolean)
        .join('\n');
    }
    if (toolName === 'metrics_snapshot_analyzer') {
      const signals = Array.isArray(preview.signals) ? preview.signals : [];
      const top = signals
        .map((item) => asRecord(item))
        .map((item) => `${String(item.label || item.metric || '-')}: ${String(item.value || '-')}`)
        .slice(0, truncate ? 6 : 16);
      return [`指标信号数：${signals.length}`, top.length ? `异常信号：${top.join('；')}` : ''].filter(Boolean).join('\n');
    }
    if (toolName === 'runbook_case_library') {
      const query = String(preview.query || '-');
      const items = Array.isArray(preview.items) ? preview.items : [];
      const top = items
        .map((item) => asRecord(item))
        .map((item) => `${String(item.id || '-')}: ${String(item.title || item.description || '-')}`)
        .slice(0, truncate ? 4 : 12);
      return [`检索词：${query}`, `命中案例：${items.length}`, top.length ? `案例摘要：${top.join('；')}` : '']
        .filter(Boolean)
        .join('\n');
    }
    const lines = Object.entries(preview)
      .slice(0, 6)
      .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : toDisplayText(value)}`);
    return lines.join('\n');
  };

  const formatToolAuditLog = (auditItems: unknown[]): string => {
    if (!Array.isArray(auditItems) || auditItems.length === 0) return '无审计记录';
    return auditItems
      .slice(0, 12)
      .map((item, index) => {
        const row = asRecord(item);
        const ts = firstTextValue(row, ['timestamp']) || '-';
        const action = firstTextValue(row, ['action']) || '-';
        const status = firstTextValue(row, ['status']) || '-';
        const detail = toDisplayText(row.detail);
        return `${index + 1}. [${ts}] action=${action} status=${status}\n${detail}`;
      })
      .join('\n');
  };

  const extractSessionError = (detail: DebateDetail | null): string => {
    const context = (detail?.context || {}) as Record<string, unknown>;
    const code = String(context.last_error_code || '').trim();
    const direct = String(context.last_error || '').trim();
    const retryHint = String(context.last_error_retry_hint || '').trim();
    if (direct) return direct;
    const eventLog = context.event_log;
    if (!Array.isArray(eventLog)) return '';
    for (let i = eventLog.length - 1; i >= 0; i -= 1) {
      const row = asRecord(eventLog[i]);
      const event = asRecord(row.event);
      if (String(event.type || '') === 'session_failed') {
        const err = String(event.error_message || event.error || '').trim();
        if (err) {
          const suffix = retryHint ? `；重试建议：${retryHint}` : '';
          return `${code ? `[${code}] ` : ''}${err}${suffix}`;
        }
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

  const tryParseJson = (text: string): Record<string, unknown> | null => {
    const source = String(text || '').trim();
    if (!source) return null;
    const candidates: string[] = [];
    const fencedMatches = Array.from(source.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi));
    fencedMatches.forEach((match) => {
      const body = String(match[1] || '').trim();
      if (body) candidates.push(body);
    });
    if ((source.startsWith('{') && source.endsWith('}')) || (source.startsWith('[') && source.endsWith(']'))) {
      candidates.push(source);
    }
    const firstBrace = source.indexOf('{');
    const lastBrace = source.lastIndexOf('}');
    if (firstBrace >= 0 && lastBrace > firstBrace) {
      candidates.push(source.slice(firstBrace, lastBrace + 1));
    }
    for (const candidate of candidates) {
      try {
        const parsed = JSON.parse(candidate);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return parsed as Record<string, unknown>;
        }
      } catch {
        continue;
      }
    }
    return null;
  };

  const extractReadableTextFromObject = (value: Record<string, unknown>): string => {
    const chat = extractChatMessageText(firstTextValue(value, ['chat_message', 'message', 'summary']));
    const conclusion = extractChatMessageText(firstTextValue(value, ['conclusion', 'root_cause', 'judgment']));
    const analysis = extractChatMessageText(firstTextValue(value, ['analysis', 'reason', 'detail']));
    const confidenceRaw = value.confidence;
    const confidence =
      typeof confidenceRaw === 'number' ? `置信度 ${(Number(confidenceRaw) * 100).toFixed(1)}%` : '';
    const lines = [chat, conclusion ? `结论：${conclusion}` : '', analysis ? `依据：${analysis}` : '', confidence]
      .map((line) => String(line || '').trim())
      .filter(Boolean);
    if (lines.length > 0) return lines.join('\n');
    return '结构化分析结果已生成';
  };

  const extractLooseJsonStringField = (source: string, fieldName: string): string => {
    const marker = `"${fieldName}"`;
    const markerIndex = source.indexOf(marker);
    if (markerIndex < 0) return '';
    const colonIndex = source.indexOf(':', markerIndex + marker.length);
    if (colonIndex < 0) return '';
    let idx = colonIndex + 1;
    while (idx < source.length && /\s/.test(source[idx])) idx += 1;
    if (idx >= source.length || source[idx] !== '"') return '';
    idx += 1;
    let output = '';
    let escaping = false;
    while (idx < source.length) {
      const ch = source[idx];
      if (escaping) {
        if (ch === 'n') output += '\n';
        else if (ch === 't') output += '\t';
        else output += ch;
        escaping = false;
        idx += 1;
        continue;
      }
      if (ch === '\\') {
        escaping = true;
        idx += 1;
        continue;
      }
      if (ch === '"') {
        break;
      }
      output += ch;
      idx += 1;
    }
    return output.trim();
  };

  const stripJsonTail = (source: string): string => {
    const firstBrace = source.indexOf('{');
    if (firstBrace < 0) return source.trim();
    const prefix = source.slice(0, firstBrace).trim();
    if (prefix) return prefix;
    return source
      .replace(/\{[\s\S]*$/, '')
      .trim();
  };

  const extractChatMessageText = (raw: unknown): string => {
    if (raw === null || raw === undefined) return '';
    if (typeof raw === 'object') return extractReadableTextFromObject(asRecord(raw));
    const source = String(raw || '')
      .replace(/```(?:json)?\s*/gi, '')
      .replace(/```/g, '')
      .trim();
    if (!source) return '';
    const parsed = tryParseJson(source);
    if (parsed) return extractReadableTextFromObject(parsed);
    const chatFromLooseJson =
      extractLooseJsonStringField(source, 'chat_message') ||
      extractLooseJsonStringField(source, 'message') ||
      extractLooseJsonStringField(source, 'summary');
    if (chatFromLooseJson) return chatFromLooseJson;
    if (source.includes('{') && /"(chat_message|message|summary|conclusion|analysis)"/.test(source)) {
      const stripped = stripJsonTail(source);
      if (stripped) return stripped;
      return '结构化分析结果已生成';
    }
    return source.trim();
  };

  const normalizeForCompare = (value: string): string =>
    String(value || '')
      .toLowerCase()
      .replace(/[^\u4e00-\u9fa5a-z0-9]/gi, '');

  const isEffectiveConclusionText = (value: string): boolean => {
    const text = String(value || '').trim();
    if (!text) return false;
    const lowered = text.toLowerCase();
    const blocked = ['需要进一步分析', 'insufficient', 'unknown', '无法确定', '待补充信息'];
    return !blocked.some((token) => lowered.includes(token));
  };

  const isNearDuplicateText = (leftText: string, rightText: string): boolean => {
    const left = normalizeForCompare(leftText);
    const right = normalizeForCompare(rightText);
    if (!left || !right) return false;
    if (left === right) return true;
    const minLen = Math.min(left.length, right.length);
    const maxLen = Math.max(left.length, right.length);
    if (minLen < 16) return false;
    if (left.startsWith(right) || right.startsWith(left)) {
      return minLen / maxLen >= 0.85;
    }
    return false;
  };

  const parseEventTimestampMs = (data: Record<string, unknown>): number | undefined => {
    const raw = String(data.timestamp || '').trim();
    if (!raw) return undefined;
    const hasTimezone = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw);
    const normalized =
      !hasTimezone && /^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(raw)
        ? `${raw.replace(' ', 'T')}Z`
        : raw;
    const ms = Date.parse(normalized);
    return Number.isNaN(ms) ? undefined : ms;
  };

  const isConsecutiveDuplicateDialogue = (prev: DialogueMessage, current: DialogueMessage): boolean => {
    if (prev.agentName !== current.agentName) return false;
    if (prev.side !== current.side) return false;
    const sameSummary = normalizeForCompare(prev.summary) === normalizeForCompare(current.summary);
    const sameDetail = normalizeForCompare(prev.detail) === normalizeForCompare(current.detail);
    if (!sameSummary || !sameDetail) return false;
    const prevTs = prev.eventTsMs;
    const currentTs = current.eventTsMs;
    if (prevTs && currentTs) {
      return Math.abs(currentTs - prevTs) <= 3000;
    }
    return true;
  };

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

    // 对话流只展示“人类可读对话”和关键状态，底层 LLM 事件放在事件明细中查看。
    if (
      kind === 'llm_stream_delta' ||
      kind === 'llm_http_request' ||
      kind === 'llm_http_response' ||
      kind === 'llm_http_error' ||
      kind === 'llm_call_started' ||
      kind === 'llm_call_completed'
    ) {
      return null;
    }

    const isRequestKind =
      kind === 'llm_prompt_started' ||
      kind === 'llm_call_started' ||
      kind === 'autogen_call_started' ||
      kind === 'llm_stream_delta';
    const isResponseKind =
      kind === 'llm_prompt_completed' ||
      kind === 'llm_cli_command_completed' ||
      kind === 'llm_call_completed' ||
      kind === 'autogen_call_completed' ||
      kind === 'agent_round';
    const isErrorKind =
      kind === 'llm_call_failed' ||
      kind === 'llm_call_timeout' ||
      kind === 'autogen_call_failed' ||
      kind === 'llm_prompt_failed' ||
      kind === 'llm_cli_command_failed' ||
      kind === 'session_failed';

    const side: 'agent' | 'system' = agentRaw ? 'agent' : 'system';
    let status: 'streaming' | 'done' | 'error' = 'done';
    let summary = normalizeInlineText(messageText || kind);
    let detail = '';

    if (kind === 'agent_chat_message') {
      status = 'done';
      const replyTo = firstTextValue(data, ['reply_to']);
      summary = replyTo && replyTo !== 'all' ? `${agentName} 回复 ${replyTo}` : `${agentName} 发言`;
      const speechText = extractChatMessageText(firstTextValue(data, ['message']) || messageText || '（空发言）');
      const conclusionText = extractChatMessageText(firstTextValue(data, ['conclusion']));
      if (conclusionText) {
        const duplicated = speechText && isNearDuplicateText(conclusionText, speechText);
        detail = normalizeMarkdownText(
          [`结论：${conclusionText}`, speechText && !duplicated ? `发言：${speechText}` : '']
            .filter(Boolean)
            .join('\n'),
        );
      } else {
        detail = normalizeMarkdownText(speechText);
      }
    } else if (kind === 'agent_tool_context_prepared') {
      const toolName = firstTextValue(data, ['tool_name']) || 'unknown_tool';
      const enabled = Boolean(data.enabled);
      const used = Boolean(data.used);
      const toolStatus = firstTextValue(data, ['status']) || 'unknown';
      const toolSummary = firstTextValue(data, ['summary']) || '无摘要';
      const dataPreview = asRecord(data.data_preview);
      const dataDetail = asRecord(data.data_detail);
      const commandGate = asRecord(data.command_gate);
      const auditLog = Array.isArray(data.audit_log) ? data.audit_log : [];
      const toolLabelMap: Record<string, string> = {
        local_log_reader: '日志文件读取工具',
        domain_excel_lookup: '责任田文档查询工具',
        git_repo_search: '代码仓检索工具',
        git_change_window: '变更窗口分析工具',
        metrics_snapshot_analyzer: '监控指标分析工具',
        runbook_case_library: '案例库检索工具',
      };
      const statusLabelMap: Record<string, string> = {
        ok: '成功',
        disabled: '已关闭',
        unavailable: '不可用',
        skipped: '跳过',
        skipped_by_command: '按命令跳过',
        error: '失败',
      };
      const toolLabel = toolLabelMap[toolName] || toolName;
      const statusLabel = statusLabelMap[toolStatus] || toolStatus;
      const dataSummaryText = formatToolDataPreview(toolName, dataPreview);
      const dataDetailText = formatToolDataPreview(
        toolName,
        Object.keys(dataDetail).length > 0 ? dataDetail : dataPreview,
        false,
      );
      const commandGateReason = firstTextValue(commandGate, ['reason']) || '-';
      const commandGateSource = firstTextValue(commandGate, ['decision_source']) || '-';
      const commandGateAllow = typeof commandGate.allow_tool === 'boolean' ? (commandGate.allow_tool ? '是' : '否') : '-';
      const auditText = formatToolAuditLog(auditLog);
      status = toolStatus === 'error' ? 'error' : 'done';
      summary = `${agentName} 工具调用：${toolLabel}（${statusLabel}）`;
      detail = normalizeMarkdownText(
        [
          `我使用了工具：${toolLabel}`,
          `开关状态：${enabled ? '开启' : '关闭'}`,
          `是否实际调用：${used ? '是' : '否'}`,
          `执行结果：${statusLabel}`,
          `命令门禁：允许调用=${commandGateAllow}，原因=${commandGateReason}，来源=${commandGateSource}`,
          `工具反馈：${toolSummary}`,
          `获取数据摘要：\n${dataSummaryText}`,
          `工具返回详情：\n${dataDetailText}`,
          `调用审计记录：\n${auditText}`,
        ]
          .filter(Boolean)
          .join('\n'),
      );
    } else if (kind === 'agent_tool_io') {
      const action = firstTextValue(data, ['io_action']) || '-';
      const ioStatus = firstTextValue(data, ['io_status']) || '-';
      const ioDetail = toDisplayText(data.io_detail);
      status = ioStatus === 'error' ? 'error' : 'done';
      summary = `${agentName} 工具I/O：${action}（${ioStatus}）`;
      detail = normalizeMarkdownText(`I/O 详情：\n${ioDetail}`);
    } else if (kind === 'agent_tool_context_failed') {
      status = 'error';
      summary = `${agentName} 工具调用失败`;
      detail = normalizeMarkdownText(
        `我尝试调用工具时发生异常。\n错误信息：${firstTextValue(data, ['error']) || messageText || '未知错误'}`,
      );
    } else if (
      (kind === 'autogen_call_completed' || kind === 'llm_call_completed') &&
      ['analysis', 'critique', 'rebuttal', 'judgment', 'verification'].includes(phase)
    ) {
      // 辩论阶段优先展示 agent_round，避免 completed 与 round 双重重复
      return null;
    } else if (kind === 'agent_round' && typeof outputJson === 'object' && outputJson !== null && 'chat_message' in (outputJson as Record<string, unknown>)) {
      // 聊天对话由 agent_chat_message 承载，agent_round 仅作为结构化记录保留在事件明细中
      return null;
    } else if (isRequestKind) {
      status = 'streaming';
      summary = `${agentName} 开始分析`;
      detail = normalizeMarkdownText(prompt || messageText || '正在调用模型，请稍候...');
    } else if (isResponseKind) {
      status = 'done';
      summary = `${agentName} 输出结论`;
      if (typeof outputJson !== 'undefined') {
        detail = normalizeMarkdownText(extractReadableTextFromObject(asRecord(outputJson)));
      } else {
        detail = normalizeMarkdownText(extractChatMessageText(output || messageText || '已完成该轮分析'));
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
    } else if (kind === 'agent_command_feedback') {
      status = 'done';
      summary = `${agentName} 向主Agent反馈`;
      const feedback = extractChatMessageText(firstTextValue(data, ['feedback']));
      const command = extractChatMessageText(firstTextValue(data, ['command']));
      const confidenceRaw = data.confidence;
      const confidenceLine =
        typeof confidenceRaw === 'number' ? `置信度：${(Number(confidenceRaw) * 100).toFixed(1)}%` : '';
      detail = normalizeMarkdownText(
        [feedback ? `反馈：${feedback}` : '', command ? `命令：${command}` : '', confidenceLine]
          .filter(Boolean)
          .join('\n'),
      );
    } else if (kind === 'agent_command_issued') {
      status = 'done';
      summary = normalizeInlineText(messageText || '主Agent指令');
      detail = normalizeMarkdownText(
        firstTextValue(data, ['message', 'command', 'feedback']) || messageText || '命令执行事件',
      );
    } else {
      return null;
    }

    return {
      id: row.id,
      timeText: row.timeText,
      eventTsMs: parseEventTimestampMs(data),
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
      case 'agent_chat_message':
        return `Agent发言 [${phase || '-'}] ${agent || ''}`.trim();
      case 'agent_tool_context_prepared':
        return `Agent工具调用 [${phase || '-'}] ${agent || ''} ${String(data?.tool_name || '')} ${String(data?.status || '')}`.trim();
      case 'agent_tool_context_failed':
        return `Agent工具调用失败 [${phase || '-'}] ${agent || ''} ${error}`.trim();
      case 'agent_tool_io':
        return `Agent工具I/O [${phase || '-'}] ${agent || ''} ${String(data?.io_action || '')} ${String(data?.io_status || '')}`.trim();
      case 'agent_command_issued':
        return `主Agent下达指令 [${phase || '-'}] ${agent || ''} -> ${String(data?.target_agent || '-')}`.trim();
      case 'agent_command_feedback':
        return `Agent反馈主Agent [${phase || '-'}] ${agent || ''}`.trim();
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
        return `会话失败 ${String(data?.error_code || '')} ${error || String(data?.error_message || '')} ${String(data?.retry_hint || '')}`.trim();
      case 'ws_ack':
        return `控制指令确认 ${String(data?.message || '')}`.trim();
      case 'ws_control':
        return `控制指令 ${String(data?.action || '-')}`.trim();
      case 'retry_requested':
        return `重试请求 ${String(data?.retry_failed_only ? '仅失败Agent' : '全量')}`.trim();
      case 'error':
        return `会话错误 ${String(data?.error_code || '')} ${String(data?.message || '')}`.trim();
      default:
        return `事件: ${kind}`;
    }
  };

  const isAssetMappingEvent = (row: EventRecord): boolean => row.kind === 'asset_interface_mapping_completed';

  const isDebateProcessEvent = (row: EventRecord): boolean => {
    const data = asRecord(row.data);
    const phase = String(data.phase || '').toLowerCase();
    const kind = row.kind.toLowerCase();
    if (isAssetMappingEvent(row)) return false;
    if (kind === 'session_created_local' || kind === 'ws_open' || kind === 'ws_close' || kind === 'snapshot') {
      return false;
    }
    return (
      kind === 'agent_chat_message' ||
      kind === 'agent_round' ||
      kind === 'agent_command_issued' ||
      kind === 'agent_command_feedback' ||
      kind.startsWith('llm_call_') ||
      kind.startsWith('llm_http_') ||
      kind === 'llm_stream_delta' ||
      kind === 'llm_invoke_path' ||
      kind === 'agent_factory_fallback' ||
      phase === 'analysis' ||
      phase.includes('coordination') ||
      phase.includes('critique') ||
      phase.includes('rebuttal') ||
      phase.includes('judgment') ||
      phase.includes('verification')
    );
  };

  const advanceStep = (nextStep: number) => {
    setActiveStep((prev) => (nextStep > prev ? nextStep : prev));
  };

  const resetDialogueFilters = () => {
    setEventFilterAgent('all');
    setEventFilterPhase('all');
    setEventFilterType('all');
    setEventSearchText('');
  };

  const loadSessionArtifacts = async (sid: string) => {
    const detail = await debateApi.get(sid);
    const status = String(detail.status || '').toLowerCase();
    const shouldLoadFinalResult = status === 'completed';
    const result = shouldLoadFinalResult
      ? await debateApi.getResult(sid).catch(() => null)
      : null;
    setSessionDetail(detail);
    setDebateResult(result);
    const reportIncidentId = detail.incident_id || incidentId;
    if (shouldLoadFinalResult && reportIncidentId) {
      const report = await reportApi.get(reportIncidentId).catch(() => null);
      setReportResult(report);
    } else {
      setReportResult(null);
    }
    const config = ((detail.context as Record<string, unknown> | undefined) || {})
      .debate_config as Record<string, unknown> | undefined;
    const maxRoundsRaw = config?.max_rounds;
    if (typeof maxRoundsRaw === 'number' && Number.isFinite(maxRoundsRaw)) {
      setDebateMaxRounds(Math.max(1, Math.min(8, Math.trunc(maxRoundsRaw))));
    }

    const persisted = (detail.context as Record<string, unknown> | undefined)?.event_log;
    if (Array.isArray(persisted)) {
      if (
        persisted.some((item) => {
          const row = (item || {}) as Record<string, unknown>;
          const event = (row.event || {}) as Record<string, unknown>;
          return String(event.type || '') === 'asset_interface_mapping_completed';
        })
      ) {
        assetMappingReadyRef.current = true;
      }
      setEventRecords((prev) => {
        if (prev.length > 0) return prev;
        return persisted
          .slice(0, 300)
          .map((item, idx) => {
            const row = (item || {}) as Record<string, unknown>;
            const event = (row.event || {}) as Record<string, unknown>;
            const ts = typeof row.timestamp === 'string' ? row.timestamp : '';
            const kind = typeof event.type === 'string' ? event.type : 'event';
            const eventId = typeof event.event_id === 'string' ? event.event_id : '';
            return {
              id: eventId || `persisted_${idx}_${ts || kind}`,
              timeText: ts ? formatBeijingTime(ts) : '--:--:--',
              kind,
              text: formatEventText(kind, event),
              data: event,
            } as EventRecord;
          })
          .reverse();
      });
      persisted.forEach((item) => {
        const row = (item || {}) as Record<string, unknown>;
        const event = (row.event || {}) as Record<string, unknown>;
        const eventId = typeof event.event_id === 'string' ? event.event_id : '';
        if (eventId) seenEventIdsRef.current.add(eventId);
        const fingerprint = [
          String(event.type || ''),
          String(event.phase || ''),
          String(event.agent_name || event.agent || ''),
          String(event.round_number || ''),
          String(event.loop_round || ''),
          String(event.timestamp || ''),
          formatEventText(String(event.type || 'event'), event),
        ].join('|');
        if (fingerprint) seenEventFingerprintsRef.current.add(fingerprint);
      });
    }
    return detail;
  };

  const createIncidentAndSession = async (): Promise<{ incidentId: string; sessionId: string } | null> => {
    if (!incidentForm.title.trim()) {
      message.error('请填写故障标题');
      return null;
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
      seenEventFingerprintsRef.current.clear();
      setEventRecords([]);
      setStreamedMessageText({});
      setExpandedDialogueIds({});
      resetDialogueFilters();
      assetMappingReadyRef.current = false;
      setReportResult(null);
      setIncidentId(incident.id);
      setSessionId(session.id);
      advanceStep(1);
      appendEvent('session_created_local', `会话已创建 ${session.id}`, { session_id: session.id });
      message.success('故障会话创建成功');
      return { incidentId: incident.id, sessionId: session.id };
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '创建失败');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const initSessionForExistingIncident = async (): Promise<string | null> => {
    if (!incidentId) return null;
    setLoading(true);
    try {
      const session = await debateApi.createSession(incidentId, { maxRounds: debateMaxRounds });
      seenEventIdsRef.current.clear();
      seenEventFingerprintsRef.current.clear();
      setEventRecords([]);
      setStreamedMessageText({});
      setExpandedDialogueIds({});
      resetDialogueFilters();
      assetMappingReadyRef.current = false;
      setReportResult(null);
      setSessionId(session.id);
      appendEvent('session_created_local', `会话已创建 ${session.id}`, { session_id: session.id });
      advanceStep(1);
      message.success('已初始化辩论会话');
      return session.id;
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '初始化会话失败');
      return null;
    } finally {
      setLoading(false);
    }
  };

  const pollResultUntilReady = async (sid: string) => {
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      const maxAttempts = 60;
      for (let i = 0; i < maxAttempts; i += 1) {
        const detail = await debateApi.get(sid).catch(() => null);
        if (detail) {
          setSessionDetail(detail);
        }
        const status = String(detail?.status || '').toLowerCase();
        if (status === 'completed') {
          const result = await debateApi.getResult(sid).catch(() => null);
          if (result) {
            appendEvent('result_polled', '后台任务已完成，正在刷新结果');
            setDebateResult(result);
            await loadSessionArtifacts(sid);
            advanceStep(3);
            setRunning(false);
            return;
          }
        }
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
        if (status === 'cancelled') {
          appendEvent('session_cancelled', '会话已取消', {
            type: 'session_cancelled',
            phase: 'cancelled',
            status: 'cancelled',
          });
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

  const startRealtimeDebate = async (
    options?: { sessionId?: string; incidentId?: string },
  ) => {
    const targetSessionId = options?.sessionId || sessionId;
    const targetIncidentId = options?.incidentId || incidentId;
    if (!targetSessionId || !targetIncidentId) return;
    resetDialogueFilters();
    setRunning(true);
    appendEvent('start', '开始实时辩论');

    try {
      const ws = new WebSocket(buildDebateWsUrl(targetSessionId));
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
              await loadSessionArtifacts(targetSessionId).catch(() => undefined);
              return;
            }
            const eventPhase = String(payload.data?.phase || '').toLowerCase();
            const isAssetEvent =
              type === 'asset_interface_mapping_completed' ||
              type === 'asset_collection_completed' ||
              type === 'runtime_assets_collected' ||
              eventPhase.includes('asset');
            if (type === 'asset_interface_mapping_completed') {
              assetMappingReadyRef.current = true;
            }
            if (isAssetEvent) {
              advanceStep(1);
            }
            const isDebatePhase =
              eventPhase.includes('analysis') ||
              eventPhase.includes('coordination') ||
              eventPhase.includes('critique') ||
              eventPhase.includes('rebuttal') ||
              eventPhase.includes('judgment');
            const isDebateProgressEvent =
              type === 'agent_round' ||
              type === 'agent_chat_message' ||
              type === 'round_started' ||
              ((type === 'autogen_call_started' || type === 'llm_call_started') && isDebatePhase);
            if (isDebateProgressEvent && assetMappingReadyRef.current) {
              advanceStep(2);
            }
            if (
              (type === 'autogen_call_started' || type === 'llm_call_started') &&
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
            await loadSessionArtifacts(targetSessionId);
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
            await loadSessionArtifacts(targetSessionId).catch(() => undefined);
            advanceStep(2);
          }
        } catch {
          appendEvent('unknown_payload', '收到非结构化消息');
        }
      };

      ws.onerror = async () => {
        appendEvent('ws_error', 'WebSocket 连接异常，改为后台轮询结果');
        await pollResultUntilReady(targetSessionId);
      };

      ws.onclose = () => {
        appendEvent('ws_close', 'WebSocket 已关闭');
        if (runningRef.current) {
          void pollResultUntilReady(targetSessionId);
        }
      };
    } catch (e: any) {
      message.error(e?.message || '启动失败');
      setRunning(false);
    }
  };

  const startAnalysisFromInput = async () => {
    let targetIncidentId = incidentId;
    let targetSessionId = sessionId;
    if (!targetIncidentId) {
      const created = await createIncidentAndSession();
      if (!created) return;
      targetIncidentId = created.incidentId;
      targetSessionId = created.sessionId;
    } else if (!targetSessionId) {
      const sid = await initSessionForExistingIncident();
      if (!sid) return;
      targetSessionId = sid;
    }
    if (!targetIncidentId || !targetSessionId) return;
    advanceStep(1);
    await loadSessionArtifacts(targetSessionId).catch(() => undefined);
    await startRealtimeDebate({ sessionId: targetSessionId, incidentId: targetIncidentId });
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

  const retryFailedAgents = async () => {
    if (!sessionId) return;
    setRunning(true);
    appendEvent('retry_requested', '已请求仅重试失败Agent', {
      type: 'retry_requested',
      session_id: sessionId,
      retry_failed_only: true,
    });
    try {
      const result = await debateApi.execute(sessionId, { retryFailedOnly: true });
      setDebateResult(result);
      await loadSessionArtifacts(sessionId);
      advanceStep(3);
      message.success('失败Agent重试完成');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '失败Agent重试失败');
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    const iid = routeIncidentId || searchParams.get('incident_id');
    const preferredView = (searchParams.get('view') || '').toLowerCase();
    if (!iid) {
      setReportResult(null);
      assetMappingReadyRef.current = false;
      return;
    }
    seenEventIdsRef.current.clear();
    seenEventFingerprintsRef.current.clear();
    setEventRecords([]);
    setStreamedMessageText({});
    setExpandedDialogueIds({});
    resetDialogueFilters();
    assetMappingReadyRef.current = false;
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
          const detail = await loadSessionArtifacts(incident.debate_session_id);
          const status = detail?.status || '';
          if (preferredView === 'result' || preferredView === 'report') {
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

  const mappingEvents = useMemo(
    () => eventRecords.filter((row) => isAssetMappingEvent(row)),
    [eventRecords],
  );

  const debateEvents = useMemo(
    () => eventRecords.filter((row) => isDebateProcessEvent(row)),
    [eventRecords],
  );

  const dialogueMessages = useMemo(
    () => {
      const rawMessages = debateEvents
        .slice()
        .reverse()
        .map((row) => buildDialogueMessage(row))
        .filter((item): item is DialogueMessage => Boolean(item));
      const deduped: DialogueMessage[] = [];
      rawMessages.forEach((msg) => {
        const prev = deduped[deduped.length - 1];
        if (prev && isConsecutiveDuplicateDialogue(prev, msg)) {
          return;
        }
        deduped.push(msg);
      });
      return deduped;
    },
    [debateEvents],
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

  const filteredDebateEvents = useMemo(() => {
    const includeIds = new Set(filteredDialogueMessages.map((item) => item.id));
    return debateEvents.filter((row) => includeIds.has(row.id));
  }, [debateEvents, filteredDialogueMessages]);

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

  const buildCompactDetail = (value: string): { text: string; truncated: boolean } => {
    const normalized = normalizeMarkdownText(value || '');
    const lines = normalized
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    if (lines.length === 0) return { text: '', truncated: false };
    const compact = lines.slice(0, 3).join('\n');
    if (compact.length > 220) {
      return { text: `${compact.slice(0, 220).trim()}...`, truncated: true };
    }
    if (lines.length > 3) return { text: `${compact}\n...`, truncated: true };
    return { text: compact, truncated: false };
  };

  const renderDialogueStream = () => {
    if (filteredDialogueMessages.length === 0) {
      return <Empty description="暂无匹配的事件明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    }
    return (
      <div className="dialogue-stream discord-thread">
        {filteredDialogueMessages.map((msg) => {
          const renderedText = streamedMessageText[msg.id] ?? '';
          const fullText = msg.status === 'streaming' ? renderedText : msg.detail;
          const compactView = buildCompactDetail(fullText || msg.detail);
          const compactText = compactView.text;
          const showCursor =
            msg.status === 'streaming' && renderedText.length < (msg.detail || '').length;
          const isExpanded = Boolean(expandedDialogueIds[msg.id]);
          const canExpand = compactView.truncated;
          return (
            <div
              key={msg.id}
              className={`dialogue-row ${msg.side === 'agent' ? 'dialogue-row-agent' : 'dialogue-row-system'}`}
            >
              <Avatar size="small" className="dialogue-avatar">
                {msg.agentName.slice(0, 1).toUpperCase()}
              </Avatar>
              <div className={`dialogue-message dialogue-status-${msg.status}`}>
                <div className="dialogue-meta">
                  <Text className="dialogue-username">{msg.agentName}</Text>
                  <Text className="dialogue-time">{msg.timeText}</Text>
                  {msg.phase && <Tag className="dialogue-tag">{msg.phase}</Tag>}
                  <Tag className="dialogue-tag">{msg.eventType}</Tag>
                  {msg.latencyMs ? <Tag className="dialogue-tag">{`${msg.latencyMs}ms`}</Tag> : null}
                </div>
                <Paragraph className="dialogue-summary">{msg.summary}</Paragraph>
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
        await loadSessionArtifacts(sessionId);
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
        <Text type="secondary">模型：{String(round.model?.name || 'glm-5')}</Text>
        <Text type="secondary">输入片段：</Text>
        <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{round.input_message || '无'}</pre>
        <Text type="secondary">输出内容：</Text>
        <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
          {extractReadableTextFromObject(asRecord(round.output_content || {}))}
        </pre>
      </Space>
    ),
  }));

  const timelineItems = useMemo(
    () =>
      filteredDebateEvents.map((row) => ({
        children: `${row.timeText} [${row.kind}] ${row.text}${
          String(asRecord(row.data).trace_id || '') ? ` trace=${String(asRecord(row.data).trace_id || '')}` : ''
        }`,
      })),
    [filteredDebateEvents],
  );

  const mappingItems = useMemo(() => {
    return mappingEvents
      .slice()
      .reverse()
      .map((row, index) => {
        const data = asRecord(row.data);
        return {
          id: `${row.id}_${index}`,
          timeText: row.timeText,
          matched: typeof data.matched === 'boolean' ? (data.matched ? '命中' : '未命中') : '未知',
          domain: firstTextValue(data, ['domain']) || '-',
          aggregate: firstTextValue(data, ['aggregate']) || '-',
          ownerTeam: firstTextValue(data, ['owner_team']) || '-',
          owner: firstTextValue(data, ['owner']) || '-',
          confidence:
            typeof data.confidence === 'number'
              ? `${(Number(data.confidence) * 100).toFixed(1)}%`
              : '-',
          reason: firstTextValue(data, ['reason']) || '-',
        };
      });
  }, [mappingEvents]);

  const mappingEmptyHint = useMemo(() => {
    if (mappingItems.length > 0) return '';
    if (!sessionId) {
      return '尚未启动分析，请先在“输入故障信息”页点击“启动分析”。';
    }
    const status = String(sessionDetail?.status || '').toLowerCase();
    const hasAssetProgressEvent = eventRecords.some((row) => {
      const data = asRecord(row.data);
      const phase = String(data.phase || '').toLowerCase();
      return (
        row.kind === 'asset_collection_started' ||
        row.kind === 'runtime_assets_collected' ||
        row.kind === 'asset_collection_completed' ||
        row.kind === 'asset_log_parse_fallback_local' ||
        phase.includes('asset')
      );
    });
    if (running || hasAssetProgressEvent || status === 'running' || status === 'analyzing') {
      return '正在执行责任田映射，请稍候，结果会自动展示在这里。';
    }
    if (status === 'failed' || status === 'cancelled') {
      return '本次分析未完成，责任田映射结果暂不可用。请查看报错后重试。';
    }
    if (status === 'completed') {
      return '本次分析未命中责任田映射，请补充更具体的接口 URL、错误日志或堆栈后重试。';
    }
    return '等待分析开始后，这里会展示责任田映射结果。';
  }, [eventRecords, mappingItems.length, running, sessionDetail?.status, sessionId]);

  const mainAgentConclusion = useMemo(() => {
    for (const row of eventRecords) {
      if (row.kind !== 'agent_chat_message') continue;
      const data = asRecord(row.data);
      const agent = firstTextValue(data, ['agent_name', 'agent']);
      if (agent !== 'ProblemAnalysisAgent') continue;
      const messageText = firstTextValue(data, ['message']);
      if (messageText) {
        return {
          text: normalizeMarkdownText(extractChatMessageText(messageText)),
          timeText: row.timeText,
        };
      }
    }
    if (debateResult?.root_cause) {
      if (!isEffectiveConclusionText(debateResult.root_cause)) {
        return null;
      }
      return {
        text: debateResult.root_cause,
        timeText: formatBeijingDateTime(debateResult.created_at),
      };
    }
    return null;
  }, [eventRecords, debateResult]);

  const reportSections = useMemo(() => {
    const content = String(reportResult?.content || '').trim();
    if (!content) return [];
    const lines = content.replace(/\r/g, '').split('\n');
    const sections: Array<{ title: string; body: string }> = [];
    let currentTitle = '报告摘要';
    let currentBody: string[] = [];
    const flush = () => {
      const body = currentBody
        .join('\n')
        .replace(/```[\s\S]*?```/g, '')
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/`([^`]+)`/g, '$1')
        .trim();
      if (body) {
        sections.push({ title: currentTitle, body });
      }
      currentBody = [];
    };
    lines.forEach((line) => {
      const heading = line.match(/^\s{0,3}#{1,6}\s+(.+)$/);
      if (heading) {
        flush();
        currentTitle = heading[1].trim();
        return;
      }
      currentBody.push(line.replace(/^\s*[-*]\s+/, '• '));
    });
    flush();
    if (sections.length === 0 && content) {
      return [{ title: '报告内容', body: normalizeMarkdownText(content) }];
    }
    return sections;
  }, [reportResult]);

  const debateSummaryCards = useMemo(() => {
    if (!debateResult) return [];
    const cards: Array<{ title: string; body: string }> = [];
    const rootCause = String(debateResult.root_cause || '').trim();
    if (rootCause) {
      cards.push({ title: '根因结论', body: rootCause });
    }
    const evidenceItems = Array.isArray(debateResult.evidence_chain) ? debateResult.evidence_chain : [];
    if (evidenceItems.length > 0) {
      const lines = evidenceItems.slice(0, 8).map((item, index) => {
        const evidence = asRecord(item);
        const evidenceId = firstTextValue(evidence, ['evidence_id']);
        const source = firstTextValue(evidence, ['source']) || '-';
        const desc = firstTextValue(evidence, ['description']) || '-';
        const ref = firstTextValue(evidence, ['source_ref', 'location']);
        return `${index + 1}. ${evidenceId ? `[${evidenceId}] ` : ''}${desc}（来源：${source}${ref ? `，引用：${ref}` : ''}）`;
      });
      cards.push({ title: '证据链', body: lines.join('\n') });
    }
    const impact = asRecord(debateResult.impact_analysis || {});
    if (Object.keys(impact).length > 0) {
      cards.push({
        title: '影响评估',
        body: [
          `受影响服务：${Array.isArray(impact.affected_services) ? impact.affected_services.join('、') || '-' : '-'}`,
          `业务影响：${firstTextValue(impact, ['business_impact']) || '-'}`,
        ].join('\n'),
      });
    }
    const fix = asRecord(debateResult.fix_recommendation || {});
    if (Object.keys(fix).length > 0) {
      const stepTexts = Array.isArray(fix.steps)
        ? fix.steps
            .slice(0, 6)
            .map((step) => {
              const row = asRecord(step);
              return firstTextValue(row, ['summary', 'action', 'step']) || toDisplayText(step);
            })
            .filter(Boolean)
        : [];
      cards.push({
        title: '修复建议',
        body: [
          firstTextValue(fix, ['summary']),
          stepTexts.length ? `步骤：\n${stepTexts.map((step, idx) => `${idx + 1}. ${step}`).join('\n')}` : '',
        ]
          .filter(Boolean)
          .join('\n'),
      });
    }
    const verificationItems = Array.isArray(debateResult.verification_plan) ? debateResult.verification_plan : [];
    if (verificationItems.length > 0) {
      const lines = verificationItems.slice(0, 8).map((item, index) => {
        const row = asRecord(item);
        const objective = firstTextValue(row, ['objective']) || '-';
        const dimension = firstTextValue(row, ['dimension']) || '-';
        const criteria = firstTextValue(row, ['pass_criteria']) || '-';
        return `${index + 1}. [${dimension}] ${objective}\n通过标准：${criteria}`;
      });
      cards.push({ title: '验证计划', body: lines.join('\n') });
    }
    return cards;
  }, [debateResult]);

  const regenerateReport = async () => {
    if (!incidentId) return;
    setReportLoading(true);
    try {
      const report = await reportApi.regenerate(incidentId);
      setReportResult(report);
      message.success('报告已重新生成');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '报告生成失败');
    } finally {
      setReportLoading(false);
    }
  };

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
            资产映射
          </Button>
          <Button type={activeStep === 2 ? 'primary' : 'default'} onClick={() => void switchToStep(2)}>
            辩论过程
          </Button>
          <Button type={activeStep === 3 ? 'primary' : 'default'} onClick={() => void switchToStep(3)}>
            辩论结果
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
                <Space>
                  <Button type="primary" loading={loading || running} onClick={() => void startAnalysisFromInput()}>
                    创建并启动分析
                  </Button>
                  <Button loading={loading} onClick={() => void createIncidentAndSession()}>
                    仅创建故障与会话
                  </Button>
                </Space>
              )}
              {incidentId && !sessionId && (
                <Space>
                  <Button type="primary" loading={loading || running} onClick={() => void startAnalysisFromInput()}>
                    初始化并启动分析
                  </Button>
                  <Button loading={loading} onClick={() => void initSessionForExistingIncident()}>
                    使用当前故障初始化会话
                  </Button>
                </Space>
              )}
              {incidentId && sessionId && (
                <Button type="primary" loading={loading || running} onClick={() => void startAnalysisFromInput()}>
                  启动分析
                </Button>
              )}
            </Space>
          </Card>
        )}

        {activeStep === 1 && <AssetMappingPanel mappingItems={mappingItems} mappingEmptyHint={mappingEmptyHint} />}

        {activeStep === 2 && (
          <DebateProcessPanel
            incidentId={incidentId}
            sessionId={sessionId}
            running={running}
            loading={loading}
            debateMaxRounds={debateMaxRounds}
            onStartRealtimeDebate={startRealtimeDebate}
            onCancel={() => sendWsControl('cancel')}
            onResume={() => sendWsControl('resume')}
            onRetryFailed={retryFailedAgents}
            eventFiltersNode={renderEventFilters()}
            dialogueNode={renderDialogueStream()}
            roundCollapseItems={roundCollapseItems}
            timelineItems={timelineItems}
          />
        )}

        {activeStep === 3 && (
          <DebateResultPanel
            mainAgentConclusion={mainAgentConclusion}
            sessionStatus={String(sessionDetail?.status || '').toLowerCase()}
            sessionError={extractSessionError(sessionDetail)}
            debateSummaryCards={debateSummaryCards}
            reportResult={reportResult}
            reportSections={reportSections}
            reportLoading={reportLoading}
            incidentId={incidentId}
            sessionId={sessionId}
            onRegenerateReport={regenerateReport}
          />
        )}
      </div>
    </div>
  );
};

export default IncidentPage;
