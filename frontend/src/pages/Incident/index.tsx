import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Card,
  Space,
  Spin,
  Tag,
  Tabs,
  Typography,
  Upload,
  type UploadProps,
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
import type { InvestigationLeadsView } from '@/components/incident/AssetMappingPanel';
import DebateProcessPanel from '@/components/incident/DebateProcessPanel';
import DebateResultPanel from '@/components/incident/DebateResultPanel';
import IncidentOverviewPanel from '@/components/incident/IncidentOverviewPanel';
import DialogueFilterBar from '@/components/incident/DialogueFilterBar';
import DialogueStream, { type DialogueViewMessage } from '@/components/incident/DialogueStream';
import AgentNetworkGraph, {
  type AgentNetworkEdge,
  type AgentNetworkNode,
  type AgentNetworkStep,
} from '@/components/incident/AgentNetworkGraph';

const { Text } = Typography;

type EventRecord = {
  id: string;
  timeText: string;
  kind: string;
  text: string;
  data?: unknown;
};

type IncidentFormState = {
  title: string;
  description: string;
  severity: string;
  service_name: string;
  environment: string;
  log_content: string;
};

type DialogueMessage = DialogueViewMessage & {
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

type NetworkStepDetailItem = {
  id: string;
  timeText: string;
  agentName: string;
  kind: string;
  summary: string;
  detailLines?: string[];
  leadGroups?: Array<{ label: string; items: string[] }>;
};

type LeadFilter = {
  label: string;
  value: string;
} | null;

type SessionQualitySummary = {
  limitedAnalysis: boolean;
  limitedAgentNames: string[];
  limitedCount: number;
  evidenceGap: boolean;
  riskFactors: string[];
  evidenceCoverage: {
    ok: number;
    degraded: number;
    missing: number;
  };
};

type QualityFocus = {
  label: string;
  agentNames: string[];
  eventType?: string;
  statusFilter?: 'all' | 'inferred_without_tool' | 'missing';
} | null;

type PersistedRunningTask = {
  incidentId: string;
  sessionId: string;
  taskId: string;
  mode: string;
  startedAt: string;
  status?: string;
};

const RUNNING_ANALYSIS_STORAGE_KEY = 'incident_running_analysis_task';

const IncidentPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const { incidentId: routeIncidentId } = useParams();
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [incidentForm, setIncidentForm] = useState<IncidentFormState>({
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
  const [selectedLeadFilter, setSelectedLeadFilter] = useState<LeadFilter>(null);
  const [selectedQualityFocus, setSelectedQualityFocus] = useState<QualityFocus>(null);
  const [selectedNetworkStep, setSelectedNetworkStep] = useState<AgentNetworkStep | null>(null);
  const [activeProcessTab, setActiveProcessTab] = useState('dialogue');
  const [running, setRunning] = useState(false);
  const [debateMaxRounds, setDebateMaxRounds] = useState<number>(1);
  const [executionMode, setExecutionMode] = useState<'standard' | 'quick' | 'background' | 'async'>('standard');
  const [logUploadMeta, setLogUploadMeta] = useState<{ name: string; size: number; lines: number } | null>(null);
  const [bootstrapping, setBootstrapping] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const navShellRef = useRef<HTMLDivElement | null>(null);
  const pollingRef = useRef(false);
  const runningRef = useRef(false);
  const assetMappingReadyRef = useRef(false);
  const autoStartConsumedRef = useRef<Set<string>>(new Set());
  const streamTimersRef = useRef<Record<string, number>>({});
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const seenEventDedupeKeysRef = useRef<Set<string>>(new Set());
  const seenEventFingerprintsRef = useRef<Set<string>>(new Set());
  const pendingEventRecordsRef = useRef<EventRecord[]>([]);
  const eventFlushTimerRef = useRef<number | null>(null);

  const readPersistedRunningTask = (): PersistedRunningTask | null => {
    try {
      const raw = localStorage.getItem(RUNNING_ANALYSIS_STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as PersistedRunningTask;
      if (!parsed || typeof parsed !== 'object') return null;
      if (!parsed.sessionId || !parsed.taskId) return null;
      return parsed;
    } catch {
      return null;
    }
  };

  const persistRunningTask = (payload: PersistedRunningTask) => {
    try {
      localStorage.setItem(RUNNING_ANALYSIS_STORAGE_KEY, JSON.stringify(payload));
    } catch {
      // 本地存储失败不会影响后台任务继续运行。
    }
  };

  const clearPersistedRunningTask = (sid?: string) => {
    try {
      const existing = readPersistedRunningTask();
      if (!existing) return;
      if (sid && existing.sessionId !== sid) return;
      localStorage.removeItem(RUNNING_ANALYSIS_STORAGE_KEY);
    } catch {
      // 忽略本地清理异常，避免影响界面主流程。
    }
  };

  const isLowLevelRealtimeNoise = (kind: string): boolean => [
    'llm_stream_delta',
    'llm_http_request',
    'llm_http_response',
    'llm_call_started',
    'llm_call_completed',
    'llm_request_started',
    'llm_request_completed',
    'llm_invoke_path',
  ].includes(kind);

  const flushPendingEvents = () => {
    if (eventFlushTimerRef.current) {
      window.clearTimeout(eventFlushTimerRef.current);
      eventFlushTimerRef.current = null;
    }
    if (!pendingEventRecordsRef.current.length) return;
    const buffered = pendingEventRecordsRef.current;
    pendingEventRecordsRef.current = [];
    setEventRecords((prev) => [...buffered.reverse(), ...prev].slice(0, 180));
  };

  const appendEvent = (kind: string, text: string, data?: unknown) => {
    if (isLowLevelRealtimeNoise(kind)) return;
    const dataRecord = asRecord(data);
    const dedupeKey = String(dataRecord.dedupe_key || '').trim();
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
    if (dedupeKey) {
      if (seenEventDedupeKeysRef.current.has(dedupeKey)) {
        return;
      }
      seenEventDedupeKeysRef.current.add(dedupeKey);
    }
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
      id: dedupeKey || eventId || `${Date.now()}_${Math.random().toString(16).slice(2)}`,
      timeText: displayTime,
      kind,
      text,
      data,
    };
    pendingEventRecordsRef.current.push(record);
    if (eventFlushTimerRef.current === null) {
      eventFlushTimerRef.current = window.setTimeout(() => {
        flushPendingEvents();
      }, 80);
    }
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
    if (toolName === 'agent_skill_router' || preview.skill_context) {
      const ctx = preview.skill_context && typeof preview.skill_context === 'object'
        ? asRecord(preview.skill_context)
        : preview;
      const base = preview.base_tool_context && typeof preview.base_tool_context === 'object'
        ? asRecord(preview.base_tool_context)
        : {};
      const summary = String(ctx.summary || '-');
      const status = String(ctx.status || '-');
      const items = Array.isArray(ctx.items) ? ctx.items : [];
      const top = items
        .map((item) => asRecord(item))
        .map((item) => {
          const name = String(item.name || '-');
          const score = String(item.score || '-');
          const path = String(item.path || '-');
          return `${name} (score=${score}) @ ${path}`;
        })
        .slice(0, truncate ? 4 : 12);
      return [
        `Skill状态：${status}`,
        `Skill摘要：${summary}`,
        `命中数量：${items.length}`,
        Object.keys(base).length
          ? `基础工具状态：${String(base.name || '-')}/${String(base.status || '-')}`
          : '',
        top.length ? `命中明细：${top.join('；')}` : '',
      ]
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
        const callId = firstTextValue(row, ['call_id']) || '-';
        const action = firstTextValue(row, ['action']) || '-';
        const status = firstTextValue(row, ['status']) || '-';
        const requestSummary = firstTextValue(row, ['request_summary']);
        const responseSummary = firstTextValue(row, ['response_summary']);
        const duration = firstTextValue(row, ['duration_ms']);
        const detail = toDisplayText(row.detail);
        return `${index + 1}. [${ts}] call_id=${callId} action=${action} status=${status}${
          duration ? ` duration_ms=${duration}` : ''
        }\n${requestSummary ? `request=${requestSummary}\n` : ''}${responseSummary ? `response=${responseSummary}\n` : ''}${detail}`;
      })
      .join('\n');
  };

  const formatFocusedContextPreview = (
    agentName: string,
    preview: Record<string, unknown>,
    detail: Record<string, unknown>,
  ): string => {
    const source = Object.keys(detail).length > 0 ? detail : preview;
    if (!source || Object.keys(source).length === 0) return '';
    const pickList = (value: unknown, limit = 6) =>
      Array.isArray(value) ? value.map((item) => String(item || '').trim()).filter(Boolean).slice(0, limit) : [];
    if (agentName === 'CodeAgent') {
      const entry = asRecord(source.problem_entrypoint);
      const scope = asRecord(source.mapped_code_scope);
      const methodChain = Array.isArray(source.method_call_chain) ? source.method_call_chain.map((item) => asRecord(item)) : [];
      const windows = Array.isArray(source.code_windows) ? source.code_windows.map((item) => asRecord(item)) : [];
      return [
        `问题入口：${String(entry.method || '-') || '-'} ${String(entry.path || '-')}`.trim(),
        `服务：${String(entry.service || '-')}`,
        pickList(scope.code_artifacts, 5).length ? `责任田代码：${pickList(scope.code_artifacts, 5).join('；')}` : '',
        methodChain.length
          ? `方法链：${methodChain.map((item) => `${String(item.symbol || '-')}.${String(item.method || '-')}`).slice(0, 4).join(' -> ')}`
          : '',
        windows.length ? `代码窗口：${windows.map((item) => String(item.file || '-')).slice(0, 4).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'ProblemAnalysisAgent') {
      const summary = asRecord(source.coordination_summary);
      return [
        `主模式：${String(summary.dominant_pattern || '-')}`,
        pickList(summary.priority_tracks, 4).length ? `优先调查线：${pickList(summary.priority_tracks, 4).join('；')}` : '',
        pickList(summary.dispatch_targets, 5).length ? `建议分发：${pickList(summary.dispatch_targets, 5).join(' -> ')}` : '',
        pickList(summary.evidence_points, 4).length ? `初始依据：${pickList(summary.evidence_points, 4).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'JudgeAgent') {
      const summary = asRecord(source.verdict_summary);
      return [
        `主模式：${String(summary.dominant_pattern || '-')}`,
        pickList(summary.decision_axes, 4).length ? `裁决维度：${pickList(summary.decision_axes, 4).join('；')}` : '',
        pickList(summary.evidence_points, 4).length ? `裁决依据：${pickList(summary.evidence_points, 4).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'VerificationAgent') {
      const summary = asRecord(source.verification_summary);
      return [
        `主模式：${String(summary.dominant_pattern || '-')}`,
        pickList(summary.checkpoints, 4).length ? `验证检查点：${pickList(summary.checkpoints, 4).join('；')}` : '',
        pickList(summary.evidence_points, 4).length ? `验证依据：${pickList(summary.evidence_points, 4).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'CriticAgent') {
      const summary = asRecord(source.critique_summary);
      return [
        `主模式：${String(summary.dominant_pattern || '-')}`,
        pickList(summary.challenge_axes, 4).length ? `质疑维度：${pickList(summary.challenge_axes, 4).join('；')}` : '',
        pickList(summary.evidence_points, 4).length ? `质疑依据：${pickList(summary.evidence_points, 4).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'RebuttalAgent') {
      const summary = asRecord(source.rebuttal_summary);
      return [
        `主模式：${String(summary.dominant_pattern || '-')}`,
        pickList(summary.reinforcement_axes, 4).length ? `补强维度：${pickList(summary.reinforcement_axes, 4).join('；')}` : '',
        pickList(summary.evidence_points, 4).length ? `补强依据：${pickList(summary.evidence_points, 4).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'RuleSuggestionAgent') {
      const summary = asRecord(source.rule_summary);
      return [
        `主模式：${String(summary.dominant_pattern || '-')}`,
        pickList(summary.recommendation_axes, 4).length ? `规则建议：${pickList(summary.recommendation_axes, 4).join('；')}` : '',
        pickList(summary.evidence_points, 4).length ? `建议依据：${pickList(summary.evidence_points, 4).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'LogAgent') {
      const causal = Array.isArray(source.causal_timeline) ? source.causal_timeline.map((item) => asRecord(item)) : [];
      return causal
        .slice(0, 5)
        .map((item) => `${String(item.stage || '-')}: ${String(item.message || '-')}`)
        .join('\n');
    }
    if (agentName === 'DatabaseAgent') {
      const causal = asRecord(source.causal_summary);
      return [
        `主模式：${String(causal.dominant_pattern || '-')}`,
        pickList(causal.target_tables, 6).length ? `目标表：${pickList(causal.target_tables, 6).join('；')}` : '',
        pickList(causal.likely_causes, 4).length ? `可能原因：${pickList(causal.likely_causes, 4).join('；')}` : '',
        pickList(causal.evidence_points, 4).length ? `关键证据：${pickList(causal.evidence_points, 4).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'MetricsAgent') {
      const chain = Array.isArray(source.causal_metric_chain) ? source.causal_metric_chain.map((item) => asRecord(item)) : [];
      return chain
        .slice(0, 5)
        .map((item) => `${String(item.stage || '-')}: ${String(item.label || item.metric || '-')}=${String(item.value || '-')}`)
        .join('\n');
    }
    if (agentName === 'DomainAgent') {
      const causal = asRecord(source.causal_summary);
      const scope = asRecord(causal.impact_scope);
      return [
        `主模式：${String(causal.dominant_pattern || '-')}`,
        `责任田：${String(causal.domain || '-')}/${String(causal.aggregate || '-')}`,
        `责任团队：${String(causal.owner_team || '-')}/${String(causal.owner || '-')}`,
        pickList(scope.database_tables, 6).length ? `关联表：${pickList(scope.database_tables, 6).join('；')}` : '',
        pickList(scope.dependency_services, 6).length ? `依赖：${pickList(scope.dependency_services, 6).join('；')}` : '',
        pickList(causal.evidence_points, 3).length ? `依据：${pickList(causal.evidence_points, 3).join('；')}` : '',
      ].filter(Boolean).join('\n');
    }
    if (agentName === 'RunbookAgent') {
      const summary = asRecord(source.action_summary);
      return [
        `主模式：${String(summary.dominant_pattern || '-')}`,
        pickList(summary.recommended_steps, 4).length ? `推荐动作：${pickList(summary.recommended_steps, 4).join('；')}` : '',
        pickList(summary.verification_steps, 3).length ? `验证动作：${pickList(summary.verification_steps, 3).join('；')}` : '',
        pickList(summary.evidence_points, 3).length ? `依据：${pickList(summary.evidence_points, 3).join('；')}` : '',
      ]
        .filter(Boolean)
        .join('\n');
    }
    if (agentName === 'ChangeAgent') {
      const causal = asRecord(source.causal_summary);
      const suspects = Array.isArray(causal.suspect_changes) ? causal.suspect_changes.map((item) => asRecord(item)) : [];
      return [
        `主模式：${String(causal.dominant_pattern || '-')}`,
        suspects.length
          ? `可疑变更：${suspects
              .slice(0, 3)
              .map((item) => `${String(item.commit || '-')}: ${String(item.subject || '-')}`)
              .join('；')}`
          : '',
        pickList(causal.mechanism_links, 4).length ? `机制关联：${pickList(causal.mechanism_links, 4).join('；')}` : '',
        pickList(causal.evidence_points, 4).length ? `关键证据：${pickList(causal.evidence_points, 4).join('；')}` : '',
      ]
        .filter(Boolean)
        .join('\n');
    }
    const lines = Object.entries(source)
      .slice(0, 5)
      .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : toDisplayText(value)}`);
    return lines.join('\n');
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

  const normalizeStringList = (value: unknown, limit = 16): string[] => {
    if (!Array.isArray(value)) return [];
    const picks: string[] = [];
    value.forEach((item) => {
      const text = String(item || '').trim();
      if (text) picks.push(text);
    });
    return Array.from(new Set(picks)).slice(0, limit);
  };

  const extractLeadGroups = (data: Record<string, unknown>): Array<{ label: string; items: string[] }> => {
    const groups = [
      { label: '接口', items: normalizeStringList(data.api_endpoints, 12) },
      { label: '服务', items: normalizeStringList(data.service_names, 12) },
      { label: '类名', items: normalizeStringList(data.class_names, 16) },
      { label: '代码线索', items: normalizeStringList(data.code_artifacts, 16) },
      { label: '数据库表', items: normalizeStringList(data.database_tables, 20) },
      { label: '监控项', items: normalizeStringList(data.monitor_items, 16) },
      { label: '依赖服务', items: normalizeStringList(data.dependency_services, 16) },
      { label: 'Trace', items: normalizeStringList(data.trace_ids, 8) },
      { label: '异常关键词', items: normalizeStringList(data.error_keywords, 12) },
    ];
    return groups.filter((group) => group.items.length > 0);
  };

  const pickStepKeyClues = (groups: Array<{ label: string; items: string[] }>): string[] => {
    const priority = ['接口', '数据库表', '类名', '监控项', '依赖服务', '服务', '代码线索', 'Trace', '异常关键词'];
    const ordered = groups
      .slice()
      .sort((left, right) => priority.indexOf(left.label) - priority.indexOf(right.label));
    const clues: string[] = [];
    ordered.forEach((group) => {
      group.items.forEach((item) => {
        if (clues.length >= 2) return;
        clues.push(item);
      });
    });
    return clues.slice(0, 2);
  };

  const toLeadKeys = (groups: Array<{ label: string; items: string[] }>): string[] =>
    groups.flatMap((group) => group.items.map((item) => `${group.label}:${item}`));

  const extractInvestigationLeadsView = (detail: DebateDetail | null): InvestigationLeadsView | null => {
    const context = asRecord(detail?.context);
    const leads = asRecord(context.investigation_leads);
    if (Object.keys(leads).length === 0) return null;
    return {
      apiEndpoints: normalizeStringList(leads.api_endpoints, 12),
      serviceNames: normalizeStringList(leads.service_names, 12),
      codeArtifacts: normalizeStringList(leads.code_artifacts, 16),
      classNames: normalizeStringList(leads.class_names, 16),
      databaseTables: normalizeStringList(leads.database_tables, 20),
      monitorItems: normalizeStringList(leads.monitor_items, 16),
      dependencyServices: normalizeStringList(leads.dependency_services, 16),
      traceIds: normalizeStringList(leads.trace_ids, 8),
      errorKeywords: normalizeStringList(leads.error_keywords, 12),
      domain: String(leads.domain || '').trim(),
      aggregate: String(leads.aggregate || '').trim(),
      ownerTeam: String(leads.owner_team || '').trim(),
      owner: String(leads.owner || '').trim(),
    };
  };

  const eventMatchesLead = (row: EventRecord, lead: LeadFilter): boolean => {
    if (!lead) return true;
    const data = asRecord(row.data);
    const value = String(lead.value || '').trim().toLowerCase();
    if (!value) return true;
    const haystack = [
      row.text,
      toDisplayText(data),
      ...extractLeadGroups(data).flatMap((group) => group.items),
      firstTextValue(data, ['command', 'focus', 'expected_output', 'message', 'feedback']),
    ]
      .join('\n')
      .toLowerCase();
    return haystack.includes(value);
  };

  const eventMatchesQualityFocus = (row: EventRecord, focus: QualityFocus): boolean => {
    if (!focus) return true;
    const agentNames = Array.isArray(focus.agentNames) ? focus.agentNames.map((item) => String(item || '').trim()).filter(Boolean) : [];
    if (agentNames.length === 0) return true;
    const data = asRecord(row.data);
    const eventType = String(focus.eventType || '').trim();
    if (eventType && row.kind !== eventType) {
      return false;
    }
    if (focus.statusFilter && focus.statusFilter !== 'all') {
      const evidenceStatus = String(data.evidence_status || '').trim().toLowerCase();
      if (evidenceStatus !== focus.statusFilter) {
        return false;
      }
    }
    const candidates = [
      firstTextValue(data, ['agent_name', 'agent', 'source', 'target', 'target_agent', 'reply_to']),
      row.text,
      toDisplayText(data),
    ]
      .join('\n')
      .toLowerCase();
    return agentNames.some((agent) => candidates.includes(agent.toLowerCase()));
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

  const extractRegexField = (source: string, fieldName: string): string => {
    const escaped = fieldName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const patterns = [
      new RegExp(`"${escaped}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`, 'is'),
      new RegExp(`'${escaped}'\\s*:\\s*'((?:\\\\.|[^'\\\\])*)'`, 'is'),
    ];
    for (const pattern of patterns) {
      const match = source.match(pattern);
      if (!match) continue;
      const raw = String(match[1] || '').trim();
      if (!raw) continue;
      return raw
        .replace(/\\n/g, '\n')
        .replace(/\\t/g, '\t')
        .replace(/\\"/g, '"')
        .replace(/\\'/g, "'");
    }
    return '';
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
      extractLooseJsonStringField(source, 'summary') ||
      extractRegexField(source, 'chat_message') ||
      extractRegexField(source, 'message') ||
      extractRegexField(source, 'summary');
    if (chatFromLooseJson) return chatFromLooseJson;
    if (source.includes('{') && /"(chat_message|message|summary|conclusion|analysis)"/.test(source)) {
      const stripped = stripJsonTail(source);
      if (stripped) return stripped;
      return '结构化分析结果已生成';
    }
    return source
      .replace(/^我的判断是[:：]\s*/i, '')
      .replace(/^结论[:：]\s*/i, '')
      .trim();
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

  const isCoordinationMessageText = (value: string): boolean => {
    const text = String(value || '').trim();
    if (!text) return false;
    const parsed = tryParseJson(text.replace(/```(?:json)?\s*/gi, '').replace(/```/g, '').trim());
    if (parsed) {
      return ['next_agent', 'next_mode', 'should_stop', 'commands'].some((key) => key in parsed);
    }
    const normalized = text.toLowerCase();
    return (
      normalized.includes('"next_agent"') ||
      normalized.includes('"should_stop"') ||
      normalized.includes('"commands"') ||
      normalized.includes('next_agent') && normalized.includes('should_stop')
    );
  };

  const buildConclusionCandidate = (text: string, timeText: string, sourceLabel: string) => {
    const cleaned = normalizeMarkdownText(extractChatMessageText(text));
    if (!cleaned || !isEffectiveConclusionText(cleaned) || isCoordinationMessageText(text) || isCoordinationMessageText(cleaned)) {
      return null;
    }
    return { text: cleaned, timeText, sourceLabel };
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

  const isLikelyDuplicateStatement = (leftText: string, rightText: string): boolean => {
    if (isNearDuplicateText(leftText, rightText)) return true;
    const left = normalizeForCompare(leftText);
    const right = normalizeForCompare(rightText);
    if (!left || !right) return false;
    return left.includes(right) || right.includes(left);
  };

  const formatEvidenceStatusLabel = (value: unknown): string => {
    const status = String(value || '').trim().toLowerCase();
    if (status === 'inferred_without_tool') return '工具不可用，已基于现有证据完成受限分析';
    if (status === 'missing') return '关键证据缺失，本轮未完成真实取证';
    if (status === 'degraded') return '本轮为降级结果，需补采关键证据';
    if (status === 'collected') return '已完成证据采集';
    return status ? `证据状态：${status}` : '';
  };

  const formatToolStatusLabel = (value: unknown): string => {
    const status = String(value || '').trim().toLowerCase();
    const labelMap: Record<string, string> = {
      ok: '工具执行成功',
      disabled: '工具已关闭',
      unavailable: '工具不可用',
      error: '工具执行失败',
      failed: '工具执行失败',
      timeout: '工具执行超时',
      skipped: '工具已跳过',
      skipped_by_command: '按主 Agent 命令跳过',
      unknown: '工具状态未知',
    };
    return labelMap[status] || (status ? `工具状态：${status}` : '');
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
    const isMainAgent = ['problemanalysisagent', 'mainagent', 'commanderagent', 'orchestratoragent'].includes(
      String(agentName || '').toLowerCase(),
    );
    let messageKind: 'chat' | 'tool' | 'command' | 'status' = 'status';
    let status: 'streaming' | 'done' | 'error' = 'done';
    let summary = normalizeInlineText(messageText || kind);
    let detail = '';
    let toolPayload: DialogueMessage['toolPayload'] | undefined;

    if (kind === 'agent_chat_message') {
      messageKind = 'chat';
      status = 'done';
      const replyTo = firstTextValue(data, ['reply_to']);
      summary = replyTo && replyTo !== 'all' ? `${agentName} 回复 ${replyTo}` : `${agentName} 发言`;
      const speechText = extractChatMessageText(firstTextValue(data, ['message']) || messageText || '（空发言）');
      const conclusionText = extractChatMessageText(firstTextValue(data, ['conclusion']));
      if (conclusionText) {
        const duplicated = speechText && isLikelyDuplicateStatement(conclusionText, speechText);
        detail = normalizeMarkdownText(
          [`结论：${conclusionText}`, speechText && !duplicated ? `发言：${speechText}` : '']
            .filter(Boolean)
            .join('\n'),
        );
      } else {
        detail = normalizeMarkdownText(speechText);
      }
    } else if (kind === 'agent_tool_context_prepared') {
      messageKind = 'tool';
      const toolName = firstTextValue(data, ['tool_name']) || 'unknown_tool';
      const enabled = Boolean(data.enabled);
      const used = Boolean(data.used);
      const toolStatus = firstTextValue(data, ['status']) || 'unknown';
      const toolSummary = firstTextValue(data, ['summary']) || '无摘要';
      const dataPreview = asRecord(data.data_preview);
      const dataDetail = asRecord(data.data_detail);
      const focusedPreview = asRecord(data.focused_preview);
      const focusedDetail = asRecord(data.focused_detail);
      const commandGate = asRecord(data.command_gate);
      const auditLog = Array.isArray(data.audit_log) ? data.audit_log : [];
      const toolLabelMap: Record<string, string> = {
        local_log_reader: '日志文件读取工具',
        domain_excel_lookup: '责任田文档查询工具',
        git_repo_search: '代码仓检索工具',
        git_change_window: '变更窗口分析工具',
        agent_skill_router: 'Skill 路由工具',
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
      const focusedText = formatFocusedContextPreview(agentName, focusedPreview, focusedDetail);
      const commandGateReason = firstTextValue(commandGate, ['reason']) || '-';
      const commandGateSource = firstTextValue(commandGate, ['decision_source']) || '-';
      const commandGateAllow = typeof commandGate.allow_tool === 'boolean' ? (commandGate.allow_tool ? '是' : '否') : '-';
      const auditText = formatToolAuditLog(auditLog);
      status = toolStatus === 'error' ? 'error' : 'done';
      summary = `${agentName} 工具调用：${toolLabel}（${statusLabel}）`;
      const limitedAnalysis =
        !used && ['disabled', 'unavailable', 'error', 'failed', 'timeout'].includes(toolStatus)
          && commandGate.allow_tool === true;
      toolPayload = {
        toolName: toolLabel,
        statusLabel,
        requestText: [
          `开关状态：${enabled ? '开启' : '关闭'}`,
          `是否实际调用：${used ? '是' : '否'}`,
          `命令门禁：允许调用=${commandGateAllow}，原因=${commandGateReason}，来源=${commandGateSource}`,
        ]
          .filter(Boolean)
          .join('\n'),
        responseText: [
          limitedAnalysis ? '工具未实际执行，相关 Agent 将基于现有证据继续进行受限分析。' : '',
          `工具反馈：${toolSummary}`,
          `数据摘要：${dataSummaryText}`,
          `返回详情：${dataDetailText}`,
        ]
          .filter(Boolean)
          .join('\n\n'),
        auditText,
        focusedText,
      };
      detail = normalizeMarkdownText(
        [
          `我使用了工具：${toolLabel}`,
          `开关状态：${enabled ? '开启' : '关闭'}`,
          `是否实际调用：${used ? '是' : '否'}`,
          `执行结果：${statusLabel}`,
          limitedAnalysis ? '说明：工具不可用，后续会转入“基于现有证据的受限分析”。' : '',
          `命令门禁：允许调用=${commandGateAllow}，原因=${commandGateReason}，来源=${commandGateSource}`,
          `工具反馈：${toolSummary}`,
          `获取数据摘要：\n${dataSummaryText}`,
          focusedText ? `聚焦分析上下文：\n${focusedText}` : '',
          `工具返回详情：\n${dataDetailText}`,
          `调用审计记录：\n${auditText}`,
        ]
          .filter(Boolean)
          .join('\n'),
      );
    } else if (kind === 'agent_tool_io') {
      messageKind = 'tool';
      const action = firstTextValue(data, ['io_action']) || '-';
      const ioStatus = firstTextValue(data, ['io_status']) || '-';
      const ioCallId = firstTextValue(data, ['io_call_id']) || '-';
      const ioTs = firstTextValue(data, ['io_timestamp']) || '-';
      const ioDuration = firstTextValue(data, ['io_duration_ms']) || '';
      const ioRequest = firstTextValue(data, ['io_request_summary']) || '';
      const ioResponse = firstTextValue(data, ['io_response_summary']) || '';
      const ioDetail = toDisplayText(data.io_detail);
      status = ioStatus === 'error' ? 'error' : 'done';
      summary = `${agentName} 工具I/O：${action}（${ioStatus}）`;
      toolPayload = {
        toolName: `工具I/O ${action}`,
        statusLabel: ioStatus,
        requestText: [ioRequest ? `请求摘要：${ioRequest}` : '', `调用ID：${ioCallId}`].filter(Boolean).join('\n'),
        responseText: [ioResponse ? `响应摘要：${ioResponse}` : '', ioDetail ? `I/O详情：${ioDetail}` : '']
          .filter(Boolean)
          .join('\n\n'),
        auditText: [`时间：${ioTs}`, ioDuration ? `耗时：${ioDuration} ms` : ''].filter(Boolean).join('\n'),
      };
      detail = normalizeMarkdownText(
        [
          `调用ID：${ioCallId}`,
          `时间：${ioTs}`,
          ioDuration ? `耗时：${ioDuration} ms` : '',
          ioRequest ? `请求摘要：${ioRequest}` : '',
          ioResponse ? `响应摘要：${ioResponse}` : '',
          `I/O 详情：\n${ioDetail}`,
        ]
          .filter(Boolean)
          .join('\n'),
      );
    } else if (kind === 'agent_tool_context_failed') {
      messageKind = 'tool';
      status = 'error';
      summary = `${agentName} 工具调用失败`;
      toolPayload = {
        toolName: '工具调用',
        statusLabel: '失败',
        requestText: '调用过程中发生异常',
        responseText: `错误信息：${firstTextValue(data, ['error']) || messageText || '未知错误'}`,
      };
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
    } else if (kind === 'session_completed') {
      messageKind = 'status';
      status = 'done';
      summary = '辩论结束，已生成最终结果';
      detail = normalizeMarkdownText(
        [
          firstTextValue(data, ['message']) || '系统已结束本次辩论会话。',
          firstTextValue(data, ['reason']) ? `结束原因：${firstTextValue(data, ['reason'])}` : '',
        ]
          .filter(Boolean)
          .join('\n'),
      );
    } else if (kind === 'debate_timeout_recovered') {
      messageKind = 'status';
      status = 'done';
      summary = '辩论已收口，系统按超时恢复路径结束';
      detail = normalizeMarkdownText(
        [
          firstTextValue(data, ['message']) || '系统检测到讨论超时后，已按恢复策略收口本轮分析。',
          firstTextValue(data, ['reason']) ? `恢复原因：${firstTextValue(data, ['reason'])}` : '',
        ]
          .filter(Boolean)
          .join('\n'),
      );
    } else if (kind === 'status_changed') {
      const nextStatus = firstTextValue(data, ['status', 'to_status', 'new_status']).toLowerCase();
      if (['completed', 'failed', 'cancelled', 'waiting_review', 'waiting_resume'].includes(nextStatus)) {
        messageKind = 'status';
        status = nextStatus === 'failed' ? 'error' : 'done';
        const labelMap: Record<string, string> = {
          completed: '会话状态：已完成',
          failed: '会话状态：失败',
          cancelled: '会话状态：已取消',
          waiting_review: '会话状态：待人工审核',
          waiting_resume: '会话状态：审核通过，待恢复执行',
        };
        summary = labelMap[nextStatus] || `会话状态：${nextStatus}`;
        detail = normalizeMarkdownText(
          [
            firstTextValue(data, ['message']) || messageText || summary,
            firstTextValue(data, ['reason']) ? `原因：${firstTextValue(data, ['reason'])}` : '',
          ]
            .filter(Boolean)
            .join('\n'),
        );
      } else {
        return null;
      }
    } else if (kind === 'agent_command_feedback') {
      messageKind = 'command';
      const degraded = Boolean(data.degraded);
      const evidenceStatus = firstTextValue(data, ['evidence_status']);
      const toolStatus = firstTextValue(data, ['tool_status']);
      const degradeReason = extractChatMessageText(firstTextValue(data, ['degrade_reason']));
      const missingInfo = Array.isArray(data.missing_info) ? data.missing_info.map((item) => String(item || '').trim()).filter(Boolean) : [];
      const nextChecks = Array.isArray(data.next_checks) ? data.next_checks.map((item) => String(item || '').trim()).filter(Boolean) : [];
      const evidenceStatusLabel = formatEvidenceStatusLabel(evidenceStatus);
      const toolStatusLabel = formatToolStatusLabel(toolStatus);
      status = degraded ? 'error' : 'done';
      summary = evidenceStatus === 'inferred_without_tool'
        ? `${agentName} 提交受限分析反馈`
        : degraded
          ? `${agentName} 提交降级反馈`
          : `${agentName} 向主Agent反馈`;
      const feedback = extractChatMessageText(firstTextValue(data, ['feedback']));
      const command = extractChatMessageText(firstTextValue(data, ['command']));
      const confidenceRaw = data.confidence;
      const confidenceLine =
        typeof confidenceRaw === 'number' ? `置信度：${(Number(confidenceRaw) * 100).toFixed(1)}%` : '';
      detail = normalizeMarkdownText(
        [
          feedback ? `反馈：${feedback}` : '',
          command ? `命令：${command}` : '',
          evidenceStatusLabel ? `分析类型：${evidenceStatusLabel}` : '',
          toolStatusLabel ? `${toolStatusLabel}` : '',
          degradeReason ? `限制原因：${degradeReason}` : '',
          missingInfo.length > 0 ? `缺失证据：${missingInfo.join('、')}` : '',
          nextChecks.length > 0 ? `建议补采：${nextChecks.join('；')}` : '',
          confidenceLine,
        ]
          .filter(Boolean)
          .join('\n'),
      );
    } else if (kind === 'agent_command_issued') {
      messageKind = 'command';
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
      isMainAgent,
      messageKind,
      phase,
      eventType: kind,
      traceId: firstTextValue(data, ['trace_id']) || '-',
      latencyMs: typeof data.latency_ms === 'number' ? Number(data.latency_ms) : undefined,
      status,
      summary,
      detail,
      toolPayload,
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
      case 'session_completed':
        return `辩论结束 ${String(data?.reason || data?.message || '')}`.trim();
      case 'debate_timeout_recovered':
        return `辩论按超时恢复路径结束 ${String(data?.reason || data?.message || '')}`.trim();
      case 'status_changed': {
        const nextStatus = String(data?.status || data?.to_status || data?.new_status || '').trim();
        return `状态更新 ${nextStatus || '-'} ${String(data?.reason || data?.message || '')}`.trim();
      }
      case 'ws_ack':
        if (String(data?.message || '').toLowerCase().includes('resume')) {
          const resumeFrom = asRecord(data?.resume_from);
          const fromPhase = String(resumeFrom.phase || '-');
          const fromEvent = String(resumeFrom.event_type || '-');
          const fromRound = String(resumeFrom.round || '0');
          return `恢复分析确认：从 phase=${fromPhase}, event=${fromEvent}, round=${fromRound} 继续`;
        }
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
      kind === 'session_completed' ||
      kind === 'debate_timeout_recovered' ||
      kind === 'status_changed' ||
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

  function parseTargetAgentFromEvent(data: Record<string, unknown>, text: string): string {
    const direct = firstTextValue(data, ['target_agent', 'receiver', 'to_agent', 'target']);
    if (direct) return direct;
    const fromText = String(text || '').match(/->\s*([A-Za-z][A-Za-z0-9_-]*)/);
    return fromText?.[1] || '';
  }

  function extractNetworkRelationFromEvent(
    row: EventRecord,
  ): { source: string; target: string; relation: AgentNetworkEdge['relation'] } | null {
    const data = asRecord(row.data);
    const kind = row.kind;
    const agentName = firstTextValue(data, ['agent_name', 'agent']) || '';

    if (kind === 'agent_command_issued') {
      const source = agentName || 'ProblemAnalysisAgent';
      const target = parseTargetAgentFromEvent(data, row.text);
      if (source && target) {
        return { source, target, relation: 'command' };
      }
      return null;
    }

    if (kind === 'agent_command_feedback') {
      const source = agentName;
      const target = firstTextValue(data, ['target_agent']) || 'ProblemAnalysisAgent';
      if (source && target) {
        return { source, target, relation: 'feedback' };
      }
      return null;
    }

    if (kind === 'agent_chat_message') {
      const source = agentName;
      const target = firstTextValue(data, ['reply_to']);
      if (source && target && target !== 'all') {
        return { source, target, relation: 'reply' };
      }
    }

    return null;
  }

  const resetDialogueFilters = () => {
    setEventFilterAgent('all');
    setEventFilterPhase('all');
    setEventFilterType('all');
    setEventSearchText('');
  };

  const resetQualityFocus = () => {
    setSelectedQualityFocus(null);
  };

  const updateQualityFocusStatus = (statusFilter: 'all' | 'inferred_without_tool' | 'missing') => {
    setSelectedQualityFocus((prev) => (prev ? { ...prev, statusFilter } : prev));
  };

  const resetProcessFocus = () => {
    setSelectedNetworkStep(null);
    setActiveProcessTab('dialogue');
    setSelectedQualityFocus(null);
  };

  const loadSessionArtifacts = async (sid: string) => {
    const detail = await debateApi.get(sid);
    const status = String(detail.status || '').toLowerCase();
    if (['completed', 'failed', 'cancelled'].includes(status)) {
      clearPersistedRunningTask(sid);
    }
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
    const modeRaw = String((detail.context as Record<string, unknown> | undefined)?.execution_mode || '').trim();
    if (modeRaw === 'standard' || modeRaw === 'quick' || modeRaw === 'background' || modeRaw === 'async') {
      setExecutionMode(modeRaw);
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
          .filter((item) => {
            const row = (item || {}) as Record<string, unknown>;
            const event = (row.event || {}) as Record<string, unknown>;
            return !isLowLevelRealtimeNoise(String(event.type || ''));
          })
          .slice(0, 180)
          .map((item, idx) => {
            const row = (item || {}) as Record<string, unknown>;
            const event = (row.event || {}) as Record<string, unknown>;
            const ts = typeof row.timestamp === 'string' ? row.timestamp : '';
            const kind = typeof event.type === 'string' ? event.type : 'event';
            const eventId = typeof event.event_id === 'string' ? event.event_id : '';
            const dedupeKey = typeof event.dedupe_key === 'string' ? event.dedupe_key : '';
            return {
              id: dedupeKey || eventId || `persisted_${idx}_${ts || kind}`,
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
        const dedupeKey = typeof event.dedupe_key === 'string' ? event.dedupe_key : '';
        if (dedupeKey) seenEventDedupeKeysRef.current.add(dedupeKey);
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
      const session = await debateApi.createSession(incident.id, {
        maxRounds: debateMaxRounds,
        mode: executionMode,
      });
      seenEventIdsRef.current.clear();
      seenEventDedupeKeysRef.current.clear();
      seenEventFingerprintsRef.current.clear();
      setEventRecords([]);
      setStreamedMessageText({});
      setExpandedDialogueIds({});
      resetProcessFocus();
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
      const session = await debateApi.createSession(incidentId, {
        maxRounds: debateMaxRounds,
        mode: executionMode,
      });
      seenEventIdsRef.current.clear();
      seenEventDedupeKeysRef.current.clear();
      seenEventFingerprintsRef.current.clear();
      setEventRecords([]);
      setStreamedMessageText({});
      setExpandedDialogueIds({});
      resetProcessFocus();
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

  const pollTaskUntilDone = async (taskId: string, sid: string) => {
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      const maxAttempts = 120;
      for (let i = 0; i < maxAttempts; i += 1) {
        const task = await debateApi.getTask(taskId).catch(() => null);
        const status = String(task?.status || 'pending').toLowerCase();
        persistRunningTask({
          incidentId: incidentId || String(sessionDetail?.incident_id || ''),
          sessionId: sid,
          taskId,
          mode: executionMode,
          startedAt: new Date().toISOString(),
          status,
        });
        appendEvent('task_status', `后台任务状态: ${status}`, { task_id: taskId, status });
        if (status === 'completed') {
          const resultStatus = String(task?.result?.status || '').toLowerCase();
          if (resultStatus === 'waiting_review') {
            appendEvent('human_review_requested', `会话进入人工审核: ${String(task?.result?.review_reason || '等待人工审核')}`, {
              type: 'human_review_requested',
              phase: 'judgment',
              status: 'waiting',
              reason: String(task?.result?.review_reason || ''),
              resume_from_step: String(task?.result?.resume_from_step || ''),
            });
            await loadSessionArtifacts(sid).catch(() => undefined);
            advanceStep(2);
            setRunning(false);
            return;
          }
          await loadSessionArtifacts(sid);
          advanceStep(3);
          setRunning(false);
          clearPersistedRunningTask(sid);
          return;
        }
        if (status === 'failed') {
          appendEvent('session_failed', `后台任务失败: ${String(task?.error || '')}`, {
            task_id: taskId,
            status,
            error: String(task?.error || ''),
          });
          await loadSessionArtifacts(sid).catch(() => undefined);
          advanceStep(2);
          setRunning(false);
          clearPersistedRunningTask(sid);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      appendEvent('result_timeout', '后台任务等待超时，请稍后查看结果');
      setRunning(false);
    } finally {
      pollingRef.current = false;
    }
  };

  const attachDebateStream = async (
    options?: { sessionId?: string; incidentId?: string },
  ) => {
    const targetSessionId = options?.sessionId || sessionId;
    const targetIncidentId = options?.incidentId || incidentId;
    if (!targetSessionId || !targetIncidentId) return;
    resetDialogueFilters();
    appendEvent('stream_attach', '已连接后台分析事件流');

    try {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      const ws = new WebSocket(buildDebateWsUrl(targetSessionId, { autoStart: false }));
      wsRef.current = ws;

      ws.onopen = () => {
        appendEvent('ws_open', '后台分析事件流已连接');
      };

      ws.onmessage = async (event) => {
        try {
          const payload = JSON.parse(event.data) as { type: string; data?: any; message?: string };
          if (payload.type === 'event') {
            const type = payload.data?.type || 'event';
            appendEvent(type, formatEventText(type, payload.data || {}), payload.data);
            if (type === 'session_failed') {
              setRunning(false);
              clearPersistedRunningTask(targetSessionId);
              advanceStep(2);
              await loadSessionArtifacts(targetSessionId).catch(() => undefined);
              return;
            }
            if (type === 'human_review_requested') {
              setRunning(false);
              advanceStep(2);
              await loadSessionArtifacts(targetSessionId).catch(() => undefined);
              return;
            }
            if (type === 'human_review_approved') {
              await loadSessionArtifacts(targetSessionId).catch(() => undefined);
              return;
            }
            if (type === 'human_review_rejected') {
              setRunning(false);
              clearPersistedRunningTask(targetSessionId);
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
              await loadSessionArtifacts(targetSessionId).catch(() => undefined);
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
            const snapshotStatus = String(payload.data?.status || '').toLowerCase();
            const snapshotReviewStatus = String(payload.data?.human_review?.status || '').toLowerCase();
            const taskStatus = String(payload.data?.task_state?.status || '').toLowerCase();
            if (snapshotStatus === 'failed') {
              setRunning(false);
              advanceStep(2);
            }
            if (taskStatus === 'waiting_review' || snapshotReviewStatus === 'pending' || snapshotReviewStatus === 'approved') {
              setRunning(false);
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
            clearPersistedRunningTask(targetSessionId);
            return;
          }
          if (payload.type === 'ack') {
            appendEvent('ws_ack', `控制指令已确认: ${payload.message || '-'}`, payload.data || payload);
            return;
          }
          if (payload.type === 'error') {
            appendEvent('error', `错误: ${payload.message || 'unknown'}`, payload.data || payload);
            await loadSessionArtifacts(targetSessionId).catch(() => undefined);
          }
        } catch {
          appendEvent('unknown_payload', '收到非结构化消息');
        }
      };

      ws.onerror = () => {
        appendEvent('ws_error', '后台事件流连接异常，将继续通过任务状态轮询观察');
      };

      ws.onclose = () => {
        appendEvent('ws_close', '后台事件流订阅已关闭');
      };
    } catch (e: any) {
      message.error(e?.message || '启动失败');
    }
  };

  const startBackgroundAnalysis = async (targetSessionId: string, targetIncidentId: string) => {
    setRunning(true);
    appendEvent('start', '开始后台持续分析');
    try {
      const task = await debateApi.executeBackground(targetSessionId);
      persistRunningTask({
        incidentId: targetIncidentId,
        sessionId: targetSessionId,
        taskId: task.task_id,
        mode: executionMode,
        startedAt: new Date().toISOString(),
        status: String(task.status || 'pending'),
      });
      appendEvent('task_submitted', `后台任务已提交: ${task.task_id}`, {
        task_id: task.task_id,
        status: task.status,
        mode: executionMode,
      });
      advanceStep(2);
      await attachDebateStream({ sessionId: targetSessionId, incidentId: targetIncidentId });
      await pollTaskUntilDone(task.task_id, targetSessionId);
    } catch (e: any) {
      clearPersistedRunningTask(targetSessionId);
      message.error(e?.response?.data?.detail || e?.message || '后台任务启动失败');
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
    await startBackgroundAnalysis(targetSessionId, targetIncidentId);
  };

  const sendWsControl = async (action: 'cancel' | 'resume' | 'approve' | 'reject') => {
    if (!sessionId) return;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(action);
      appendEvent(
        'ws_control',
        action === 'cancel'
          ? '已发送取消指令'
          : action === 'resume'
            ? '已发送恢复指令'
            : action === 'approve'
              ? '已发送审核通过指令'
              : '已发送审核驳回指令',
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
          clearPersistedRunningTask(sessionId);
          message.success('会话已取消');
        } else {
          message.info('当前无可取消的运行任务');
        }
      } catch (e: any) {
        message.error(e?.response?.data?.detail || e?.message || '取消失败');
      }
      return;
    }
    if (action === 'approve' || action === 'reject') {
      try {
        if (action === 'approve') {
          await debateApi.approveHumanReview(sessionId);
          appendEvent('human_review_approved', '人工审核已批准，等待恢复执行', {
            type: 'human_review_approved',
            phase: 'judgment',
            status: 'waiting',
          });
          await loadSessionArtifacts(sessionId).catch(() => undefined);
          message.success('人工审核已批准');
        } else {
          await debateApi.rejectHumanReview(sessionId);
          appendEvent('human_review_rejected', '人工审核已驳回，本次分析结束', {
            type: 'human_review_rejected',
            phase: 'failed',
            status: 'failed',
          });
          setRunning(false);
          clearPersistedRunningTask(sessionId);
          await loadSessionArtifacts(sessionId).catch(() => undefined);
          message.success('人工审核已驳回');
        }
      } catch (e: any) {
        message.error(e?.response?.data?.detail || e?.message || '人工审核操作失败');
      }
      return;
    }
    if (action === 'resume') {
      if (String(humanReviewState?.status || '').toLowerCase() === 'pending') {
        message.info('当前仍在等待人工审核，请先批准后再恢复');
        return;
      }
      if (String(humanReviewState?.status || '').toLowerCase() === 'approved') {
        try {
          setRunning(true);
          appendEvent('human_review_resume_requested', '已通过后台任务恢复审核后执行', {
            type: 'human_review_resume_requested',
            phase: 'judgment',
            status: 'running',
          });
          const task = await debateApi.executeBackground(sessionId);
          persistRunningTask({
            incidentId,
            sessionId,
            taskId: task.task_id,
            mode: executionMode,
            startedAt: new Date().toISOString(),
            status: String(task.status || 'pending'),
          });
          await attachDebateStream({ sessionId, incidentId });
          await pollTaskUntilDone(task.task_id, sessionId);
        } catch (e: any) {
          clearPersistedRunningTask(sessionId);
          setRunning(false);
          message.error(e?.response?.data?.detail || e?.message || '恢复失败');
        }
        return;
      }
      const persisted = readPersistedRunningTask();
      if (persisted && persisted.sessionId === sessionId) {
        setRunning(true);
        await attachDebateStream({ sessionId, incidentId });
        await pollTaskUntilDone(persisted.taskId, sessionId);
        return;
      }
      message.info('当前没有可恢复的后台任务，请直接重新启动分析');
      return;
    }
    const persisted = readPersistedRunningTask();
    if (persisted && persisted.sessionId === sessionId) {
      setRunning(true);
      await attachDebateStream({ sessionId, incidentId });
      await pollTaskUntilDone(persisted.taskId, sessionId);
      return;
    }
    message.info('当前没有可恢复的后台任务，请直接重新启动分析');
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
    const querySessionId = String(searchParams.get('session_id') || '').trim();
    const modeParam = String(searchParams.get('mode') || '').trim().toLowerCase();
    if (modeParam === 'standard' || modeParam === 'quick' || modeParam === 'background' || modeParam === 'async') {
      setExecutionMode(modeParam);
    }
    const preferredView = (searchParams.get('view') || '').toLowerCase();
    if (!iid) {
      setBootstrapping(false);
      setReportResult(null);
      assetMappingReadyRef.current = false;
      return;
    }
    if (preferredView === 'result' || preferredView === 'report') {
      setActiveStep(3);
    } else if (preferredView === 'analysis') {
      setActiveStep(2);
    }
    setBootstrapping(true);
    seenEventIdsRef.current.clear();
    seenEventDedupeKeysRef.current.clear();
    seenEventFingerprintsRef.current.clear();
    setEventRecords([]);
    setStreamedMessageText({});
    setExpandedDialogueIds({});
    resetProcessFocus();
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
        const targetSessionId = querySessionId || incident.debate_session_id || '';
        if (targetSessionId) {
          setSessionId(targetSessionId);
          const detail = await loadSessionArtifacts(targetSessionId);
          const status = detail?.status || '';
          if (preferredView === 'result' || preferredView === 'report') {
            advanceStep(3);
          } else if (preferredView === 'analysis') {
            advanceStep(2);
          } else if (status === 'completed') {
            advanceStep(3);
          } else {
            advanceStep(1);
          }
          const persisted = readPersistedRunningTask();
          const lowerStatus = String(status || '').toLowerCase();
          const hasPersistedRunningTask =
            persisted &&
            persisted.sessionId === targetSessionId &&
            ['pending', 'running', 'waiting_review', 'waiting_resume'].includes(String(persisted.status || 'running').toLowerCase());
          const runningLike = ['pending', 'running', 'analyzing', 'debating', 'waiting', 'retrying'].includes(lowerStatus);
          if (hasPersistedRunningTask && !autoStartConsumedRef.current.has(targetSessionId)) {
            autoStartConsumedRef.current.add(targetSessionId);
            setRunning(runningLike || String(persisted.status || '').toLowerCase() === 'running');
            void attachDebateStream({ sessionId: targetSessionId, incidentId: iid });
            if (['pending', 'running'].includes(String(persisted.status || '').toLowerCase())) {
              void pollTaskUntilDone(persisted.taskId, targetSessionId);
            }
          }
        } else if (preferredView === 'analysis') {
          advanceStep(0);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        setBootstrapping(false);
      });
  }, [searchParams, routeIncidentId]);

  useEffect(() => {
    runningRef.current = running;
  }, [running]);

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      Object.values(streamTimersRef.current).forEach((timerId) => window.clearInterval(timerId));
      streamTimersRef.current = {};
      if (eventFlushTimerRef.current) {
        window.clearTimeout(eventFlushTimerRef.current);
        eventFlushTimerRef.current = null;
      }
      pollingRef.current = false;
    };
  }, []);

  const mappingEvents = useMemo(
    () => eventRecords.filter((row) => isAssetMappingEvent(row)),
    [eventRecords],
  );

  const debateEvents = useMemo(
    () =>
      eventRecords
        .filter((row) => isDebateProcessEvent(row))
        .filter((row) => eventMatchesLead(row, selectedLeadFilter))
        .filter((row) => eventMatchesQualityFocus(row, selectedQualityFocus)),
    [eventRecords, selectedLeadFilter, selectedQualityFocus],
  );

  const dialogueMessages = useMemo(
    () => {
      const scopedEvents = debateEvents.filter((row) => isEventRelatedToNetworkStep(row, selectedNetworkStep));
      const rawMessages = scopedEvents
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
    [debateEvents, selectedNetworkStep],
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
    return debateEvents
      .filter((row) => isEventRelatedToNetworkStep(row, selectedNetworkStep))
      .filter((row) => includeIds.has(row.id));
  }, [debateEvents, filteredDialogueMessages, selectedNetworkStep]);

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

  const eventStats = useMemo(() => {
    const agents = new Set<string>();
    const phases = new Set<string>();
    dialogueMessages.forEach((item) => {
      if (item.agentName) agents.add(item.agentName);
      if (item.phase) phases.add(item.phase);
    });
    return {
      total: debateEvents.length,
      filtered: filteredDebateEvents.length,
      agentCount: agents.size,
      phaseCount: phases.size,
    };
  }, [debateEvents.length, dialogueMessages, filteredDebateEvents.length]);

  const agentNetworkData = useMemo(() => {
    const nodeMap = new Map<string, AgentNetworkNode>();
    const edgeMap = new Map<string, AgentNetworkEdge>();
    const sequenceSteps: AgentNetworkStep[] = [];

    const inferRole = (name: string): AgentNetworkNode['role'] => {
      if (name === 'ProblemAnalysisAgent') return 'commander';
      if (!name || name.toLowerCase() === 'system') return 'observer';
      return 'specialist';
    };

    const ensureNode = (name: string): AgentNetworkNode | null => {
      const nodeId = String(name || '').trim();
      if (!nodeId) return null;
      const existing = nodeMap.get(nodeId);
      if (existing) return existing;
      const created: AgentNetworkNode = {
        id: nodeId,
        label: nodeId,
        role: inferRole(nodeId),
        inbound: 0,
        outbound: 0,
        activity: 0,
      };
      nodeMap.set(nodeId, created);
      return created;
    };

    const bumpActivity = (name: string) => {
      const node = ensureNode(name);
      if (!node) return;
      node.activity += 1;
    };

    const upsertEdge = (
      sourceName: string,
      targetName: string,
      relation: AgentNetworkEdge['relation'],
    ) => {
      const source = ensureNode(sourceName);
      const target = ensureNode(targetName);
      if (!source || !target || source.id === target.id) return;
      const edgeKey = `${source.id}|${target.id}|${relation}`;
      const existing = edgeMap.get(edgeKey);
      if (existing) {
        existing.count += 1;
      } else {
        edgeMap.set(edgeKey, {
          id: edgeKey,
          source: source.id,
          target: target.id,
          relation,
          count: 1,
        });
      }
      source.outbound += 1;
      source.activity += 1;
      target.inbound += 1;
      target.activity += 1;
    };

    const appendSequenceStep = (
      sourceName: string,
      targetName: string,
      relation: AgentNetworkEdge['relation'],
    ) => {
      const source = ensureNode(sourceName);
      const target = ensureNode(targetName);
      if (!source || !target || source.id === target.id) return;
      const last = sequenceSteps[sequenceSteps.length - 1];
      if (
        last
        && last.source === source.id
        && last.target === target.id
        && last.relation === relation
      ) {
        last.count += 1;
        return;
      }
      sequenceSteps.push({
        id: `step_${sequenceSteps.length}_${source.id}_${target.id}_${relation}`,
        source: source.id,
        target: target.id,
        relation,
        count: 1,
      });
    };

    ensureNode('ProblemAnalysisAgent');

    (sessionDetail?.rounds || []).forEach((round) => {
      const roundAgent = String(round.agent_name || '').trim();
      if (roundAgent && /agent$/i.test(roundAgent)) ensureNode(roundAgent);
    });

    debateEvents
      .slice()
      .reverse()
      .forEach((row) => {
        const data = asRecord(row.data);
        const kind = row.kind;
        const agentName = firstTextValue(data, ['agent_name', 'agent']) || '';
        if (agentName) bumpActivity(agentName);

        if (kind === 'agent_command_issued') {
          const source = agentName || 'ProblemAnalysisAgent';
          const target = parseTargetAgentFromEvent(data, row.text);
          if (target) {
            upsertEdge(source, target, 'command');
            appendSequenceStep(source, target, 'command');
          }
          return;
        }

        if (kind === 'agent_command_feedback') {
          const source = agentName;
          const target = firstTextValue(data, ['target_agent']) || 'ProblemAnalysisAgent';
          if (source && target) {
            upsertEdge(source, target, 'feedback');
            appendSequenceStep(source, target, 'feedback');
          }
          return;
        }

        if (kind === 'agent_chat_message') {
          const source = agentName;
          const replyTo = firstTextValue(data, ['reply_to']);
          if (source && replyTo && replyTo !== 'all') {
            upsertEdge(source, replyTo, 'reply');
            appendSequenceStep(source, replyTo, 'reply');
          }
          return;
        }
      });

    const nodes = Array.from(nodeMap.values()).sort((left, right) => {
      if (left.role === 'commander' && right.role !== 'commander') return -1;
      if (left.role !== 'commander' && right.role === 'commander') return 1;
      return left.label.localeCompare(right.label);
    });
    const edges = Array.from(edgeMap.values()).sort((left, right) => right.count - left.count);
    const steps = sequenceSteps.map((step) => {
      const relatedRows = debateEvents.filter((row) => isEventRelatedToNetworkStep(row, step));
      const leadGroups = relatedRows
        .filter((row) => row.kind === 'agent_command_issued')
        .flatMap((row) => extractLeadGroups(asRecord(row.data)));
      const clueCount = relatedRows
        .filter((row) => row.kind === 'agent_command_issued')
        .flatMap((row) => extractLeadGroups(asRecord(row.data)).flatMap((group) => group.items))
        .filter(Boolean).length;
      const toolCount = relatedRows.filter((row) => row.kind === 'agent_tool_context_prepared' || row.kind === 'agent_tool_io').length;
      return {
        ...step,
        clueCount,
        toolCount,
        keyClues: pickStepKeyClues(leadGroups),
      };
    });
    return { nodes, edges, steps };
  }, [debateEvents, sessionDetail?.rounds]);

  const selectedNetworkStepDetails = useMemo<NetworkStepDetailItem[]>(() => {
    if (!selectedNetworkStep) return [];
    const buildStepDetail = (row: EventRecord): NetworkStepDetailItem => {
      const data = asRecord(row.data);
      const leadGroups = row.kind === 'agent_command_issued' ? extractLeadGroups(data) : [];
      const detailLines =
        row.kind === 'agent_command_issued'
          ? [
              firstTextValue(data, ['command']) ? `任务：${extractChatMessageText(firstTextValue(data, ['command']))}` : '',
              firstTextValue(data, ['focus']) ? `重点：${extractChatMessageText(firstTextValue(data, ['focus']))}` : '',
              firstTextValue(data, ['expected_output']) ? `输出：${extractChatMessageText(firstTextValue(data, ['expected_output']))}` : '',
            ].filter(Boolean)
          : row.kind === 'agent_command_feedback'
            ? [
                firstTextValue(data, ['feedback']) ? `反馈：${extractChatMessageText(firstTextValue(data, ['feedback']))}` : '',
                firstTextValue(data, ['command']) ? `命令：${extractChatMessageText(firstTextValue(data, ['command']))}` : '',
                formatEvidenceStatusLabel(firstTextValue(data, ['evidence_status']))
                  ? `分析类型：${formatEvidenceStatusLabel(firstTextValue(data, ['evidence_status']))}` : '',
                formatToolStatusLabel(firstTextValue(data, ['tool_status']))
                  ? `${formatToolStatusLabel(firstTextValue(data, ['tool_status']))}` : '',
                firstTextValue(data, ['degrade_reason'])
                  ? `限制原因：${extractChatMessageText(firstTextValue(data, ['degrade_reason']))}` : '',
                Array.isArray(data.missing_info) && data.missing_info.length > 0
                  ? `缺失证据：${data.missing_info.map((item) => String(item || '').trim()).filter(Boolean).join('、')}` : '',
                Array.isArray(data.next_checks) && data.next_checks.length > 0
                  ? `建议补采：${data.next_checks.map((item) => String(item || '').trim()).filter(Boolean).join('；')}` : '',
                typeof data.confidence === 'number' ? `置信度：${(Number(data.confidence) * 100).toFixed(1)}%` : '',
              ].filter(Boolean)
            : row.kind === 'agent_chat_message'
              ? [extractChatMessageText(firstTextValue(data, ['message']) || row.text)].filter(Boolean)
              : [];
      const richSummary =
        row.kind === 'agent_command_issued'
          ? firstTextValue(data, ['command']) || firstTextValue(data, ['message']) || row.text
          : row.kind === 'agent_command_feedback'
            ? [
                firstTextValue(data, ['feedback']) ? `反馈：${extractChatMessageText(firstTextValue(data, ['feedback']))}` : '',
                firstTextValue(data, ['command']) ? `命令：${extractChatMessageText(firstTextValue(data, ['command']))}` : '',
                typeof data.confidence === 'number' ? `置信度：${(Number(data.confidence) * 100).toFixed(1)}%` : '',
              ]
                .filter(Boolean)
                .join('\n')
            : row.kind === 'agent_chat_message'
              ? extractChatMessageText(firstTextValue(data, ['message']) || row.text)
              : row.text;
      return {
        id: row.id,
        timeText: row.timeText,
        agentName: firstTextValue(data, ['agent_name', 'agent']) || '-',
        kind: row.kind,
        summary: richSummary || toDisplayText(data).slice(0, 280),
        detailLines,
        leadGroups,
      };
    };
    const exactMatches = debateEvents
      .filter((row) => {
        const interaction = extractNetworkRelationFromEvent(row);
        return Boolean(
          interaction
          && interaction.source === selectedNetworkStep.source
          && interaction.target === selectedNetworkStep.target
          && interaction.relation === selectedNetworkStep.relation,
        );
      })
      .map(buildStepDetail);

    if (exactMatches.length > 0) return exactMatches;

    return debateEvents
      .filter((row) => isEventRelatedToNetworkStep(row, selectedNetworkStep))
      .slice(0, 8)
      .map(buildStepDetail);
  }, [debateEvents, selectedNetworkStep]);

  useEffect(() => {
    if (!selectedNetworkStep) return;
    const stillExists = agentNetworkData.steps.some((step) => step.id === selectedNetworkStep.id);
    if (!stillExists) {
      setSelectedNetworkStep(null);
    }
  }, [agentNetworkData.steps, selectedNetworkStep]);

  useEffect(() => {
    if (!selectedLeadFilter) return;
    const match = agentNetworkData.steps.find((step) =>
      (step.keyClues || []).some((item) => item.toLowerCase().includes(String(selectedLeadFilter.value || '').toLowerCase())),
    );
    if (match) {
      setSelectedNetworkStep(match);
    }
  }, [agentNetworkData.steps, selectedLeadFilter]);

  const selectedNetworkStepJourney = useMemo(() => {
    if (!selectedNetworkStep) {
      return {
        leadGroups: [] as Array<{ label: string; items: string[] }>,
        toolItems: [] as Array<{ id: string; timeText: string; summary: string; detail: string }>,
        conclusionItems: [] as Array<{ id: string; timeText: string; summary: string; detail: string }>,
      };
    }

    const scopedRows = debateEvents.filter((row) => isEventRelatedToNetworkStep(row, selectedNetworkStep));
    const commandRow = scopedRows.find((row) => row.kind === 'agent_command_issued');
    const leadGroups = commandRow ? extractLeadGroups(asRecord(commandRow.data)) : [];

    const toolItems = scopedRows
      .filter((row) =>
        row.kind === 'agent_tool_context_prepared'
        || row.kind === 'agent_tool_io'
        || row.kind === 'agent_tool_context_failed',
      )
      .slice(0, 8)
      .map((row) => {
        const built = buildDialogueMessage(row);
        return {
          id: row.id,
          timeText: row.timeText,
          summary: built?.summary || row.text,
          detail: built?.toolPayload?.responseText || built?.detail || row.text,
        };
      });

    const conclusionItems = scopedRows
      .filter((row) => row.kind === 'agent_command_feedback' || row.kind === 'agent_chat_message')
      .slice(0, 8)
      .map((row) => {
        const built = buildDialogueMessage(row);
        return {
          id: row.id,
          timeText: row.timeText,
          summary: built?.summary || row.text,
          detail: built?.detail || row.text,
        };
      });

    return { leadGroups, toolItems, conclusionItems };
  }, [debateEvents, selectedNetworkStep]);

  function isEventRelatedToNetworkStep(row: EventRecord, step: AgentNetworkStep | null): boolean {
    if (!step) return true;
    const data = asRecord(row.data);
    const agentName = firstTextValue(data, ['agent_name', 'agent']) || '';
    const interaction = extractNetworkRelationFromEvent(row);

    if (
      interaction
      && interaction.source === step.source
      && interaction.target === step.target
      && interaction.relation === step.relation
    ) {
      return true;
    }

    if (step.relation === 'command') {
      return agentName === step.target;
    }

    if (step.relation === 'feedback') {
      return agentName === step.source;
    }

    if (step.relation === 'reply') {
      return row.kind === 'agent_chat_message' && (agentName === step.source || agentName === step.target);
    }

    return false;
  }

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

  const renderEventFilters = (
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      {selectedLeadFilter ? (
        <Space wrap>
          <Tag color="gold">线索过滤中</Tag>
          <Tag>{selectedLeadFilter.label}</Tag>
          <Tag color="blue">{selectedLeadFilter.value}</Tag>
          <Button size="small" onClick={() => setSelectedLeadFilter(null)}>
            清除线索过滤
          </Button>
        </Space>
      ) : null}
      {selectedQualityFocus ? (
        <Space wrap>
          <Tag color="purple">质量过滤中</Tag>
          <Tag color="blue">{selectedQualityFocus.label}</Tag>
          <Tag color={selectedQualityFocus.statusFilter === 'all' ? 'processing' : 'default'}>
            {selectedQualityFocus.statusFilter === 'missing'
              ? '仅看缺失反馈'
              : selectedQualityFocus.statusFilter === 'inferred_without_tool'
                ? '仅看受限反馈'
                : '全部质量问题'}
          </Tag>
          {selectedQualityFocus.agentNames.map((agent) => (
            <Tag key={agent}>{agent}</Tag>
          ))}
          <Button
            size="small"
            type={selectedQualityFocus.statusFilter === 'all' ? 'primary' : 'default'}
            onClick={() => updateQualityFocusStatus('all')}
          >
            全部质量问题
          </Button>
          <Button
            size="small"
            type={selectedQualityFocus.statusFilter === 'inferred_without_tool' ? 'primary' : 'default'}
            onClick={() => updateQualityFocusStatus('inferred_without_tool')}
          >
            仅看受限反馈
          </Button>
          <Button
            size="small"
            type={selectedQualityFocus.statusFilter === 'missing' ? 'primary' : 'default'}
            onClick={() => updateQualityFocusStatus('missing')}
          >
            仅看缺失反馈
          </Button>
          <Button size="small" onClick={resetQualityFocus}>
            清除质量过滤
          </Button>
        </Space>
      ) : null}
      <DialogueFilterBar
        agents={eventFilterOptions.agents}
        phases={eventFilterOptions.phases}
        types={eventFilterOptions.types}
        selectedAgent={eventFilterAgent}
        selectedPhase={eventFilterPhase}
        selectedType={eventFilterType}
        searchText={eventSearchText}
        onAgentChange={setEventFilterAgent}
        onPhaseChange={setEventFilterPhase}
        onTypeChange={setEventFilterType}
        onSearchChange={setEventSearchText}
        onReset={() => {
          setEventFilterAgent('all');
          setEventFilterPhase('all');
          setEventFilterType('all');
          setEventSearchText('');
          setSelectedLeadFilter(null);
          setSelectedQualityFocus(null);
        }}
        filteredCount={filteredDialogueMessages.length}
        totalCount={dialogueMessages.length}
      />
    </Space>
  );

  const renderNetworkFocus = selectedNetworkStep ? (
    <Card className="module-card network-focus-card" size="small">
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
          <Space wrap>
            <Tag color="processing">链路过滤中</Tag>
            <Tag color="blue">{selectedNetworkStep.source}</Tag>
            <span>{'->'}</span>
            <Tag color="green">{selectedNetworkStep.target}</Tag>
            <Tag color="purple">
              {selectedNetworkStep.relation === 'command'
                ? '下发指令'
                : selectedNetworkStep.relation === 'feedback'
                  ? '反馈结果'
                  : '对话回复'} x{selectedNetworkStep.count}
            </Tag>
          </Space>
          <Button size="small" onClick={() => setSelectedNetworkStep(null)}>
            清除过滤
          </Button>
        </Space>
        <div className="network-step-detail-list">
          {selectedNetworkStepDetails.length > 0 ? (
            selectedNetworkStepDetails.map((item) => (
              <div key={item.id} className="network-step-detail-item">
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag>{item.kind}</Tag>
                    <Text type="secondary">{item.timeText}</Text>
                    <Text type="secondary">{item.agentName}</Text>
                  </Space>
                  <Text>{item.summary}</Text>
                  {item.detailLines && item.detailLines.length > 0 ? (
                    <div className="network-step-detail-lines">
                      {item.detailLines.map((line) => (
                        <Text key={`${item.id}_${line}`} type="secondary">
                          {line}
                        </Text>
                      ))}
                    </div>
                  ) : null}
                  {item.leadGroups && item.leadGroups.length > 0 ? (
                    <div className="network-step-leads">
                      {item.leadGroups.map((group) => (
                        <div key={`${item.id}_${group.label}`} className="network-step-lead-group">
                          <Text type="secondary" className="network-step-lead-label">
                            {group.label}
                          </Text>
                          <Space wrap>
                            {group.items.map((value) => (
                              <Tag key={`${item.id}_${group.label}_${value}`}>{value}</Tag>
                            ))}
                          </Space>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </Space>
              </div>
            ))
          ) : (
            <Text type="secondary">暂无与当前链路直接关联的明细事件。</Text>
          )}
        </div>
        <div className="network-journey-board">
          <div className="network-journey-column">
            <Text className="network-journey-title">1. 输入线索</Text>
            {selectedNetworkStepJourney.leadGroups.length > 0 ? (
              selectedNetworkStepJourney.leadGroups.map((group) => (
                <div key={`lead_${group.label}`} className="network-step-lead-group">
                  <Text type="secondary" className="network-step-lead-label">
                    {group.label}
                  </Text>
                  <Space wrap>
                    {group.items.map((value) => (
                      <Tag key={`lead_${group.label}_${value}`}>{value}</Tag>
                    ))}
                  </Space>
                </div>
              ))
            ) : (
              <Text type="secondary">当前链路没有显式结构化线索。</Text>
            )}
          </div>
          <div className="network-journey-column">
            <Text className="network-journey-title">2. 工具查询</Text>
            {selectedNetworkStepJourney.toolItems.length > 0 ? (
              selectedNetworkStepJourney.toolItems.map((item) => (
                <div key={item.id} className="network-journey-item">
                  <Text>{item.summary}</Text>
                  <Text type="secondary">{item.timeText}</Text>
                  <pre className="network-journey-pre">{item.detail}</pre>
                </div>
              ))
            ) : (
              <Text type="secondary">当前链路没有记录到独立工具查询事件。</Text>
            )}
          </div>
          <div className="network-journey-column">
            <Text className="network-journey-title">3. 输出结论</Text>
            {selectedNetworkStepJourney.conclusionItems.length > 0 ? (
              selectedNetworkStepJourney.conclusionItems.map((item) => (
                <div key={item.id} className="network-journey-item">
                  <Text>{item.summary}</Text>
                  <Text type="secondary">{item.timeText}</Text>
                  <pre className="network-journey-pre">{item.detail}</pre>
                </div>
              ))
            ) : (
              <Text type="secondary">当前链路还没有形成明确结论。</Text>
            )}
          </div>
        </div>
      </Space>
    </Card>
  ) : null;

  const renderDialogueStream = (
    <DialogueStream
      messages={filteredDialogueMessages}
      streamedMessageText={streamedMessageText}
      expandedDialogueIds={expandedDialogueIds}
      onToggleExpanded={(id) =>
        setExpandedDialogueIds((prev) => ({
          ...prev,
          [id]: !prev[id],
        }))
      }
    />
  );

  const renderAgentNetwork = (
    <AgentNetworkGraph
      nodes={agentNetworkData.nodes}
      edges={agentNetworkData.edges}
      steps={agentNetworkData.steps}
      selectedStepId={selectedNetworkStep?.id || null}
      onStepSelect={(step) => {
        setSelectedNetworkStep((prev) => (prev?.id === step.id ? null : step));
      }}
    />
  );

  const workspaceTabs = useMemo(
    () => [
      {
        key: 'overview',
        step: 0,
        label: '概览与启动',
        hint: '先录入故障信息，确认事件与会话是否已初始化。',
      },
      {
        key: 'asset',
        step: 1,
        label: '责任田',
        hint: '查看责任田映射是否命中，确认领域、聚合根、责任团队和责任人。',
      },
      {
        key: 'process',
        step: 2,
        label: '调查过程',
        hint: '查看主 Agent 调度过程、专家发言、工具调用和关键事件轨迹。',
      },
      {
        key: 'result',
        step: 3,
        label: '结论与行动',
        hint: '查看根因结论、证据链、修复建议、验证计划和最终报告。',
      },
    ],
    [],
  );

  const workspaceActive = workspaceTabs[activeStep] || workspaceTabs[0];
  const workspaceActiveKey = workspaceActive.key;

  const sessionQualitySummary = useMemo<SessionQualitySummary>(() => {
    const eventLog = Array.isArray((sessionDetail?.context || {}).event_log)
      ? ((sessionDetail?.context || {}).event_log as Array<Record<string, unknown>>)
      : [];
    const limitedAgents = new Set<string>();
    let limitedCount = 0;
    eventLog.forEach((row) => {
      const event = row && typeof row.event === 'object' && !Array.isArray(row.event)
        ? (row.event as Record<string, unknown>)
        : {};
      if (
        String(event.type || '').toLowerCase() === 'agent_command_feedback'
        && String(event.evidence_status || '').toLowerCase() === 'inferred_without_tool'
      ) {
        limitedCount += 1;
        const agentName = String(event.agent_name || event.agent || '').trim();
        if (agentName) limitedAgents.add(agentName);
      }
    });
    const riskFactors = Array.isArray(debateResult?.risk_assessment?.risk_factors)
      ? debateResult.risk_assessment.risk_factors.map((item) => String(item || '')).filter(Boolean)
      : [];
    const keyAgents = ['LogAgent', 'CodeAgent', 'DatabaseAgent', 'MetricsAgent'];
    const latestEvidenceStatus = new Map<string, string>();
    eventLog.forEach((row) => {
      const event = row && typeof row.event === 'object' && !Array.isArray(row.event)
        ? (row.event as Record<string, unknown>)
        : {};
      if (String(event.type || '').toLowerCase() !== 'agent_command_feedback') return;
      const agentName = String(event.agent_name || event.agent || '').trim();
      if (!agentName || !keyAgents.includes(agentName)) return;
      latestEvidenceStatus.set(agentName, String(event.evidence_status || '').toLowerCase().trim() || 'collected');
    });
    const evidenceCoverage = { ok: 0, degraded: 0, missing: 0 };
    keyAgents.forEach((agentName) => {
      const status = latestEvidenceStatus.get(agentName);
      if (status === 'missing') {
        evidenceCoverage.missing += 1;
      } else if (status === 'degraded' || status === 'inferred_without_tool') {
        evidenceCoverage.degraded += 1;
      } else if (status) {
        evidenceCoverage.ok += 1;
      }
    });
    return {
      limitedAnalysis: limitedCount > 0,
      limitedAgentNames: Array.from(limitedAgents),
      limitedCount,
      evidenceGap: riskFactors.some((item) => item.includes('关键证据不足')),
      riskFactors,
      evidenceCoverage,
    };
  }, [sessionDetail, debateResult]);

  const focusSessionQuality = (mode: 'limited' | 'evidence-gap') => {
    const agentNames =
      mode === 'limited'
        ? sessionQualitySummary.limitedAgentNames
        : Array.from(
            new Set([
              ...sessionQualitySummary.limitedAgentNames,
              ...(sessionQualitySummary.evidenceCoverage.missing > 0
                ? ['LogAgent', 'CodeAgent', 'DatabaseAgent', 'MetricsAgent']
                : []),
            ]),
          ).filter(Boolean);
    setSelectedLeadFilter(null);
    setSelectedNetworkStep(null);
    setSelectedQualityFocus({
      label: mode === 'limited' ? '受限分析' : '关键证据不足',
      agentNames,
      eventType: 'agent_command_feedback',
      statusFilter: mode === 'limited' ? 'inferred_without_tool' : 'all',
    });
    setActiveStep(2);
    setActiveProcessTab('dialogue');
    resetDialogueFilters();
    setEventFilterType('agent_command_feedback');
    window.requestAnimationFrame(() => {
      if (window.scrollY > 220) {
        scrollToWorkspaceTop();
      }
    });
  };

  const switchToStep = async (nextStep: number) => {
    if (nextStep > 0 && !incidentId) {
      message.warning('请先创建故障并初始化会话');
      return;
    }
    if (nextStep !== 2) {
      resetProcessFocus();
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
    window.requestAnimationFrame(() => {
      if (window.scrollY > 220) {
        scrollToWorkspaceTop();
      }
    });
  };

  const scrollToWorkspaceTop = useCallback((smooth: boolean = true) => {
    const shell = navShellRef.current;
    if (!shell) return;
    const stickyOffset = 84;
    const top = Math.max(0, window.scrollY + shell.getBoundingClientRect().top - stickyOffset);
    window.scrollTo({ top, behavior: smooth ? 'smooth' : 'auto' });
  }, []);

  useEffect(() => {
    if (activeStep !== 2 && selectedNetworkStep) {
      setSelectedNetworkStep(null);
    }
  }, [activeStep, selectedNetworkStep]);

  useEffect(() => {
    if (activeProcessTab !== 'network' && selectedNetworkStep) {
      setSelectedNetworkStep(null);
    }
  }, [activeProcessTab, selectedNetworkStep]);

  const roundCollapseItems = (sessionDetail?.rounds || [])
    .filter((round) => {
      if (selectedQualityFocus && selectedQualityFocus.agentNames.length > 0) {
        if (!selectedQualityFocus.agentNames.includes(round.agent_name)) {
          return false;
        }
      }
      if (!selectedNetworkStep) return true;
      if (selectedNetworkStep.relation === 'command') {
        return round.agent_name === selectedNetworkStep.target;
      }
      if (selectedNetworkStep.relation === 'feedback') {
        return round.agent_name === selectedNetworkStep.source;
      }
      return round.agent_name === selectedNetworkStep.source || round.agent_name === selectedNetworkStep.target;
    })
    .map((round) => ({
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
      filteredDebateEvents.slice(0, 120).map((row) => ({
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

  const humanReviewState = useMemo(() => {
    const context = asRecord(sessionDetail?.context);
    const review = asRecord(context.human_review);
    const status = String(review.status || '').trim();
    const reason = String(review.reason || '').trim();
    if (!status && !reason) return null;
    return {
      status,
      reason,
      resumeFromStep: String(review.resume_from_step || '').trim(),
      approver: String(review.approver || '').trim(),
      comment: String(review.comment || review.rejection_reason || '').trim(),
    };
  }, [sessionDetail]);

  const investigationLeads = useMemo(() => extractInvestigationLeadsView(sessionDetail), [sessionDetail]);
  const highlightedLeadKeys = useMemo(() => {
    if (selectedLeadFilter) return [`${selectedLeadFilter.label}:${selectedLeadFilter.value}`];
    if (!selectedNetworkStep) return [];
    const step = agentNetworkData.steps.find((item) => item.id === selectedNetworkStep.id);
    if (!step) return [];
    const relatedRows = debateEvents.filter((row) => isEventRelatedToNetworkStep(row, step));
    const groups = relatedRows
      .filter((row) => row.kind === 'agent_command_issued')
      .flatMap((row) => extractLeadGroups(asRecord(row.data)));
    return Array.from(new Set(toLeadKeys(groups)));
  }, [agentNetworkData.steps, debateEvents, selectedLeadFilter, selectedNetworkStep]);

  const mainAgentConclusion = useMemo(() => {
    if (debateResult?.root_cause) {
      const finalConclusion = buildConclusionCandidate(
        String(debateResult.root_cause || ''),
        formatBeijingDateTime(debateResult.created_at),
        '最终裁决',
      );
      if (finalConclusion) return finalConclusion;
    }
    for (const row of eventRecords) {
      if (row.kind !== 'agent_chat_message') continue;
      const data = asRecord(row.data);
      const agent = firstTextValue(data, ['agent_name', 'agent']);
      if (agent !== 'JudgeAgent') continue;
      const messageText = firstTextValue(data, ['conclusion', 'message']);
      const candidate = buildConclusionCandidate(messageText, row.timeText, 'JudgeAgent');
      if (candidate) return candidate;
    }
    for (const row of eventRecords) {
      if (row.kind !== 'agent_chat_message') continue;
      const data = asRecord(row.data);
      const agent = firstTextValue(data, ['agent_name', 'agent']);
      if (agent !== 'ProblemAnalysisAgent') continue;
      const messageText = firstTextValue(data, ['conclusion', 'message']);
      const candidate = buildConclusionCandidate(messageText, row.timeText, 'ProblemAnalysisAgent');
      if (candidate) return candidate;
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
    const candidates = Array.isArray(debateResult.root_cause_candidates) ? debateResult.root_cause_candidates : [];
    if (candidates.length > 0) {
      const lines = candidates.slice(0, 5).map((item, index) => {
        const row = asRecord(item);
        const summary = firstTextValue(row, ['summary']) || '-';
        const agent = firstTextValue(row, ['source_agent']) || '-';
        const confidence = Number(row.confidence || 0);
        const interval = Array.isArray(row.confidence_interval) ? row.confidence_interval : [];
        const low = Number(interval[0] || 0);
        const high = Number(interval[1] || 0);
        return `${index + 1}. ${summary}\n来源：${agent}，置信度：${(confidence * 100).toFixed(1)}%，区间：[${(low * 100).toFixed(1)}%, ${(high * 100).toFixed(1)}%]`;
      });
      cards.push({ title: 'Top-K 根因候选', body: lines.join('\n') });
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

  const sessionStatus = String(sessionDetail?.status || '').toLowerCase();

  const fillDemoIncident = () => {
    setIncidentForm((prev) => ({
      ...prev,
      title: '/api/v1/orders 接口 502 + CPU 飙高',
      description: '网关 502，order-service CPU 飙高，连接池打满',
      severity: 'high',
      service_name: 'order-service',
      log_content: [
        '2026-02-20T14:01:38.124+08:00 ERROR gateway upstream timeout status=502 uri=POST /api/v1/orders costMs=30211',
        '2026-02-20T14:01:38.095+08:00 ERROR order-service HikariPool-1 - Connection is not available, request timed out after 30000ms',
        '2026-02-20T14:02:01.122+08:00 WARN mysql lock wait timeout exceeded table=t_order_item',
      ].join('\n'),
    }));
    setLogUploadMeta(null);
    message.success('已填充示例故障，可直接启动分析');
  };

  const handleLogFileUpload: UploadProps['beforeUpload'] = async (file) => {
    try {
      if (file.size > 5 * 1024 * 1024) {
        message.error('日志文件过大，请上传 5MB 以内文件');
        return Upload.LIST_IGNORE;
      }
      const text = await file.text();
      if (!text.trim()) {
        message.warning('上传文件内容为空');
        return Upload.LIST_IGNORE;
      }
      const maxChars = 50000;
      const clipped = text.length > maxChars ? text.slice(0, maxChars) : text;
      const lineCount = clipped.split(/\r?\n/).length;
      if (text.length > maxChars) {
        message.warning(`日志内容超过 ${maxChars} 字符，已自动截断`);
      }
      setIncidentForm((prev) => {
        const merged = prev.log_content
          ? `${prev.log_content}\n\n# 上传文件: ${file.name}\n${clipped}`
          : clipped;
        return { ...prev, log_content: merged };
      });
      setLogUploadMeta({ name: file.name, size: file.size, lines: lineCount });
      message.success(`已加载日志文件：${file.name}`);
    } catch (error: any) {
      message.error(error?.message || '读取日志文件失败');
    }
    return Upload.LIST_IGNORE;
  };

  return (
    <div className="incident-page">
      <div ref={navShellRef} className="incident-section-nav-shell">
        <div className="incident-section-nav">
          <Tabs
            className="incident-workspace-tabs"
            activeKey={workspaceActiveKey}
            onChange={(key) => {
              const target = workspaceTabs.find((item) => item.key === key);
              if (target) {
                void switchToStep(target.step);
              }
            }}
            items={workspaceTabs.map((item) => ({
              key: item.key,
              label: item.label,
              children: null,
            }))}
          />
          <Text type="secondary">{workspaceActive.hint}</Text>
          <Space wrap size={6} className="incident-session-quality-pills">
            {typeof debateResult?.confidence === 'number' ? (
              <Tag color="geekblue">{`置信度 ${(debateResult.confidence * 100).toFixed(1)}%`}</Tag>
            ) : null}
            {sessionQualitySummary.limitedAnalysis ? (
              <Tag color="gold">{`受限分析 ${sessionQualitySummary.limitedCount} 次`}</Tag>
            ) : null}
            {sessionQualitySummary.evidenceGap ? <Tag color="volcano">关键证据不足</Tag> : null}
          </Space>
        </div>
      </div>

      <div style={{ marginTop: 24 }}>
        {bootstrapping && (
          <Card className="module-card" style={{ minHeight: 180 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 132 }}>
              <Space direction="vertical" align="center" size="middle">
                <Spin />
                <Text type="secondary">正在加载会话与报告数据...</Text>
              </Space>
            </div>
          </Card>
        )}
        {!bootstrapping && (
          <>
        {activeStep === 0 && (
          <IncidentOverviewPanel
            incidentForm={incidentForm}
            running={running}
            loading={loading}
            incidentId={incidentId}
            sessionId={sessionId}
            debateMaxRounds={debateMaxRounds}
            executionMode={executionMode}
            logUploadMeta={logUploadMeta}
            onFillDemoIncident={fillDemoIncident}
            onChangeIncidentForm={(patch) => setIncidentForm((s) => ({ ...s, ...patch }))}
            onDebateMaxRoundsChange={setDebateMaxRounds}
            onExecutionModeChange={setExecutionMode}
            onLogFileUpload={handleLogFileUpload}
            onClearLogUploadMeta={() => setLogUploadMeta(null)}
            onStartAnalysis={() => void startAnalysisFromInput()}
            onCreateIncidentAndSession={() => void createIncidentAndSession()}
            onInitSessionForExistingIncident={() => void initSessionForExistingIncident()}
          />
        )}

        {activeStep === 1 && (
          <AssetMappingPanel
            mappingItems={mappingItems}
            mappingEmptyHint={mappingEmptyHint}
            investigationLeads={investigationLeads}
            selectedLeadKey={selectedLeadFilter ? `${selectedLeadFilter.label}:${selectedLeadFilter.value}` : null}
            highlightedLeadKeys={highlightedLeadKeys}
            onLeadSelect={(lead) => {
              setSelectedQualityFocus(null);
              setSelectedLeadFilter(lead);
              if (lead) {
                setActiveStep(2);
                setActiveProcessTab('network');
                setSelectedNetworkStep(null);
                window.requestAnimationFrame(() => {
                  if (window.scrollY > 220) {
                    scrollToWorkspaceTop();
                  }
                });
              }
            }}
          />
        )}

        {activeStep === 2 && (
          <DebateProcessPanel
            incidentId={incidentId}
            sessionId={sessionId}
            running={running}
            loading={loading}
            sessionStatus={String(sessionDetail?.status || '')}
            debateMaxRounds={debateMaxRounds}
            onStartAnalysis={startAnalysisFromInput}
            onCancel={() => sendWsControl('cancel')}
            onResume={() => sendWsControl('resume')}
            onApproveReview={() => sendWsControl('approve')}
            onRejectReview={() => sendWsControl('reject')}
            onRetryFailed={retryFailedAgents}
            activeTabKey={activeProcessTab}
            onTabChange={(key) => {
              setActiveProcessTab(key);
            }}
            eventFiltersNode={renderEventFilters}
            networkFocusNode={renderNetworkFocus}
            dialogueNode={renderDialogueStream}
            agentNetworkNode={renderAgentNetwork}
            roundCollapseItems={roundCollapseItems}
            timelineItems={timelineItems}
            eventStats={eventStats}
            humanReview={humanReviewState}
          />
        )}

        {activeStep === 3 && (
          <DebateResultPanel
            mainAgentConclusion={mainAgentConclusion}
            debateResult={debateResult}
            sessionStatus={sessionStatus}
            sessionError={extractSessionError(sessionDetail)}
            debateSummaryCards={debateSummaryCards}
            reportResult={reportResult}
            reportSections={reportSections}
            reportLoading={reportLoading}
            incidentId={incidentId}
            sessionId={sessionId}
            incidentTitle={incidentForm.title}
            serviceName={incidentForm.service_name}
            debateConfidence={debateResult?.confidence}
            sessionQualitySummary={sessionQualitySummary}
            onFocusLimitedAnalysis={() => focusSessionQuality('limited')}
            onFocusEvidenceGap={() => focusSessionQuality('evidence-gap')}
            onRegenerateReport={regenerateReport}
          />
        )}
          </>
        )}
      </div>
    </div>
  );
};

export default IncidentPage;
