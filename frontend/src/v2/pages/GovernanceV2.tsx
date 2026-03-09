import React, { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { governanceApi } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const GovernanceV2: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [systemCard, setSystemCard] = useState<Record<string, any>>({});
  const [quality, setQuality] = useState<Array<Record<string, any>>>([]);
  const [cost, setCost] = useState<Record<string, any>>({});
  const [remediationItems, setRemediationItems] = useState<Array<Record<string, any>>>([]);
  const [humanReview, setHumanReview] = useState<{ items: Array<Record<string, any>>; summary: Record<string, any> }>({ items: [], summary: {} });
  const [runtimeActive, setRuntimeActive] = useState('');
  const [runtimeProfiles, setRuntimeProfiles] = useState<Array<Record<string, any>>>([]);

  const load = async () => {
    setLoading(true);
    try {
      const [card, trend, estimate, remediation, review, runtimeRes, activeRes] = await Promise.all([
        governanceApi.systemCard(),
        governanceApi.qualityTrend(20),
        governanceApi.costEstimate(100),
        governanceApi.listRemediation(30),
        governanceApi.listHumanReview(50),
        governanceApi.runtimeStrategies(),
        governanceApi.runtimeStrategyActive(),
      ]);
      setSystemCard(card as Record<string, any>);
      setQuality((trend.items || []) as Array<Record<string, any>>);
      setCost(estimate as Record<string, any>);
      setRemediationItems((remediation.items || []) as Array<Record<string, any>>);
      setHumanReview({ items: (review.items || []) as Array<Record<string, any>>, summary: (review.summary || {}) as Record<string, any> });
      setRuntimeProfiles((runtimeRes.items || []) as Array<Record<string, any>>);
      setRuntimeActive(String(activeRes.active_profile || ''));
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载治理中心失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const latestQuality = quality[0] || {};
  const top1 = Number((latestQuality.summary || {}).top1_rate || 0);
  const timeoutRate = Number((latestQuality.summary || {}).timeout_rate || 0);
  const pendingReview = Number(humanReview.summary.pending || 0);
  const pendingActions = remediationItems.filter((item) => !['executed', 'closed', 'rolled_back'].includes(String(item.state || '').toLowerCase()));

  const switchProfile = async (profile: string) => {
    try {
      await governanceApi.updateRuntimeStrategyActive(profile);
      message.success('运行策略已更新');
      await load();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '运行策略切换失败');
    }
  };

  const recommendation = useMemo(() => {
    if (pendingReview > 0) return '当前有待人工审核会话，优先处理人工审核。';
    if (pendingActions.length > 0) return '当前有待执行或待审批修复动作，优先处理修复状态机。';
    if (timeoutRate > 0.15) return '最近超时率偏高，建议先检查队列和工具链健康度。';
    return '当前治理面整体稳定，可继续使用默认运行策略。';
  }, [pendingActions.length, pendingReview, timeoutRate]);

  return (
    <>
      <PageHeader
        title="运行治理中心"
        desc="真实读取 system card、质量趋势、修复状态机和人工审核信息，不再展示演示治理状态。"
        actions={
          <>
            <button className="btn" onClick={() => void load()} disabled={loading}>刷新治理状态</button>
            <button className="btn primary" onClick={() => runtimeProfiles[0] && void switchProfile(String(runtimeProfiles[0].name || runtimeActive))}>切换运行策略</button>
          </>
        }
      />

      <section className="grid-4" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        <div className="metric-card"><span className="eyebrow">Top1</span><strong>{(top1 * 100).toFixed(1)}%</strong><p>最近质量</p></div>
        <div className="metric-card"><span className="eyebrow">Timeout</span><strong>{(timeoutRate * 100).toFixed(1)}%</strong><p>最近超时率</p></div>
        <div className="metric-card"><span className="eyebrow">Human review</span><strong>{pendingReview}</strong><p>待人工审核</p></div>
        <div className="metric-card"><span className="eyebrow">Runtime</span><strong>{runtimeActive || '--'}</strong><p>当前运行策略</p></div>
      </section>

      <section className="data-grid">
        <Panel title="System Card" subtitle="真实 system card 摘要。">
          <div className="kv-list scroll-region compact-scroll">
            <div className="kv-item"><h5>能力边界</h5><p>{String(systemCard.capability_boundary || systemCard.summary || '暂无 system card 摘要')}</p></div>
            <div className="kv-item"><h5>当前判断</h5><p>{recommendation}</p></div>
            <div className="kv-item"><h5>成本估算</h5><p>{Object.keys(cost).length ? JSON.stringify(cost) : '暂无成本估算'}</p></div>
          </div>
        </Panel>
        <Panel title="修复状态机" subtitle="真实 remediation actions 列表。" extra={<Badge tone={pendingActions.length > 0 ? 'amber' : 'teal'}>{pendingActions.length} pending</Badge>}>
          <div className="scroll-region compact-scroll kv-list">
            {remediationItems.length === 0 ? <div className="empty-note">暂无修复动作。</div> : remediationItems.map((item) => (
              <div key={String(item.action_id || item.id || Math.random())} className="kv-item"><h5>{String(item.action_id || item.id || 'action')}</h5><p>{String(item.summary || '-')} · state={String(item.state || '-')}</p></div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="data-grid">
        <Panel title="人工审核" subtitle="真实 human-review 队列。">
          <div className="scroll-region compact-scroll status-grid">
            {humanReview.items.length === 0 ? <div className="empty-note">暂无人工审核队列。</div> : humanReview.items.map((item) => (
              <div key={String(item.session_id || Math.random())} className="status-row"><div><div className="status-name">{String(item.session_id || '-')}</div><div className="status-meta">{String(item.review_status || '-')} · {String(item.reason || item.comment || '-')}</div></div><Badge tone={String(item.review_status || '').toLowerCase() === 'pending' ? 'amber' : 'teal'}>{String(item.review_status || '-')}</Badge></div>
            ))}
          </div>
        </Panel>
        <Panel title="运行策略" subtitle="真实 runtime strategy 列表。">
          <div className="scroll-region compact-scroll kv-list">
            {runtimeProfiles.length === 0 ? <div className="empty-note">暂无运行策略配置。</div> : runtimeProfiles.map((item) => (
              <div key={String(item.name || Math.random())} className="kv-item"><h5>{String(item.name || '-')}</h5><p>{String(item.description || '-')} · {runtimeActive === String(item.name || '') ? `active · ${formatBeijingDateTime(new Date())}` : 'inactive'}</p></div>
            ))}
          </div>
        </Panel>
      </section>
    </>
  );
};

export default GovernanceV2;
