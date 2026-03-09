import React, { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import {
  assetApi,
  type ResponsibilityAssetRecord,
} from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';
import { compactText, uniqueStrings } from '@/v2/utils';

const splitListText = (value: string): string[] =>
  String(value || '')
    .split(/[,，;；\n|、]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const AssetsV2: React.FC = () => {
  const [tab, setTab] = useState<'overview' | 'maintain'>('overview');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [replaceExisting, setReplaceExisting] = useState(true);
  const [filters, setFilters] = useState({ q: '', domain: '', aggregate: '', api: '' });
  const [records, setRecords] = useState<ResponsibilityAssetRecord[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [resourceSummary, setResourceSummary] = useState<Record<string, unknown>>({});
  const [manual, setManual] = useState({
    asset_id: '', feature: '', domain: '', aggregate: '', frontend_pages: '', api_interfaces: '',
    code_items: '', database_tables: '', dependency_services: '', monitor_items: '', owner_team: '', owner: '',
  });

  const load = async () => {
    setLoading(true);
    try {
      const [list, resources] = await Promise.all([
        assetApi.listResponsibilityAssets({
          q: filters.q || undefined,
          domain: filters.domain || undefined,
          aggregate: filters.aggregate || undefined,
          api: filters.api || undefined,
        }),
        assetApi.resources().catch(() => ({})),
      ]);
      const items = list.items || [];
      setRecords(items);
      setSelectedId((prev) => prev || items[0]?.asset_id || '');
      setResourceSummary(resources);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载责任田资产失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.domain, filters.aggregate, filters.api]);

  const filtered = useMemo(() => {
    const q = filters.q.trim().toLowerCase();
    if (!q) return records;
    return records.filter((row) => {
      const text = [
        row.feature,
        row.domain,
        row.aggregate,
        row.owner_team,
        row.owner,
        ...(row.api_interfaces || []),
        ...(row.database_tables || []),
      ].join(' ').toLowerCase();
      return text.includes(q);
    });
  }, [filters.q, records]);

  const selected = useMemo(
    () => filtered.find((row) => row.asset_id === selectedId) || filtered[0] || null,
    [filtered, selectedId],
  );

  const stats = useMemo(() => ({
    domains: uniqueStrings(records.map((row) => row.domain)).length,
    aggregates: uniqueStrings(records.map((row) => row.aggregate)).length,
    apis: records.reduce((sum, row) => sum + (row.api_interfaces || []).length, 0),
    tables: uniqueStrings(records.flatMap((row) => row.database_tables || [])).length,
  }), [records]);

  const uploadFile = async (file?: File | null) => {
    if (!file) return;
    setUploading(true);
    try {
      const result = await assetApi.uploadResponsibilityAssets(file, replaceExisting);
      message.success(`导入完成：${result.imported} 条，当前存量 ${result.stored} 条`);
      setTab('overview');
      await load();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '导入失败');
    } finally {
      setUploading(false);
    }
  };

  const saveManual = async () => {
    if (!manual.domain.trim() || !manual.aggregate.trim() || !manual.api_interfaces.trim()) {
      message.warning('至少填写领域、聚合根、API 接口');
      return;
    }
    try {
      await assetApi.upsertResponsibilityAsset({
        asset_id: manual.asset_id.trim() || undefined,
        feature: manual.feature.trim(),
        domain: manual.domain.trim(),
        aggregate: manual.aggregate.trim(),
        frontend_pages: splitListText(manual.frontend_pages),
        api_interfaces: splitListText(manual.api_interfaces),
        code_items: splitListText(manual.code_items),
        database_tables: splitListText(manual.database_tables),
        dependency_services: splitListText(manual.dependency_services),
        monitor_items: splitListText(manual.monitor_items),
        owner_team: manual.owner_team.trim(),
        owner: manual.owner.trim(),
      });
      message.success('已保存责任田资产');
      setManual({
        asset_id: '', feature: '', domain: '', aggregate: '', frontend_pages: '', api_interfaces: '',
        code_items: '', database_tables: '', dependency_services: '', monitor_items: '', owner_team: '', owner: '',
      });
      setTab('overview');
      await load();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '保存失败');
    }
  };

  const editRecord = (row: ResponsibilityAssetRecord) => {
    setManual({
      asset_id: row.asset_id,
      feature: row.feature || '',
      domain: row.domain || '',
      aggregate: row.aggregate || '',
      frontend_pages: (row.frontend_pages || []).join(', '),
      api_interfaces: (row.api_interfaces || []).join(', '),
      code_items: (row.code_items || []).join(', '),
      database_tables: (row.database_tables || []).join(', '),
      dependency_services: (row.dependency_services || []).join(', '),
      monitor_items: (row.monitor_items || []).join(', '),
      owner_team: row.owner_team || '',
      owner: row.owner || '',
    });
    setTab('maintain');
  };

  const deleteRecord = async (assetId: string) => {
    try {
      await assetApi.deleteResponsibilityAsset(assetId);
      message.success('已删除资产');
      if (selectedId === assetId) setSelectedId('');
      await load();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '删除失败');
    }
  };

  return (
    <>
      <PageHeader
        title="责任田资产目录"
        desc="已保存资产和导入维护分离；默认先看真实资产，再决定补录或导入。"
        actions={
          <>
            <button className="btn" onClick={() => void load()} disabled={loading}>刷新</button>
            <button className="btn primary" onClick={() => setTab('maintain')}>上传 / 维护</button>
          </>
        }
      />

      <section className="grid-4">
        <div className="metric-card"><span className="eyebrow">Domains</span><strong>{stats.domains}</strong><p>领域数</p></div>
        <div className="metric-card"><span className="eyebrow">Aggregates</span><strong>{stats.aggregates}</strong><p>聚合根数</p></div>
        <div className="metric-card"><span className="eyebrow">APIs</span><strong>{stats.apis}</strong><p>接口数</p></div>
        <div className="metric-card"><span className="eyebrow">Tables</span><strong>{stats.tables}</strong><p>数据库表数</p></div>
      </section>

      <Panel title="页面结构" subtitle="已保存资产和导入维护并列，而不是把保存结果堆到页面最后。">
        <div className="tab-strip">
          <button className={`tab-chip${tab === 'overview' ? ' active' : ''}`} onClick={() => setTab('overview')}>资产总览</button>
          <button className={`tab-chip${tab === 'maintain' ? ' active' : ''}`} onClick={() => setTab('maintain')}>导入与维护</button>
        </div>
      </Panel>

      {tab === 'overview' ? (
        <section className="data-grid">
          <Panel title="已保存资产" subtitle="列表与过滤使用真实责任田数据；数据过多时内部滚动。" extra={<Badge tone="brand">{filtered.length} records</Badge>}>
            <div className="toolbar">
              <input className="v2-input" placeholder="搜索领域 / 聚合根 / API / 表" value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} />
              <input className="v2-input" placeholder="领域" value={filters.domain} onChange={(e) => setFilters((prev) => ({ ...prev, domain: e.target.value }))} />
              <input className="v2-input" placeholder="聚合根" value={filters.aggregate} onChange={(e) => setFilters((prev) => ({ ...prev, aggregate: e.target.value }))} />
              <input className="v2-input" placeholder="API" value={filters.api} onChange={(e) => setFilters((prev) => ({ ...prev, api: e.target.value }))} />
            </div>
            <div className="table-scroll compact-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>资产</th>
                    <th>Owner</th>
                    <th>接口 / 表</th>
                    <th>依赖</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => (
                    <tr key={row.asset_id} className={selected?.asset_id === row.asset_id ? 'active clickable-row' : 'clickable-row'} onClick={() => setSelectedId(row.asset_id)}>
                      <td>
                        <span className="row-title">{row.domain} / {row.aggregate}</span><br />
                        <span className="muted">特性：{compactText(row.feature || '-', 48)}</span>
                      </td>
                      <td>{row.owner_team || '-'} / {row.owner || '-'}</td>
                      <td>{compactText([...(row.api_interfaces || []), ...(row.database_tables || [])].join(' · '), 88)}</td>
                      <td>{compactText((row.dependency_services || []).join('、') || '-', 48)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!filtered.length ? <div className="empty-note">暂无责任田资产</div> : null}
            </div>
          </Panel>

          <div className="stack">
            <Panel title="资产详情" subtitle="按页面 / 接口 / 代码 / DB / 监控组织，内容多时内部滚动。" extra={selected ? <Badge tone="teal">{selected.asset_id}</Badge> : undefined}>
              {selected ? (
                <div className="scroll-region compact-scroll">
                  <dl className="summary-grid">
                    <div className="summary-row"><dt>特性</dt><dd>{selected.feature || '-'}</dd></div>
                    <div className="summary-row"><dt>前端页面</dt><dd>{(selected.frontend_pages || []).join('、') || '-'}</dd></div>
                    <div className="summary-row"><dt>代码清单</dt><dd>{(selected.code_items || []).join('、') || '-'}</dd></div>
                    <div className="summary-row"><dt>数据库表</dt><dd>{(selected.database_tables || []).join('、') || '-'}</dd></div>
                    <div className="summary-row"><dt>依赖服务</dt><dd>{(selected.dependency_services || []).join('、') || '-'}</dd></div>
                    <div className="summary-row"><dt>监控清单</dt><dd>{(selected.monitor_items || []).join('、') || '-'}</dd></div>
                    <div className="summary-row"><dt>更新时间</dt><dd>{formatBeijingDateTime(selected.updated_at)}</dd></div>
                  </dl>
                </div>
              ) : <div className="empty-note">选择左侧资产后查看详情</div>}
            </Panel>

            <Panel title="存储摘要" subtitle="来自真实资源接口，不再展示假统计。">
              <div className="kv-list">
                <div className="kv-item"><h5>存储位置</h5><p>{String((resourceSummary.responsibility_assets as Record<string, unknown> | undefined)?.storage_path || '--')}</p></div>
                <div className="kv-item"><h5>最近更新时间</h5><p>{formatBeijingDateTime(String((resourceSummary.responsibility_assets as Record<string, unknown> | undefined)?.latest_updated_at || ''))}</p></div>
                <div className="kv-item"><h5>操作</h5><p><button className="btn" onClick={() => selected && editRecord(selected)} disabled={!selected}>编辑当前资产</button> <button className="btn danger" onClick={() => selected && void deleteRecord(selected.asset_id)} disabled={!selected}>删除当前资产</button></p></div>
              </div>
            </Panel>
          </div>
        </section>
      ) : (
        <section className="data-grid">
          <Panel title="Excel 导入" subtitle="支持替换或追加，导入成功后刷新目录。" extra={<Badge tone="amber">{uploading ? 'uploading' : 'ready'}</Badge>}>
            <div className="stack">
              <label className="toggle-line"><input type="checkbox" checked={replaceExisting} onChange={(e) => setReplaceExisting(e.target.checked)} /> 替换已有资产</label>
              <label className="upload-dropzone">
                <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => void uploadFile(e.target.files?.[0] || null)} />
                <span>{uploading ? '正在上传...' : '选择责任田 Excel / CSV 文件'}</span>
              </label>
            </div>
          </Panel>
          <div className="stack">
            <Panel title="手工补录" subtitle="用于修正 owner、接口、代码、数据库表和监控项。">
              <div className="form-grid">
                <input className="v2-input" placeholder="特性" value={manual.feature} onChange={(e) => setManual((prev) => ({ ...prev, feature: e.target.value }))} />
                <input className="v2-input" placeholder="领域" value={manual.domain} onChange={(e) => setManual((prev) => ({ ...prev, domain: e.target.value }))} />
                <input className="v2-input" placeholder="聚合根" value={manual.aggregate} onChange={(e) => setManual((prev) => ({ ...prev, aggregate: e.target.value }))} />
                <input className="v2-input" placeholder="负责人团队" value={manual.owner_team} onChange={(e) => setManual((prev) => ({ ...prev, owner_team: e.target.value }))} />
                <input className="v2-input" placeholder="负责人" value={manual.owner} onChange={(e) => setManual((prev) => ({ ...prev, owner: e.target.value }))} />
                <input className="v2-input" placeholder="前端页面，逗号分隔" value={manual.frontend_pages} onChange={(e) => setManual((prev) => ({ ...prev, frontend_pages: e.target.value }))} />
                <textarea className="v2-textarea" placeholder="API 接口，逗号分隔" value={manual.api_interfaces} onChange={(e) => setManual((prev) => ({ ...prev, api_interfaces: e.target.value }))} />
                <textarea className="v2-textarea" placeholder="代码清单，逗号分隔" value={manual.code_items} onChange={(e) => setManual((prev) => ({ ...prev, code_items: e.target.value }))} />
                <textarea className="v2-textarea" placeholder="数据库表，逗号分隔" value={manual.database_tables} onChange={(e) => setManual((prev) => ({ ...prev, database_tables: e.target.value }))} />
                <textarea className="v2-textarea" placeholder="依赖服务，逗号分隔" value={manual.dependency_services} onChange={(e) => setManual((prev) => ({ ...prev, dependency_services: e.target.value }))} />
                <textarea className="v2-textarea" placeholder="监控清单，逗号分隔" value={manual.monitor_items} onChange={(e) => setManual((prev) => ({ ...prev, monitor_items: e.target.value }))} />
              </div>
              <div className="toolbar">
                <button className="btn" onClick={() => setManual({ asset_id: '', feature: '', domain: '', aggregate: '', frontend_pages: '', api_interfaces: '', code_items: '', database_tables: '', dependency_services: '', monitor_items: '', owner_team: '', owner: '' })}>清空</button>
                <button className="btn primary" onClick={() => void saveManual()}>保存资产</button>
              </div>
            </Panel>
          </div>
        </section>
      )}
    </>
  );
};

export default AssetsV2;
