import React, { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { settingsApi, type AgentToolingConfig, type ToolConnector } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const cloneTooling = (value: AgentToolingConfig): AgentToolingConfig => JSON.parse(JSON.stringify(value)) as AgentToolingConfig;

const SettingsV2: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tooling, setTooling] = useState<AgentToolingConfig | null>(null);
  const [draft, setDraft] = useState<AgentToolingConfig | null>(null);
  const [connectors, setConnectors] = useState<ToolConnector[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const [toolingRes, connectorsRes] = await Promise.all([
        settingsApi.getTooling(),
        settingsApi.getToolConnectors().catch(() => []),
      ]);
      setTooling(toolingRes);
      setDraft(cloneTooling(toolingRes));
      setConnectors(connectorsRes || []);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载设置失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const connectorSummary = useMemo(() => ({
    total: connectors.length,
    connected: connectors.filter((item) => item.connected || item.healthy || item.status === 'connected').length,
  }), [connectors]);

  const updateNested = (path: string[], value: unknown) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const next = cloneTooling(prev);
      let cursor: Record<string, unknown> = next as unknown as Record<string, unknown>;
      for (let idx = 0; idx < path.length - 1; idx += 1) {
        const key = path[idx];
        const current = cursor[key] as Record<string, unknown> | undefined;
        cursor[key] = current && typeof current === 'object' ? { ...current } : {};
        cursor = cursor[key] as Record<string, unknown>;
      }
      cursor[path[path.length - 1]] = value;
      return next;
    });
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const saved = await settingsApi.updateTooling(draft);
      setTooling(saved);
      setDraft(cloneTooling(saved));
      message.success('设置已保存');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        title="系统设置与运行时控制"
        desc="直接读取真实工具配置和连接器状态；页面保留分组结构，但不再展示假状态。"
        actions={
          <>
            <button className="btn" onClick={() => void load()} disabled={loading}>刷新</button>
            <button className="btn primary" onClick={() => void save()} disabled={!draft || saving}>保存修改</button>
          </>
        }
      />

      <section className="grid-4">
        <div className="metric-card"><span className="eyebrow">Local tools</span><strong>{[
          draft?.code_repo?.enabled,
          draft?.log_file?.enabled,
          draft?.domain_excel?.enabled,
          draft?.database?.enabled,
        ].filter(Boolean).length}</strong><p>已启用本地工具</p></div>
        <div className="metric-card"><span className="eyebrow">Connectors</span><strong>{connectorSummary.connected}/{connectorSummary.total}</strong><p>连接器可用数</p></div>
        <div className="metric-card"><span className="eyebrow">Skills</span><strong>{draft?.skills?.enabled ? 'ON' : 'OFF'}</strong><p>本地 Skill 注入</p></div>
        <div className="metric-card"><span className="eyebrow">Updated</span><strong>{tooling?.updated_at ? 'SYNC' : '--'}</strong><p>{formatBeijingDateTime(tooling?.updated_at || '')}</p></div>
      </section>

      <section className="stack">
        <Panel title="模型与运行时" subtitle="真实运行时配置摘要。" extra={<Badge tone="brand">runtime</Badge>}>
          <div className="kv-list">
            <div className="kv-item"><h5>代码仓</h5><p>{draft?.code_repo?.repo_url || draft?.code_repo?.local_repo_path || '--'}</p></div>
            <div className="kv-item"><h5>日志文件</h5><p>{draft?.log_file?.file_path || '--'}</p></div>
            <div className="kv-item"><h5>责任田文件</h5><p>{draft?.domain_excel?.excel_path || '--'}</p></div>
            <div className="kv-item"><h5>数据库</h5><p>{draft?.database?.engine || '--'} · {draft?.database?.postgres_dsn || draft?.database?.db_path || '--'}</p></div>
          </div>
        </Panel>

        <Panel title="数据源与工具" subtitle="可直接编辑真实配置；内容过多时块内滚动。" extra={<Badge tone="teal">editable</Badge>}>
          {draft ? (
            <div className="scroll-region compact-scroll">
              <div className="settings-block">
                <div className="settings-row"><label className="toggle-line"><input type="checkbox" checked={draft.code_repo.enabled} onChange={(e) => updateNested(['code_repo', 'enabled'], e.target.checked)} /> 启用 Git 工具</label><input className="v2-input" value={draft.code_repo.local_repo_path || ''} onChange={(e) => updateNested(['code_repo', 'local_repo_path'], e.target.value)} placeholder="本地代码仓路径" /></div>
                <div className="settings-row"><label className="toggle-line"><input type="checkbox" checked={draft.log_file.enabled} onChange={(e) => updateNested(['log_file', 'enabled'], e.target.checked)} /> 启用日志文件</label><input className="v2-input" value={draft.log_file.file_path || ''} onChange={(e) => updateNested(['log_file', 'file_path'], e.target.value)} placeholder="日志文件路径" /></div>
                <div className="settings-row"><label className="toggle-line"><input type="checkbox" checked={draft.domain_excel.enabled} onChange={(e) => updateNested(['domain_excel', 'enabled'], e.target.checked)} /> 启用责任田文件</label><input className="v2-input" value={draft.domain_excel.excel_path || ''} onChange={(e) => updateNested(['domain_excel', 'excel_path'], e.target.value)} placeholder="责任田 Excel 路径" /></div>
                <div className="settings-row"><label className="toggle-line"><input type="checkbox" checked={Boolean(draft.database?.enabled)} onChange={(e) => updateNested(['database', 'enabled'], e.target.checked)} /> 启用数据库工具</label><input className="v2-input" value={draft.database?.postgres_dsn || draft.database?.db_path || ''} onChange={(e) => updateNested(['database', draft.database?.engine === 'postgresql' ? 'postgres_dsn' : 'db_path'], e.target.value)} placeholder="PostgreSQL DSN / DB 路径" /></div>
                <div className="settings-row"><label className="toggle-line"><input type="checkbox" checked={Boolean(draft.skills?.enabled)} onChange={(e) => updateNested(['skills', 'enabled'], e.target.checked)} /> 启用 Skill</label><input className="v2-input" value={draft.skills?.skills_dir || ''} onChange={(e) => updateNested(['skills', 'skills_dir'], e.target.value)} placeholder="skills 目录" /></div>
              </div>
            </div>
          ) : <div className="empty-note">暂无设置数据</div>}
        </Panel>

        <Panel title="连接器状态" subtitle="直接展示真实 connector 探活状态。" extra={<Badge tone="amber">{connectorSummary.connected}/{connectorSummary.total}</Badge>}>
          <div className="scroll-region compact-scroll">
            <div className="status-grid">
              {connectors.map((item) => (
                <div key={item.name} className="status-row">
                  <div>
                    <div className="status-name">{item.name}</div>
                    <div className="status-meta">{item.resource} · {item.tools.join(', ') || 'no tools'}</div>
                  </div>
                  <Badge tone={item.connected || item.healthy || item.status === 'connected' ? 'teal' : 'amber'}>{item.status || (item.connected ? 'connected' : 'unknown')}</Badge>
                </div>
              ))}
              {!connectors.length ? <div className="empty-note">暂无连接器状态</div> : null}
            </div>
          </div>
        </Panel>
      </section>
    </>
  );
};

export default SettingsV2;
