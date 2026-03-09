import React, { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { debateApi, incidentApi, lineageApi, reportApi, settingsApi, type DebateResult, type Incident, type ReportDiff, type ReportVersion, type ToolAuditResponse } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';
import { compactText } from '@/v2/utils';

const ReplayV2: React.FC = () => {
  const [sessionId, setSessionId] = useState('');
  const [incidentId, setIncidentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [renderedSteps, setRenderedSteps] = useState<string[]>([]);
  const [keyDecisions, setKeyDecisions] = useState<Array<Record<string, unknown>>>([]);
  const [toolAudit, setToolAudit] = useState<ToolAuditResponse | null>(null);
  const [result, setResult] = useState<DebateResult | null>(null);
  const [reportVersions, setReportVersions] = useState<ReportVersion[]>([]);
  const [reportDiff, setReportDiff] = useState<ReportDiff | null>(null);

  useEffect(() => {
    incidentApi.list(1, 20).then((res) => {
      const items = res.items || [];
      setIncidents(items);
      const firstWithSession = items.find((item) => String(item.debate_session_id || '').trim());
      if (firstWithSession) {
        setIncidentId(firstWithSession.id);
        setSessionId(String(firstWithSession.debate_session_id || ''));
      }
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!sessionId.trim()) return;
    if (renderedSteps.length || keyDecisions.length || toolAudit?.items?.length || result || reportVersions.length) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, incidentId]);

  const load = async () => {
    if (!sessionId.trim()) {
      message.warning('请输入 session_id');
      return;
    }
    setLoading(true);
    try {
      const [replay, audit, debateResult] = await Promise.all([
        lineageApi.replay(sessionId.trim(), 120),
        settingsApi.getToolAudit(sessionId.trim()).catch(() => null),
        debateApi.getResult(sessionId.trim()).catch(() => null),
      ]);
      setRenderedSteps(replay.rendered_steps || []);
      setKeyDecisions((replay.key_decisions || []) as Array<Record<string, unknown>>);
      setToolAudit(audit);
      setResult(debateResult);
      if (incidentId.trim()) {
        const [versions, diff] = await Promise.all([
          reportApi.compare(incidentId.trim()).catch(() => []),
          reportApi.compareDiff(incidentId.trim()).catch(() => null),
        ]);
        setReportVersions(versions || []);
        setReportDiff(diff);
      } else {
        setReportVersions([]);
        setReportDiff(null);
      }
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载调查复盘失败');
    } finally {
      setLoading(false);
    }
  };

  const summary = useMemo(() => ({
    decisions: keyDecisions.length,
    steps: renderedSteps.length,
    tools: toolAudit?.items?.length || 0,
    versions: reportVersions.length,
  }), [keyDecisions.length, renderedSteps.length, toolAudit?.items?.length, reportVersions.length]);

  return (
    <>
      <PageHeader
        title="调查复盘台"
        desc="读取真实 replay、工具审计和报告版本差异。先看关键决策路径，再下钻事件和版本变化。"
        actions={
          <>
            <button className="btn" onClick={() => void load()} disabled={loading}>加载 session</button>
            <button className="btn primary" onClick={() => void load()} disabled={loading || !incidentId.trim()}>对比报告版本</button>
          </>
        }
      />

      <section className="grid-4">
        <div className="metric-card"><span className="eyebrow">Steps</span><strong>{summary.steps}</strong><p>回放步骤</p></div>
        <div className="metric-card"><span className="eyebrow">Decisions</span><strong>{summary.decisions}</strong><p>关键决策</p></div>
        <div className="metric-card"><span className="eyebrow">Tool audit</span><strong>{summary.tools}</strong><p>工具审计</p></div>
        <div className="metric-card"><span className="eyebrow">Reports</span><strong>{summary.versions}</strong><p>报告版本</p></div>
      </section>

      <Panel title="会话选择" subtitle="从真实 incident 中选择，或直接手输 session_id / incident_id。">
        <div className="toolbar">
          <select className="v2-input" value={sessionId} onChange={(e) => {
            const sid = e.target.value;
            setSessionId(sid);
            const matched = incidents.find((item) => String(item.debate_session_id || '') === sid);
            setIncidentId(matched?.id || '');
          }}>
            <option value="">选择最近会话</option>
            {incidents.filter((item) => String(item.debate_session_id || '').trim()).map((item) => (
              <option key={item.id} value={String(item.debate_session_id)}>{String(item.debate_session_id)} · {item.title}</option>
            ))}
          </select>
          <input className="v2-input" placeholder="session_id" value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
          <input className="v2-input" placeholder="incident_id" value={incidentId} onChange={(e) => setIncidentId(e.target.value)} />
        </div>
      </Panel>

      <section className="data-grid">
        <Panel title="复盘总览" subtitle="结论、关键证据、下一步都来自真实结果，不再使用演示文案。" extra={<Badge tone={result ? 'teal' : 'brand'}>{result ? 'loaded' : 'empty'}</Badge>}>
          <div className="kv-list scroll-region compact-scroll">
            <div className="kv-item"><h5>当前结论</h5><p>{result?.root_cause || '暂无最终结论'}</p></div>
            <div className="kv-item"><h5>关键证据</h5><p>{Array.isArray(result?.evidence_chain) && result.evidence_chain.length > 0 ? result.evidence_chain.slice(0, 3).map((row) => row.description).join('；') : '暂无关键证据'}</p></div>
            <div className="kv-item"><h5>下一步</h5><p>{reportDiff?.summary || '优先查看关键决策路径与工具审计。'}</p></div>
          </div>
        </Panel>

        <Panel title="报告差异" subtitle="真实 compare / compare-diff 结果；没有版本时显示空态。" extra={<Badge tone={reportDiff?.changed ? 'amber' : 'brand'}>{reportDiff?.changed ? 'changed' : 'no diff'}</Badge>}>
          <div className="kv-list scroll-region compact-scroll">
            {reportVersions.length === 0 ? <div className="empty-note">当前 incident 还没有可对比的报告版本。</div> : reportVersions.map((item) => (
              <div key={item.report_id} className="kv-item"><h5>{item.report_id}</h5><p>{formatBeijingDateTime(item.generated_at)} · {compactText(item.content_preview, 120)}</p></div>
            ))}
            {reportDiff ? <div className="kv-item"><h5>差异摘要</h5><p>{reportDiff.summary}</p></div> : null}
          </div>
        </Panel>
      </section>

      <section className="data-grid">
        <Panel title="关键决策路径" subtitle="真实回放步骤和 key decisions，内容过多时内部滚动。">
          <div className="timeline scroll-region compact-scroll">
            {renderedSteps.length === 0 ? <div className="empty-note">暂无回放步骤。</div> : renderedSteps.map((step, index) => (
              <div key={`${index + 1}`} className="timeline-card"><div className="timeline-meta"><span>step {index + 1}</span><span>replay</span></div><h4>关键步骤</h4><p>{step}</p></div>
            ))}
            {keyDecisions.map((item, index) => (
              <div key={`decision-${index + 1}`} className="timeline-card"><div className="timeline-meta"><span>{String(item.timestamp || '--')}</span><span>{String(item.agent || 'agent')}</span></div><h4>{String(item.title || '决策')}</h4><p>{compactText(item.summary || item.reason || item.content || '-', 180)}</p></div>
            ))}
          </div>
        </Panel>
        <Panel title="工具审计" subtitle="真实 tool audit 记录，帮助确认这次 session 的工具调用是否可靠。">
          <div className="scroll-region compact-scroll status-grid">
            {toolAudit?.items?.length ? toolAudit.items.map((item) => (
              <div key={`${item.seq}-${item.timestamp}`} className="status-row"><div><div className="status-name">{item.agent_name || item.kind}</div><div className="status-meta">{item.event_type} · {formatBeijingDateTime(item.timestamp)}</div></div><Badge tone="teal">audit</Badge></div>
            )) : <div className="empty-note">暂无工具审计记录。</div>}
          </div>
        </Panel>
      </section>
    </>
  );
};

export default ReplayV2;
