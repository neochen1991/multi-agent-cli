import React, { useEffect, useMemo, useRef, useState } from 'react';
import { message } from 'antd';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  assetApi,
  debateApi,
  incidentApi,
  lineageApi,
  reportApi,
  settingsApi,
  type AssetFusion,
  type DebateDetail,
  type DebateResult,
  type Incident,
  type LineageRecord,
  type Report,
  type ToolAuditResponse,
} from '@/services/api';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { formatBeijingDateTime } from '@/utils/dateTime';
import { asRecord, compactText, isActiveStatus, pickToneByStatus } from '@/v2/utils';

type IncidentFormState = {
  title: string;
  description: string;
  severity: string;
  service_name: string;
  environment: string;
  log_content: string;
};

const normalizeText = (value: unknown): string => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const firstFilled = (...values: unknown[]): string => {
  for (const value of values) {
    const text = normalizeText(value);
    if (text) return text;
  }
  return '';
};

const summarizeLineage = (row: LineageRecord): string => {
  const payload = asRecord(row.payload);
  const outputSummary = asRecord(row.output_summary);
  const inputSummary = asRecord(row.input_summary);
  return firstFilled(
    outputSummary.summary,
    outputSummary.conclusion,
    payload.summary,
    payload.chat_message,
    payload.message,
    payload.conclusion,
    payload.reason,
    inputSummary.summary,
    inputSummary.command,
    row.event_type,
  ) || '暂无摘要';
};

const isConclusionBearingEvent = (row: LineageRecord): boolean => {
  const eventType = String(row.event_type || '').toLowerCase();
  return ['agent_round', 'agent_chat_message', 'agent_feedback', 'agent_reply'].includes(eventType);
};

const IncidentV2: React.FC = () => {
  const navigate = useNavigate();
  const { incidentId: routeIncidentId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [sessionDetail, setSessionDetail] = useState<DebateDetail | null>(null);
  const [debateResult, setDebateResult] = useState<DebateResult | null>(null);
  const [reportResult, setReportResult] = useState<Report | null>(null);
  const [fusion, setFusion] = useState<AssetFusion | null>(null);
  const [lineage, setLineage] = useState<LineageRecord[]>([]);
  const [toolAudit, setToolAudit] = useState<ToolAuditResponse | null>(null);
  const [debateMaxRounds, setDebateMaxRounds] = useState<number>(1);
  const [logUploadMeta, setLogUploadMeta] = useState<{ name: string; size: number; lines: number } | null>(null);
  const [processTab, setProcessTab] = useState<'dialogue' | 'tools' | 'rounds' | 'events'>('dialogue');
  const [runRequestedAt, setRunRequestedAt] = useState<string | null>(null);
  const [lastHydratedAt, setLastHydratedAt] = useState<string | null>(null);
  const [incidentForm, setIncidentForm] = useState<IncidentFormState>({
    title: '',
    description: '',
    severity: 'high',
    service_name: '',
    environment: 'production',
    log_content: '',
  });
  const autoStartedRef = useRef<Set<string>>(new Set());

  const sessionId = String(searchParams.get('session_id') || incident?.debate_session_id || '').trim();
  const rawExecutionMode = String(searchParams.get('mode') || 'standard').trim().toLowerCase();
  const executionMode =
    rawExecutionMode === 'quick' || rawExecutionMode === 'background' || rawExecutionMode === 'standard'
      ? rawExecutionMode
      : rawExecutionMode === 'async'
        ? 'background'
        : 'standard';
  const autoStart = searchParams.get('auto_start') === '1';
  const reviewState = asRecord(asRecord(sessionDetail?.context).human_review);
  const reviewStatus = String(reviewState.status || '').toLowerCase();

  const setModeInQuery = (mode: string) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('mode', mode);
      return next;
    });
  };

  const hydrate = async (incidentId: string, sid?: string) => {
    setLoading(true);
    try {
      const incidentRes = await incidentApi.get(incidentId);
      setIncident(incidentRes);
      const effectiveSessionId = String(sid || incidentRes.debate_session_id || '').trim();
      if (!effectiveSessionId) {
        setSessionDetail(null);
        setDebateResult(null);
        setReportResult(null);
        setFusion(null);
        setLineage([]);
        setToolAudit(null);
        return;
      }
      const detail = await debateApi.get(effectiveSessionId);
      const shouldFetchResult = !isActiveStatus(detail.status) || String(detail.current_phase || '').toLowerCase() === 'judge';
      const shouldFetchReport = ['resolved', 'completed', 'closed'].includes(String(detail.status || '').toLowerCase());
      const [result, report, fusionRes, lineageRes, toolAuditRes] = await Promise.all([
        shouldFetchResult ? debateApi.getResult(effectiveSessionId).catch(() => null) : Promise.resolve(null),
        shouldFetchReport ? reportApi.get(incidentId).catch(() => null) : Promise.resolve(null),
        assetApi.fusion(incidentId).catch(() => null),
        lineageApi.get(effectiveSessionId, 200).catch(() => null),
        settingsApi.getToolAudit(effectiveSessionId).catch(() => null),
      ]);
      setSessionDetail(detail);
      setDebateResult(result);
      setReportResult(report);
      setFusion(fusionRes);
      setLineage(lineageRes?.items || []);
      setToolAudit(toolAuditRes);
      setLastHydratedAt(new Date().toISOString());
      const detailStatus = String(detail.status || '').toLowerCase();
      if (['resolved', 'completed', 'closed', 'failed', 'cancelled'].includes(detailStatus)) {
        setRunRequestedAt(null);
      }
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载故障分析详情失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!routeIncidentId) return;
    void hydrate(routeIncidentId, sessionId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeIncidentId, sessionId]);

  useEffect(() => {
    if (!routeIncidentId || !sessionId || !autoStart || autoStartedRef.current.has(sessionId)) return;
    autoStartedRef.current.add(sessionId);
    setRunRequestedAt(new Date().toISOString());
    setActionLoading(true);
    debateApi.executeBackground(sessionId)
      .then(() => {
        message.success('已启动实时分析');
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          next.delete('auto_start');
          return next;
        }, { replace: true });
        return hydrate(routeIncidentId, sessionId);
      })
      .catch((error: any) => {
        setRunRequestedAt(null);
        message.error(error?.response?.data?.detail || error?.message || '启动分析失败');
      })
      .finally(() => setActionLoading(false));
  }, [autoStart, executionMode, hydrate, routeIncidentId, searchParams, sessionId, setSearchParams]);

  useEffect(() => {
    if (!routeIncidentId || !sessionId || !isActiveStatus(sessionDetail?.status)) return undefined;
    const timer = window.setInterval(() => {
      void hydrate(routeIncidentId, sessionId);
    }, 8000);
    return () => window.clearInterval(timer);
  }, [routeIncidentId, sessionId, sessionDetail?.status]);

  const createIncidentAndStart = async () => {
    if (!incidentForm.title.trim()) {
      message.warning('请先输入故障标题');
      return;
    }
    setActionLoading(true);
    try {
      const created = await incidentApi.create({
        title: incidentForm.title.trim(),
        description: incidentForm.description.trim(),
        severity: incidentForm.severity,
        service_name: incidentForm.service_name.trim(),
        environment: incidentForm.environment.trim(),
        log_content: incidentForm.log_content.trim(),
      });
      const session = await debateApi.createSession(created.id, {
        maxRounds: debateMaxRounds,
        mode: executionMode as 'standard' | 'quick' | 'background',
      });
      navigate(`/v2/incident/${created.id}?session_id=${session.id}&auto_start=1&mode=${executionMode}`);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '创建分析失败');
    } finally {
      setActionLoading(false);
    }
  };

  const initSessionForExistingIncident = async (): Promise<string | null> => {
    if (!incident?.id) {
      message.warning('请先创建或打开一个 incident');
      return null;
    }
    setActionLoading(true);
    try {
      const session = await debateApi.createSession(incident.id, {
        maxRounds: debateMaxRounds,
        mode: executionMode as 'standard' | 'quick' | 'background',
      });
      const sid = String(session.id || '').trim();
      if (!sid) throw new Error('初始化会话失败：session_id 为空');
      navigate(`/v2/incident/${incident.id}?session_id=${sid}&mode=${executionMode}`);
      message.success(`会话已初始化：${sid}`);
      return sid;
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '初始化会话失败');
      return null;
    } finally {
      setActionLoading(false);
    }
  };

  const startAnalysis = async () => {
    setRunRequestedAt(new Date().toISOString());
    setActionLoading(true);
    try {
      let sid = sessionId;
      if (!sid) {
        sid = routeIncidentId ? (await initSessionForExistingIncident()) || '' : '';
      }
      if (!sid) {
        if (!routeIncidentId) {
          await createIncidentAndStart();
        }
        return;
      }
      await debateApi.executeBackground(sid);
      message.success('已启动实时分析');
      if (routeIncidentId) {
        await hydrate(routeIncidentId, sid);
      }
    } catch (error: any) {
      setRunRequestedAt(null);
      message.error(error?.response?.data?.detail || error?.message || '启动分析失败');
    } finally {
      setActionLoading(false);
    }
  };

  const sendSessionControl = async (action: 'cancel' | 'resume' | 'approve' | 'reject') => {
    if (!sessionId) {
      message.warning('当前没有可操作的会话');
      return;
    }
    setActionLoading(true);
    try {
      if (action === 'cancel') {
        await debateApi.cancel(sessionId);
        message.success('会话已取消');
        setRunRequestedAt(null);
      } else if (action === 'approve') {
        await debateApi.approveHumanReview(sessionId);
        message.success('已批准，等待恢复执行');
      } else if (action === 'reject') {
        await debateApi.rejectHumanReview(sessionId);
        message.success('已驳回，本次分析结束');
        setRunRequestedAt(null);
      } else {
        setRunRequestedAt(new Date().toISOString());
        await debateApi.executeBackground(sessionId);
        message.success('已恢复分析');
      }
      if (routeIncidentId) await hydrate(routeIncidentId, sessionId);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '会话控制失败');
    } finally {
      setActionLoading(false);
    }
  };

  const retryFailedAgents = async () => {
    if (!sessionId) {
      message.warning('当前没有会话可重试');
      return;
    }
    setActionLoading(true);
    try {
      await debateApi.executeBackground(sessionId, { retryFailedOnly: true });
      message.success('已请求仅重试失败 Agent');
      if (routeIncidentId) await hydrate(routeIncidentId, sessionId);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '失败 Agent 重试失败');
    } finally {
      setActionLoading(false);
    }
  };

  const fillDemoIncident = () => {
    if (incident) return;
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
    message.success('已填充示例故障');
  };

  const handleLogFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 5 * 1024 * 1024) {
        message.error('日志文件过大，请上传 5MB 以内文件');
        return;
      }
      const text = await file.text();
      if (!text.trim()) {
        message.warning('上传文件内容为空');
        return;
      }
      const maxChars = 50000;
      const clipped = text.length > maxChars ? text.slice(0, maxChars) : text;
      const lineCount = clipped.split(/\r?\n/).length;
      if (text.length > maxChars) {
        message.warning(`日志超过 ${maxChars} 字符，已自动截断`);
      }
      setIncidentForm((prev) => ({
        ...prev,
        log_content: prev.log_content ? `${prev.log_content}\n\n# 上传文件: ${file.name}\n${clipped}` : clipped,
      }));
      setLogUploadMeta({ name: file.name, size: file.size, lines: lineCount });
      message.success(`已加载日志文件：${file.name}`);
    } catch (error: any) {
      message.error(error?.message || '读取日志文件失败');
    } finally {
      event.target.value = '';
    }
  };

  const regenerateReport = async () => {
    if (!incident?.id) return;
    setReportLoading(true);
    try {
      const report = await reportApi.regenerate(incident.id);
      setReportResult(report);
      message.success('报告已重新生成');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '报告生成失败');
    } finally {
      setReportLoading(false);
    }
  };

  const conclusionText = useMemo(() => {
    if (debateResult?.root_cause) return debateResult.root_cause;
    const judge = lineage.find(
      (row) => String(row.agent_name || '').toLowerCase() === 'judgeagent' && isConclusionBearingEvent(row),
    );
    if (judge) return summarizeLineage(judge);
    return '';
  }, [debateResult, lineage]);

  const confidenceText = useMemo(() => {
    if (typeof debateResult?.confidence === 'number') return `${(debateResult.confidence * 100).toFixed(1)}%`;
    return '--';
  }, [debateResult]);

  const phaseText = firstFilled(sessionDetail?.current_phase, sessionDetail?.status, 'waiting');
  const sessionStatusText = String(sessionDetail?.status || '').toLowerCase();
  const runningState =
    actionLoading ||
    autoStart ||
    Boolean(runRequestedAt) ||
    isActiveStatus(sessionDetail?.status);
  const runningStageText = firstFilled(sessionDetail?.current_phase, sessionDetail?.status, 'dispatching');
  const runningHint = runningState
    ? `会话 ${sessionId || '--'} 正在执行 ${runningStageText}，页面每 8 秒自动刷新，过程数据会持续追加。`
    : '';

  const assetRows = useMemo(() => {
    const context = asRecord(sessionDetail?.context);
    const matched = asRecord(context.locate_result);
    const runtimeAssets = Array.isArray(fusion?.runtime_assets) ? fusion.runtime_assets : [];
    const resource = runtimeAssets[0] && typeof runtimeAssets[0] === 'object' ? asRecord(runtimeAssets[0]) : {};
    return [
      { label: '领域', value: firstFilled(matched.domain, resource.domain) || '--' },
      { label: '聚合根', value: firstFilled(matched.aggregate, resource.aggregate) || '--' },
      { label: 'Owner', value: firstFilled(matched.owner_team, resource.owner_team, resource.owner) || '--' },
      { label: 'API', value: firstFilled(asRecord(matched.matched_endpoint).path, incident?.service_name) || '--' },
      { label: '表', value: Array.isArray(matched.db_tables) ? matched.db_tables.join(', ') : firstFilled(resource.tables) || '--' },
    ];
  }, [fusion, incident?.service_name, sessionDetail?.context]);

  const candidateRows = Array.isArray(debateResult?.root_cause_candidates) ? debateResult?.root_cause_candidates || [] : [];
  const evidenceRows = Array.isArray(debateResult?.evidence_chain) ? debateResult?.evidence_chain || [] : [];

  const processRows = useMemo(() => {
    const meaningful = lineage.filter((row) => {
      const eventType = String(row.event_type || '').toLowerCase();
      return !['llm_http_request', 'llm_http_response', 'llm_stream_delta', 'llm_call_started', 'llm_call_completed'].includes(eventType);
    });
    return meaningful.slice(0, 60);
  }, [lineage]);

  const toolRows = useMemo(() => {
    const auditItems = toolAudit?.items || [];
    if (auditItems.length > 0) return auditItems;
    return lineage.filter((row) => {
      const text = `${row.kind || ''} ${row.event_type || ''}`.toLowerCase();
      return text.includes('tool');
    });
  }, [lineage, toolAudit?.items]);

  const graphAgents = useMemo(() => {
    const set = new Set<string>();
    lineage.forEach((row) => {
      const name = String(row.agent_name || '').trim();
      if (name) set.add(name);
    });
    return Array.from(set);
  }, [lineage]);

  const roundRows = sessionDetail?.rounds || [];
  const reportPreview = useMemo(() => {
    const content = String(reportResult?.content || '').trim();
    if (!content) return [];
    return content.split(/\n+/).map((line) => line.trim()).filter(Boolean).slice(0, 8);
  }, [reportResult?.content]);

  return (
    <>
      <PageHeader
        title="故障分析工作台"
        desc="保持 Figma 版式，但区块内容全部来自真实接口。结论区优先，过程、责任田、证据和报告同屏。"
        actions={
          <>
            <button className="btn" onClick={() => void regenerateReport()} disabled={!incident?.id || reportLoading}>{reportLoading ? '生成中...' : '重新生成报告'}</button>
            <button className="btn" onClick={() => routeIncidentId ? void hydrate(routeIncidentId, sessionId) : void createIncidentAndStart()} disabled={loading || actionLoading}>{routeIncidentId ? '刷新调查' : '创建事件'}</button>
            <button className="btn primary" onClick={() => void startAnalysis()} disabled={loading || actionLoading || runningState}>{runningState ? '分析进行中' : actionLoading ? '执行中...' : '启动分析'}</button>
          </>
        }
      />

      {runningState ? (
        <section className="incident-live-banner" role="status" aria-live="polite">
          <div className="incident-live-main">
            <div className="incident-live-pill">
              <span className="incident-live-dot" />
              实时分析进行中
            </div>
            <strong>{runningHint}</strong>
            <p>可在「辩论过程」查看主 Agent 指令、专家反馈与工具审计；分析完成后会自动显示结论与报告。</p>
          </div>
          <div className="incident-live-meta">
            <div><span>Session</span><strong>{sessionId || '--'}</strong></div>
            <div><span>状态</span><strong>{sessionStatusText || 'running'}</strong></div>
            <div><span>阶段</span><strong>{runningStageText}</strong></div>
            <div><span>更新时间</span><strong>{lastHydratedAt ? formatBeijingDateTime(lastHydratedAt) : '等待首轮刷新'}</strong></div>
          </div>
        </section>
      ) : null}

      <section className="conclusion-band">
        <div className="conclusion-hero">
          <div className="conclusion-kicker">Primary conclusion</div>
          <h3>{conclusionText || '当前还没有有效结论，等待专家 Agent 收敛或报告生成。'}</h3>
          <p>{incident ? compactText(incident.description || incident.title || '暂无事件描述', 180) : '先在左侧输入真实故障信息并启动分析。'}</p>
          <div className="conclusion-meta">
            <div className="conclusion-stat"><div className="meta-label">Confidence</div><strong>{confidenceText}</strong></div>
            <div className="conclusion-stat"><div className="meta-label">Current stage</div><strong>{phaseText}</strong></div>
            <div className="conclusion-stat"><div className="meta-label">Human review</div><strong>{String(asRecord(sessionDetail?.context).human_review ? 'Required' : 'Not requested')}</strong></div>
            <div className="conclusion-stat"><div className="meta-label">Primary owner</div><strong>{assetRows.find((row) => row.label === 'Owner')?.value || '--'}</strong></div>
          </div>
        </div>
        <div className="conclusion-side">
          <Panel title="行动建议" subtitle="来自真实报告或修复建议；没有数据时显示空态。" extra={<Badge tone={debateResult?.fix_recommendation ? 'amber' : 'brand'}>{debateResult?.fix_recommendation ? 'Actionable' : 'Pending'}</Badge>}>
            <div className="status-grid scroll-region compact-scroll">
              {debateResult?.fix_recommendation ? (
                <>
                  <div className="status-row"><div><div className="status-name">摘要</div><div className="status-meta">{firstFilled(debateResult.fix_recommendation.summary, '暂无摘要')}</div></div></div>
                  <div className="status-row"><div><div className="status-name">代码变更</div><div className="status-meta">{debateResult.fix_recommendation.code_changes_required ? '需要' : '不需要 / 未说明'}</div></div></div>
                  <div className="status-row"><div><div className="status-name">回滚建议</div><div className="status-meta">{debateResult.fix_recommendation.rollback_recommended ? '建议准备回滚路径' : '未要求回滚'}</div></div></div>
                </>
              ) : <div className="empty-note">报告尚未生成修复建议。</div>}
            </div>
          </Panel>
        </div>
      </section>

      <section className="workbench-grid">
        <div className="stack">
          <Panel title="事件输入" subtitle="直接创建真实 incident，不再展示示例文本。">
            <div className="stack">
              <div className="field"><label>事件标题</label><input className="v2-input" value={incident?.title || incidentForm.title} onChange={(e) => setIncidentForm((prev) => ({ ...prev, title: e.target.value }))} placeholder="例如：/orders 接口 502，CPU 飙升" disabled={Boolean(incident)} /></div>
              <div className="field"><label>服务名称</label><input className="v2-input" value={incident?.service_name || incidentForm.service_name} onChange={(e) => setIncidentForm((prev) => ({ ...prev, service_name: e.target.value }))} placeholder="order-service" disabled={Boolean(incident)} /></div>
              <div className="field"><label>严重级别</label><select className="v2-input" value={incident?.severity || incidentForm.severity} onChange={(e) => setIncidentForm((prev) => ({ ...prev, severity: e.target.value }))} disabled={Boolean(incident)}><option value="critical">critical</option><option value="high">high</option><option value="medium">medium</option><option value="low">low</option></select></div>
              <div className="field"><label>会话模式</label><div className="pill-row"><button className={`pill${executionMode === 'standard' ? ' active' : ''}`} onClick={() => setModeInQuery('standard')}>Standard（完整分析）</button><button className={`pill${executionMode === 'quick' ? ' active' : ''}`} onClick={() => setModeInQuery('quick')}>Quick（快速收敛）</button><button className={`pill${executionMode === 'background' ? ' active' : ''}`} onClick={() => setModeInQuery('background')}>Background（后台）</button></div><div className="status-meta">Standard 面向能力更强的模型服务，允许更完整的多轮分析；Quick 会压缩专家数量和上下文，优先避免弱模型超时；Background 表示后台执行，不额外提升分析深度。</div></div>
              <div className="field"><label>辩论轮次</label><input className="v2-input" type="number" min={1} max={8} value={debateMaxRounds} onChange={(e) => setDebateMaxRounds(Math.max(1, Math.min(8, Number(e.target.value || 1))))} disabled={Boolean(incident && sessionId)} /></div>
              <div className="field"><label>日志摘要</label><textarea className="v2-textarea" value={incidentForm.log_content} onChange={(e) => setIncidentForm((prev) => ({ ...prev, log_content: e.target.value }))} placeholder="粘贴真实报错日志、堆栈或现象摘要" disabled={Boolean(incident)} /></div>
              {!incident ? (
                <div className="field">
                  <label>上传日志文件</label>
                  <label className="upload-dropzone">
                    <span>点击上传 .log/.txt（最大 5MB）</span>
                    <input type="file" accept=".log,.txt,.out,.json,text/plain" onChange={(e) => void handleLogFileUpload(e)} />
                  </label>
                  {logUploadMeta ? (
                    <div className="status-meta">
                      {`已加载 ${logUploadMeta.name} · ${(logUploadMeta.size / 1024).toFixed(1)}KB · ${logUploadMeta.lines} 行`}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {!incident ? (
                <div className="toolbar">
                  <button className="btn" onClick={fillDemoIncident}>填充示例故障</button>
                  <button className="btn" onClick={() => setLogUploadMeta(null)} disabled={!logUploadMeta}>清除上传信息</button>
                </div>
              ) : null}
            </div>
          </Panel>
          <Panel title="会话控制" subtitle="显示真实 session 状态、轮次和工具审计。">
            <div className="status-grid">
              <div className="status-row"><div><div className="status-name">Incident</div><div className="status-meta">{incident?.id || '--'}</div></div><Badge tone={pickToneByStatus(incident?.status)}>{incident?.status || 'draft'}</Badge></div>
              <div className="status-row"><div><div className="status-name">Session</div><div className="status-meta">{sessionId || '--'}</div></div><Badge tone={pickToneByStatus(sessionDetail?.status)}>{sessionDetail?.status || 'idle'}</Badge></div>
              <div className="status-row"><div><div className="status-name">轮次</div><div className="status-meta">{sessionDetail ? `${sessionDetail.current_round} / ${Math.max(sessionDetail.current_round, 1)}` : '--'}</div></div><Badge tone="brand">{sessionDetail?.current_phase || 'waiting'}</Badge></div>
              <div className="status-row"><div><div className="status-name">工具调用</div><div className="status-meta">{toolRows.length} 条审计记录</div></div><Badge tone={toolRows.length > 0 ? 'teal' : 'amber'}>{toolRows.length > 0 ? 'Audited' : 'None'}</Badge></div>
              {reviewStatus ? <div className="status-row"><div><div className="status-name">人工审核</div><div className="status-meta">{firstFilled(reviewState.reason, reviewState.comment, '人工审核流程中')}</div></div><Badge tone={reviewStatus === 'pending' ? 'amber' : reviewStatus === 'approved' ? 'teal' : 'red'}>{reviewStatus}</Badge></div> : null}
            </div>
            <div className="toolbar">
              <button className="btn primary" onClick={() => void startAnalysis()} disabled={actionLoading || loading || runningState}>{runningState ? '分析进行中' : actionLoading ? '执行中...' : '启动分析'}</button>
              <button className="btn" onClick={() => void initSessionForExistingIncident()} disabled={actionLoading || !incident?.id}>初始化会话</button>
              <button className="btn danger" onClick={() => void sendSessionControl('cancel')} disabled={actionLoading || !sessionId}>取消分析</button>
              <button className="btn" onClick={() => void sendSessionControl('resume')} disabled={actionLoading || !sessionId || reviewStatus === 'pending'}>恢复分析</button>
              {reviewStatus === 'pending' ? (
                <>
                  <button className="btn" onClick={() => void sendSessionControl('approve')} disabled={actionLoading || !sessionId}>批准继续</button>
                  <button className="btn danger" onClick={() => void sendSessionControl('reject')} disabled={actionLoading || !sessionId}>驳回结束</button>
                </>
              ) : null}
              <button className="btn" onClick={() => void retryFailedAgents()} disabled={actionLoading || !sessionId}>仅重试失败Agent</button>
            </div>
          </Panel>
        </div>

        <div className="stack">
          <Panel title="辩论过程" subtitle="展示真实 lineage 和 tool audit，不再显示示例对话。" extra={<Badge tone="brand">{processRows.length} events</Badge>}>
            <div className="tab-strip">
              <button className={`tab-chip${processTab === 'dialogue' ? ' active' : ''}`} onClick={() => setProcessTab('dialogue')}>对话流</button>
              <button className={`tab-chip${processTab === 'tools' ? ' active' : ''}`} onClick={() => setProcessTab('tools')}>工具调用</button>
              <button className={`tab-chip${processTab === 'rounds' ? ' active' : ''}`} onClick={() => setProcessTab('rounds')}>轮次详情</button>
              <button className={`tab-chip${processTab === 'events' ? ' active' : ''}`} onClick={() => setProcessTab('events')}>事件明细</button>
            </div>
            {processTab === 'dialogue' ? (
              <div className="chat-card scroll-region compact-scroll">
                {processRows.length === 0 ? (
                  <div className="empty-note">{runningState ? '分析已启动，正在等待首批过程事件落盘...' : '当前还没有过程记录。启动分析后，这里会展示主 Agent 命令、专家响应和 Judge 收敛过程。'}</div>
                ) : (
                  processRows.map((row) => {
                    const isTool = `${row.kind || ''} ${row.event_type || ''}`.toLowerCase().includes('tool');
                    const isJudge = String(row.agent_name || '').toLowerCase() === 'judgeagent';
                    return isTool ? (
                      <div key={`${row.seq}-${row.timestamp}`} className="tool-strip"><strong>{row.agent_name || 'System'} · {row.event_type}</strong><span>{summarizeLineage(row)}</span></div>
                    ) : (
                      <div key={`${row.seq}-${row.timestamp}`} className="message">
                        <div className="message-head"><div className="message-title">{row.agent_name || 'System'} · {row.event_type || row.kind}</div><div className="message-time">{formatBeijingDateTime(row.timestamp)}</div></div>
                        <div className={`bubble ${isJudge ? 'judge' : 'agent'}`}>{summarizeLineage(row)}</div>
                      </div>
                    );
                  })
                )}
              </div>
            ) : null}
            {processTab === 'tools' ? (
              <div className="status-grid scroll-region compact-scroll">
                {toolRows.length === 0 ? (
                  <div className="empty-note">当前会话暂无工具调用记录。</div>
                ) : (
                  toolRows.map((row, index) => {
                    const item = asRecord(row);
                    return (
                    <div key={`${index}_${String(item.id || '')}`} className="tool-strip">
                      <strong>
                        {firstFilled(item.agent_name, item.agent, 'System')}
                        {' · '}
                        {firstFilled(item.tool_name, item.event_type, item.kind, 'tool_call')}
                      </strong>
                      <span>{compactText(firstFilled(item.request_summary, item.response_summary, item.summary, summarizeLineage(row as LineageRecord)), 240)}</span>
                    </div>
                    );
                  })
                )}
              </div>
            ) : null}
            {processTab === 'rounds' ? (
              <div className="round-list scroll-region compact-scroll">
                {roundRows.length === 0 ? <div className="empty-note">暂无轮次详情。</div> : roundRows.map((round) => (
                  <div key={`${round.round_number}-${round.agent_name}-${round.started_at}`} className="round-item"><h5>Round {round.round_number} / {round.agent_name}</h5><p>{firstFilled(asRecord(round.output_content).conclusion, asRecord(round.output_content).analysis, round.phase)} · {formatBeijingDateTime(round.started_at)}</p></div>
                ))}
              </div>
            ) : null}
            {processTab === 'events' ? (
              <div className="timeline scroll-region compact-scroll">
                {lineage.slice(0, 80).map((row) => (
                  <div key={`${row.seq}-${row.timestamp}`} className="timeline-card"><div className="timeline-meta"><span>{formatBeijingDateTime(row.timestamp)}</span><span>{row.agent_name || row.kind}</span></div><h4>{row.event_type || row.kind}</h4><p>{compactText(summarizeLineage(row), 220)}</p></div>
                ))}
                {!lineage.length ? <div className="empty-note">暂无事件明细。</div> : null}
              </div>
            ) : null}
          </Panel>
        </div>

        <div className="stack">
          <Panel title="责任田映射" subtitle="真实资产和 context 信息优先展示。" extra={<Badge tone={assetRows.some((row) => row.value !== '--') ? 'teal' : 'brand'}>{assetRows.some((row) => row.value !== '--') ? 'Matched' : 'Pending'}</Badge>}>
            <dl className="summary-grid">
              {assetRows.map((row) => <div key={row.label} className="summary-row"><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
            </dl>
          </Panel>
          <div className="evidence-card">
            <div className="panel-head" style={{ marginBottom: 0 }}><div><h3 className="panel-title">证据链</h3><div className="panel-subtitle">真实 evidence_chain 或空态。</div></div></div>
            <div className="scroll-region compact-scroll">
              {evidenceRows.length === 0 ? <div className="empty-note">暂无证据链。</div> : evidenceRows.map((item, idx) => (
                <div key={`${item.evidence_id || idx}`} className="evidence-item"><h5>{formatBeijingDateTime(debateResult?.created_at || '')} · {item.source}</h5><p>{item.description}{item.source_ref ? `（${item.source_ref}）` : ''}</p></div>
              ))}
            </div>
          </div>
          <div className="evidence-card">
            <div className="panel-head" style={{ marginBottom: 0 }}><div><h3 className="panel-title">Top-K 根因候选</h3><div className="panel-subtitle">真实候选列表；没有就显示空态。</div></div></div>
            <div className="scroll-region compact-scroll">
              {candidateRows.length === 0 ? <div className="empty-note">暂无根因候选。</div> : candidateRows.map((item) => (
                <div key={`${item.rank}-${item.summary}`} className="evidence-item"><h5>Top{item.rank} · {(Number(item.confidence || 0) * 100).toFixed(1)}%</h5><p>{item.summary}</p></div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="bottom-lab">
        <div className="section-label">调查辅助视图</div>
        <div className="lab-grid">
          <div className="panel graph-card">
            <div className="panel-head"><div><h3 className="panel-title">Agent 链路图</h3><div className="panel-subtitle">根据真实 lineage 中出现的 agent 生成。</div></div></div>
            {graphAgents.length === 0 ? <div className="empty-note">暂无 agent 链路。</div> : (
              <>
                {graphAgents.filter((name) => name !== 'JudgeAgent').slice(0, 6).map((name) => (
                  <div key={name} className="graph-stage"><div className="graph-node main">Main Agent</div><div className="graph-arrow"></div><div className="graph-node">{name.replace('Agent', '')}</div></div>
                ))}
                {graphAgents.includes('JudgeAgent') ? <div className="graph-stage" style={{ marginTop: 16 }}><div className="graph-node">Experts</div><div className="graph-arrow"></div><div className="graph-node judge">Judge</div></div> : null}
              </>
            )}
          </div>
          <Panel title="报告结果" subtitle="报告全文与关键摘要。">
            <div className="timeline scroll-region compact-scroll">
              {!reportResult?.content ? (
                <div className="empty-note">报告尚未生成。分析完成后可点击“重新生成报告”。</div>
              ) : (
                <>
                  <div className="timeline-card">
                    <div className="timeline-meta"><span>{formatBeijingDateTime(reportResult?.generated_at || '')}</span><span>report</span></div>
                    <h4>报告摘要</h4>
                    <p>{reportPreview.join(' / ') || '暂无摘要'}</p>
                  </div>
                  <div className="timeline-card">
                    <h4>报告全文（节选）</h4>
                    <p>{compactText(reportResult.content, 1200)}</p>
                  </div>
                </>
              )}
            </div>
          </Panel>
          <Panel title="事件明细" subtitle="原始事件日志时间线。">
            <div className="timeline scroll-region compact-scroll">
              {lineage.slice(0, 24).map((row) => (
                <div key={`${row.seq}-${row.timestamp}`} className="timeline-card"><div className="timeline-meta"><span>{formatBeijingDateTime(row.timestamp)}</span><span>{row.agent_name || row.kind}</span></div><h4>{row.event_type || row.kind}</h4><p>{compactText(summarizeLineage(row), 160)}</p></div>
              ))}
              {!lineage.length ? <div className="empty-note">暂无事件明细。</div> : null}
            </div>
          </Panel>
        </div>
      </section>
    </>
  );
};

export default IncidentV2;
