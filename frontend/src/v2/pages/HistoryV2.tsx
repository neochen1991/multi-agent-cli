import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { debateApi, incidentApi, type Incident } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';
import {
  ACTIVE_STATUSES,
  compactText,
  formatDuration,
  formatSessionWindow,
  isActiveStatus,
  pickToneByStatus,
} from '@/v2/utils';

type SessionMeta = {
  mode: string;
  currentPhase: string;
  confidence: number | null;
  updatedAt: string;
  completedAt: string;
};

const HistoryV2: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [filters, setFilters] = useState({ status: '', service: '', query: '' });
  const [metaMap, setMetaMap] = useState<Record<string, SessionMeta>>({});

  const load = async () => {
    setLoading(true);
    try {
      const data = await incidentApi.list(1, 60, {
        status: filters.status || undefined,
        service_name: filters.service || undefined,
      });
      const items = data.items || [];
      setIncidents(items);
      setSelectedId((prev) => prev || items[0]?.id || '');
      const sessionIds = items
        .map((item) => String(item.debate_session_id || '').trim())
        .filter(Boolean)
        .slice(0, 20);
      if (!sessionIds.length) {
        setMetaMap({});
        return;
      }
      const [details, results] = await Promise.all([
        Promise.all(sessionIds.map((sid) => debateApi.get(sid).catch(() => null))),
        Promise.all(sessionIds.map((sid) => debateApi.getResult(sid).catch(() => null))),
      ]);
      const next: Record<string, SessionMeta> = {};
      sessionIds.forEach((sid, idx) => {
        const detail = details[idx];
        const result = results[idx];
        if (!detail) return;
        const context = (detail.context || {}) as Record<string, unknown>;
        next[sid] = {
          mode: String(context.requested_execution_mode || context.execution_mode || 'standard'),
          currentPhase: String(detail.current_phase || '-'),
          confidence: typeof result?.confidence === 'number' ? result.confidence : null,
          updatedAt: String(detail.updated_at || ''),
          completedAt: String(detail.completed_at || ''),
        };
      });
      setMetaMap(next);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载历史会话失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.status, filters.service]);

  useEffect(() => {
    if (!incidents.some((item) => isActiveStatus(item.status))) return undefined;
    const timer = window.setInterval(() => {
      void load();
    }, 10000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidents]);

  const filtered = useMemo(() => {
    const q = filters.query.trim().toLowerCase();
    if (!q) return incidents;
    return incidents.filter((item) => {
      const text = [item.id, item.title, item.service_name, item.root_cause, item.description]
        .map((value) => String(value || '').toLowerCase())
        .join(' ');
      return text.includes(q);
    });
  }, [filters.query, incidents]);

  const selected = useMemo(
    () => filtered.find((item) => item.id === selectedId) || filtered[0] || null,
    [filtered, selectedId],
  );
  const selectedMeta = selected?.debate_session_id ? metaMap[String(selected.debate_session_id)] : null;

  const summary = useMemo(() => ({
    total: incidents.length,
    running: incidents.filter((item) => ACTIVE_STATUSES.includes(String(item.status || '').toLowerCase())).length,
    done: incidents.filter((item) => ['resolved', 'completed', 'closed'].includes(String(item.status || '').toLowerCase())).length,
    failed: incidents.filter((item) => ['failed', 'cancelled'].includes(String(item.status || '').toLowerCase())).length,
  }), [incidents]);

  const openSelected = () => {
    if (!selected) return;
    const sid = String(selected.debate_session_id || '').trim();
    navigate(sid ? `/v2/incident/${selected.id}?session_id=${sid}` : `/v2/incident/${selected.id}`);
  };

  return (
    <>
      <PageHeader
        title="历史会话账本"
        desc="顶部筛选固定，列表与详情拆开；默认先扫状态、根因摘要和最后更新时间，再决定进入详情。"
        actions={
          <>
            <button className="btn" onClick={() => void load()} disabled={loading}>刷新</button>
            <button className="btn primary" onClick={openSelected} disabled={!selected}>进入详情</button>
          </>
        }
      />

      <section className="grid-4">
        <div className="metric-card"><span className="eyebrow">Total</span><strong>{summary.total}</strong><p>累计事件</p></div>
        <div className="metric-card"><span className="eyebrow">Running</span><strong>{summary.running}</strong><p>运行中</p></div>
        <div className="metric-card"><span className="eyebrow">Closed</span><strong>{summary.done}</strong><p>已闭环</p></div>
        <div className="metric-card"><span className="eyebrow">Failed</span><strong>{summary.failed}</strong><p>失败 / 取消</p></div>
      </section>

      <Panel title="筛选器" subtitle="筛选区固定在顶部，表格区域独立滚动。">
        <div className="toolbar">
          <input className="v2-input" placeholder="搜索标题 / 根因 / 服务" value={filters.query} onChange={(e) => setFilters((prev) => ({ ...prev, query: e.target.value }))} />
          <input className="v2-input" placeholder="状态，如 running" value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))} />
          <input className="v2-input" placeholder="服务名，如 order-service" value={filters.service} onChange={(e) => setFilters((prev) => ({ ...prev, service: e.target.value }))} />
        </div>
      </Panel>

      <section className="data-grid">
        <Panel title="会话列表" subtitle="列表内容过多时独立滚动，不带动整页滚动。" extra={<Badge tone="brand">{loading ? 'loading' : `${filtered.length} sessions`}</Badge>}>
          <div className="table-scroll compact-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>会话</th>
                  <th>状态</th>
                  <th>根因摘要</th>
                  <th>更新时间</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const sid = String(item.debate_session_id || '').trim();
                  const meta = sid ? metaMap[sid] : null;
                  const active = item.id === selected?.id;
                  return (
                    <tr key={item.id} className={active ? 'active clickable-row' : 'clickable-row'} onClick={() => setSelectedId(item.id)}>
                      <td>
                        <span className="row-title">{item.id}{sid ? ` / ${sid}` : ''}</span>
                        <br />
                        <span className="muted">{compactText(item.title || item.description || '-', 64)}</span>
                      </td>
                      <td>
                        <Badge tone={pickToneByStatus(item.status)}>{String(item.status || '-')}</Badge>
                      </td>
                      <td>
                        {compactText(item.root_cause || item.fix_suggestion || item.description || '-', 88)}
                      </td>
                      <td>
                        {formatBeijingDateTime(meta?.updatedAt || item.updated_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!filtered.length ? <div className="empty-note">暂无历史会话</div> : null}
          </div>
        </Panel>

        <div className="stack">
          <Panel title="详情预览" subtitle="点击记录后在同页预览，不新开页面。" extra={selected ? <Badge tone={pickToneByStatus(selected.status)}>{selected.status}</Badge> : undefined}>
            {selected ? (
              <div className="kv-list scroll-region compact-scroll">
                <div className="kv-item"><h5>标题</h5><p>{selected.title || '-'}</p></div>
                <div className="kv-item"><h5>服务与严重度</h5><p>{selected.service_name || '-'} · {String(selected.severity || '-').toUpperCase()}</p></div>
                <div className="kv-item"><h5>根因摘要</h5><p>{selected.root_cause || '暂无最终根因'}</p></div>
                <div className="kv-item"><h5>会话窗口</h5><p>{formatSessionWindow(selected.created_at, selectedMeta?.updatedAt || selected.updated_at)}</p></div>
                <div className="kv-item"><h5>分析模式 / 阶段</h5><p>{selectedMeta?.mode || '-'} · {selectedMeta?.currentPhase || '-'}</p></div>
                <div className="kv-item"><h5>置信度 / 耗时</h5><p>{typeof selectedMeta?.confidence === 'number' ? `${(selectedMeta.confidence * 100).toFixed(1)}%` : '--'} · {formatDuration(selected.created_at, selectedMeta?.completedAt || selected.updated_at)}</p></div>
              </div>
            ) : <div className="empty-note">选择左侧一条会话后查看详情</div>}
          </Panel>

          <Panel title="状态图例" subtitle="统一 status 颜色，减少 phase/status 混淆。">
            <div className="tag-row">
              <Badge tone="brand">running</Badge>
              <Badge tone="amber">waiting</Badge>
              <Badge tone="teal">resolved</Badge>
              <Badge tone="red">failed</Badge>
            </div>
          </Panel>
        </div>
      </section>
    </>
  );
};

export default HistoryV2;
