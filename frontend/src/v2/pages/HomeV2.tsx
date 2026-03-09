import React, { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { debateApi, incidentApi, settingsApi, type Incident, type ToolConnector } from '@/services/api';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { formatBeijingDateTime } from '@/utils/dateTime';
import { ACTIVE_STATUSES, compactText, pickToneByStatus } from '@/v2/utils';

type DashboardStats = {
  todayAnalyses: number;
  runningCount: number;
  resolvedCount: number;
  avgResolveMinutes: number;
};

const BEIJING_DAY_FORMATTER = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const parseDate = (value: unknown): Date | null => {
  if (value === null || value === undefined || value === '') return null;
  let normalized: string | number = value as string | number;
  if (typeof value === 'string') {
    const raw = value.trim();
    const hasTimezone = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw);
    if (!hasTimezone && /^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(raw)) {
      normalized = `${raw.replace(' ', 'T')}Z`;
    } else {
      normalized = raw;
    }
  }
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
};

const beijingDayKey = (value: unknown): string => {
  const date = parseDate(value);
  if (!date) return '';
  return BEIJING_DAY_FORMATTER.format(date);
};

const HomeV2: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats>({
    todayAnalyses: 0,
    runningCount: 0,
    resolvedCount: 0,
    avgResolveMinutes: 0,
  });
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [connectors, setConnectors] = useState<ToolConnector[]>([]);
  const [toolingReady, setToolingReady] = useState(0);
  const [quickStartLoading, setQuickStartLoading] = useState(false);
  const [autoTaskLoading, setAutoTaskLoading] = useState<Record<string, boolean>>({});
  const [quickStartForm, setQuickStartForm] = useState({
    title: '',
    service_name: '',
    severity: 'high',
    mode: 'standard',
    log_content: '',
  });

  const loadDashboard = async () => {
    try {
      const [recentRes, resolvedRes, closedRes, tooling, connectorList] = await Promise.all([
        incidentApi.list(1, 100),
        incidentApi.list(1, 100, { status: 'resolved' }),
        incidentApi.list(1, 100, { status: 'closed' }),
        settingsApi.getTooling().catch(() => null),
        settingsApi.getToolConnectors().catch(() => [] as ToolConnector[]),
      ]);

      const recent = recentRes.items || [];
      const resolvedItems = [...(resolvedRes.items || []), ...(closedRes.items || [])];
      const todayKey = beijingDayKey(new Date());
      const todayAnalyses = recent.filter((item) => beijingDayKey(item.created_at) === todayKey).length;
      const runningCount = recent.filter((item) => ACTIVE_STATUSES.includes(String(item.status || '').toLowerCase())).length;
      const resolvedCount = resolvedItems.length;
      const durations = resolvedItems
        .map((item) => {
          const start = parseDate(item.created_at);
          const end = parseDate(item.resolved_at || item.updated_at);
          if (!start || !end) return 0;
          const diff = (end.getTime() - start.getTime()) / 60000;
          return diff > 0 ? diff : 0;
        })
        .filter((value) => value > 0);
      const avgResolveMinutes = durations.length
        ? Math.round(durations.reduce((sum, item) => sum + item, 0) / durations.length)
        : 0;

      const localEnabled = [
        tooling?.code_repo?.enabled,
        tooling?.log_file?.enabled,
        tooling?.domain_excel?.enabled,
        tooling?.database?.enabled,
      ].filter(Boolean).length;

      setStats({ todayAnalyses, runningCount, resolvedCount, avgResolveMinutes });
      setIncidents(recent.slice(0, 12));
      setConnectors(connectorList || []);
      setToolingReady(localEnabled);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '新版首页数据加载失败');
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, []);

  const quickStartAnalysis = async () => {
    const title = String(quickStartForm.title || '').trim();
    if (!title) {
      message.warning('请先输入故障标题');
      return;
    }
    setQuickStartLoading(true);
    try {
      const incident = await incidentApi.create({
        title,
        severity: quickStartForm.severity,
        service_name: String(quickStartForm.service_name || '').trim(),
        log_content: String(quickStartForm.log_content || '').trim(),
      });
      const mode = String(quickStartForm.mode || 'standard') as 'standard' | 'quick' | 'background' | 'async';
      const session = await debateApi.createSession(incident.id, { maxRounds: 1, mode });
      message.success(`会话已创建：${session.id}`);
      navigate(`/v2/incident/${incident.id}?session_id=${session.id}&auto_start=1&mode=${mode}`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '创建分析失败');
    } finally {
      setQuickStartLoading(false);
    }
  };

  const runAutoInvestigate = async (incident: Incident) => {
    const incidentKey = String(incident.id || '');
    if (!incidentKey) return;
    setAutoTaskLoading((prev) => ({ ...prev, [incidentKey]: true }));
    try {
      const task = await incidentApi.autoInvestigate(incidentKey, 1);
      let status = String(task.status || 'pending').toLowerCase();
      let lastError = '';
      for (let i = 0; i < 36; i += 1) {
        if (status === 'completed') break;
        if (status === 'failed') {
          throw new Error(lastError || '自动调查任务失败');
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const snapshot = await debateApi.getTask(task.task_id);
        status = String(snapshot.status || 'pending').toLowerCase();
        lastError = String(snapshot.error || '');
      }
      if (status !== 'completed') {
        message.warning(`自动调查仍在执行：${incident.id}`);
      } else {
        message.success(`自动调查完成：${incident.id}`);
      }
      await loadDashboard();
      navigate(`/v2/incident/${incident.id}${incident.debate_session_id ? `?session_id=${incident.debate_session_id}` : ''}`);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || `自动调查失败：${incident.id}`);
    } finally {
      setAutoTaskLoading((prev) => ({ ...prev, [incidentKey]: false }));
    }
  };

  const activeIncidents = incidents.filter((item) => ACTIVE_STATUSES.includes(String(item.status || '').toLowerCase()));
  const resolvedIncidents = incidents.filter((item) => ['resolved', 'completed', 'closed'].includes(String(item.status || '').toLowerCase()));
  const riskIncidents = incidents.filter((item) => ['failed', 'waiting', 'retrying'].includes(String(item.status || '').toLowerCase()) || !item.root_cause);
  const healthyConnectors = connectors.filter((item) => item.connected && item.healthy).length;

  const recentCompleted = useMemo(() => resolvedIncidents.slice(0, 4), [resolvedIncidents]);

  return (
    <>
      <PageHeader
        title="生产问题根因分析总控台"
        desc="首页直接读取真实 incident、工具配置和连接状态。没有数据时给空态，有数据时优先展示正在运行和待关注的问题。"
        actions={
          <>
            <button className="btn" onClick={() => navigate('/v2/assets')}>维护责任田</button>
            <button className="btn" onClick={() => navigate('/v2/history')}>查看历史</button>
            <button className="btn primary" onClick={() => void quickStartAnalysis()} disabled={quickStartLoading}>
              {quickStartLoading ? '启动中...' : '创建并启动分析'}
            </button>
          </>
        }
      />

      <section className="grid-4">
        <div className="metric-card"><div className="label">今日新建分析</div><div className="metric-value"><strong>{stats.todayAnalyses}</strong><span>北京时间维度</span></div></div>
        <div className="metric-card"><div className="label">运行中会话</div><div className="metric-value"><strong>{stats.runningCount}</strong><span>{activeIncidents.length} 条活跃事件</span></div></div>
        <div className="metric-card"><div className="label">已闭环事件</div><div className="metric-value"><strong>{stats.resolvedCount}</strong><span>resolved / closed</span></div></div>
        <div className="metric-card"><div className="label">平均定位时长</div><div className="metric-value"><strong>{stats.avgResolveMinutes || '--'}</strong><span>{stats.avgResolveMinutes ? '分钟' : '暂无样本'}</span></div></div>
      </section>

      <section className="split-hero">
        <Panel title="快速创建分析" subtitle="这里直接走真实创建 incident + session 流程。" extra={<Badge tone="brand">Real API</Badge>}>
          <div className="form-grid">
            <div className="field"><label>故障标题</label><input className="input v2-input" value={quickStartForm.title} onChange={(e) => setQuickStartForm((prev) => ({ ...prev, title: e.target.value }))} placeholder="例如：/orders 接口 502，CPU 飙升" /></div>
            <div className="field"><label>服务名称</label><input className="input v2-input" value={quickStartForm.service_name} onChange={(e) => setQuickStartForm((prev) => ({ ...prev, service_name: e.target.value }))} placeholder="order-service" /></div>
            <div className="field"><label>严重级别</label><select className="input v2-input" value={quickStartForm.severity} onChange={(e) => setQuickStartForm((prev) => ({ ...prev, severity: e.target.value }))}><option value="critical">critical</option><option value="high">high</option><option value="medium">medium</option><option value="low">low</option></select></div>
            <div className="field"><label>会话模式</label><select className="input v2-input" value={quickStartForm.mode} onChange={(e) => setQuickStartForm((prev) => ({ ...prev, mode: e.target.value }))}><option value="standard">standard</option><option value="quick">quick</option><option value="background">background</option><option value="async">async</option></select></div>
            <div className="field" style={{ gridColumn: '1 / -1' }}><label>故障日志 / 现象摘要</label><textarea className="textarea v2-textarea" value={quickStartForm.log_content} onChange={(e) => setQuickStartForm((prev) => ({ ...prev, log_content: e.target.value }))} placeholder="可选：粘贴关键日志、报错堆栈或现象摘要" /></div>
          </div>
        </Panel>
        <div className="stack">
          <Panel title="系统状态" subtitle="从真实配置和 connector 状态汇总。" extra={<Badge tone={healthyConnectors === connectors.length && connectors.length > 0 ? 'teal' : 'amber'}>{healthyConnectors}/{connectors.length || 0}</Badge>}>
            <div className="status-grid">
              <div className="status-row"><div><div className="status-name">Tool Connectors</div><div className="status-meta">健康 {healthyConnectors} / 总数 {connectors.length || 0}</div></div><Badge tone={healthyConnectors === connectors.length && connectors.length > 0 ? 'teal' : 'amber'}>{healthyConnectors === connectors.length && connectors.length > 0 ? 'healthy' : 'degraded'}</Badge></div>
              <div className="status-row"><div><div className="status-name">Local Tools</div><div className="status-meta">Git / Log / Excel / DB</div></div><Badge tone={toolingReady >= 3 ? 'teal' : 'amber'}>{toolingReady}/4</Badge></div>
              <div className="status-row"><div><div className="status-name">Active Incidents</div><div className="status-meta">直接来自 incident 列表</div></div><Badge tone={stats.runningCount > 0 ? 'amber' : 'teal'}>{stats.runningCount}</Badge></div>
            </div>
          </Panel>
          <Panel title="近期风险信号" subtitle="优先展示 waiting / retrying / failed / 无结论事件。" extra={<Badge tone={riskIncidents.length > 0 ? 'red' : 'teal'}>{riskIncidents.length > 0 ? 'Attention' : 'Stable'}</Badge>}>
            <div className="status-grid scroll-region compact-scroll">
              {riskIncidents.length === 0 ? (
                <div className="empty-note">当前没有需要额外关注的风险事件。</div>
              ) : (
                riskIncidents.slice(0, 6).map((item) => (
                  <div key={item.id} className="status-row">
                    <div>
                      <div className="status-name">{item.title}</div>
                      <div className="status-meta">{compactText(item.root_cause || item.description || '尚未收敛结论', 72)}</div>
                    </div>
                    <Badge tone={pickToneByStatus(item.status)}>{item.status}</Badge>
                  </div>
                ))
              )}
            </div>
          </Panel>
        </div>
      </section>

      <section className="data-grid">
        <Panel title="进行中的事件" subtitle="点击直接进入 v2 分析详情。" extra={<Badge tone="brand">{activeIncidents.length} active</Badge>}>
          <div className="scroll-region table-scroll">
            {activeIncidents.length === 0 ? (
              <div className="empty-note">暂无进行中的事件，创建第一条分析即可在这里看到真实数据。</div>
            ) : (
              <table className="table">
                <thead><tr><th>事件</th><th>状态</th><th>主结论</th><th>更新时间</th><th>操作</th></tr></thead>
                <tbody>
                  {activeIncidents.slice(0, 10).map((item) => (
                    <tr key={item.id} onClick={() => navigate(`/v2/incident/${item.id}${item.debate_session_id ? `?session_id=${item.debate_session_id}` : ''}`)} className="clickable-row">
                      <td><span className="row-title">{item.id}</span><br /><span className="muted">{item.title}</span></td>
                      <td><Badge tone={pickToneByStatus(item.status)}>{item.status}</Badge></td>
                      <td>{compactText(item.root_cause || item.description || '尚无结论', 80)}</td>
                      <td>{formatBeijingDateTime(item.updated_at, '--')}</td>
                      <td>
                        <div className="table-actions">
                          <button
                            className="btn"
                            onClick={(event) => {
                              event.stopPropagation();
                              void runAutoInvestigate(item);
                            }}
                            disabled={Boolean(autoTaskLoading[item.id])}
                          >
                            {autoTaskLoading[item.id] ? '执行中...' : '一键自动调查'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Panel>
        <div className="stack">
          <Panel title="最近完成分析" subtitle="真实显示最近已收敛的 incident。">
            <div className="status-grid scroll-region compact-scroll">
              {recentCompleted.length === 0 ? (
                <div className="empty-note">最近暂无已完成分析。</div>
              ) : (
                recentCompleted.map((item) => (
                  <div key={item.id} className="status-row">
                    <div>
                      <div className="status-name">{item.title}</div>
                      <div className="status-meta">{compactText(item.root_cause || item.fix_suggestion || '报告已生成，点击查看详情', 72)}</div>
                    </div>
                    <Badge tone="teal">{item.status}</Badge>
                  </div>
                ))
              )}
            </div>
          </Panel>
          <Panel title="Agent 能力矩阵" subtitle="能力说明保留为静态信息，但不再伪装成运行数据。">
            <div className="agent-matrix">
              <div className="mini-panel"><h4>Main</h4><p>调度、阶段判断、命令分派、结果收敛</p></div>
              <div className="mini-panel"><h4>Log</h4><p>日志、异常链路、时间线与信号相关性</p></div>
              <div className="mini-panel"><h4>Code</h4><p>仓库定位、实现路径、变更窗口与热区</p></div>
              <div className="mini-panel"><h4>Domain</h4><p>责任田、领域归属、接口和聚合根映射</p></div>
              <div className="mini-panel"><h4>Database</h4><p>表结构、索引、慢 SQL、会话与锁</p></div>
            </div>
          </Panel>
        </div>
      </section>
    </>
  );
};

export default HomeV2;
