import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { benchmarkApi, governanceApi, settingsApi } from '@/services/api';

const AdvancedV2: React.FC = () => {
  const navigate = useNavigate();
  const [benchmarkLatest, setBenchmarkLatest] = useState<Record<string, any> | null>(null);
  const [connectors, setConnectors] = useState<Array<Record<string, any>>>([]);
  const [remediation, setRemediation] = useState<Array<Record<string, any>>>([]);

  useEffect(() => {
    Promise.all([
      benchmarkApi.latest().catch(() => null),
      governanceApi.qualityTrend(10).catch(() => ({ items: [] })),
      settingsApi.getToolConnectors().catch(() => []),
      governanceApi.listRemediation(20).catch(() => ({ items: [] })),
    ]).then(([latest, _trend, connectorRes, remediationRes]) => {
      setBenchmarkLatest((latest || null) as Record<string, any> | null);
      setConnectors((connectorRes || []) as Array<Record<string, any>>);
      setRemediation((remediationRes.items || []) as Array<Record<string, any>>);
    }).catch((error: any) => {
      message.error(error?.response?.data?.detail || error?.message || '加载高级概览失败');
    });
  }, []);

  const top1 = Number((benchmarkLatest?.summary || {}).top1_rate || 0);
  const timeoutRate = Number((benchmarkLatest?.summary || {}).timeout_rate || 0);
  const unhealthyConnectors = connectors.filter((item) => item.healthy === false || ['error', 'disconnected'].includes(String(item.status || '').toLowerCase())).length;
  const pendingActions = remediation.filter((item) => !['executed', 'closed', 'rolled_back'].includes(String(item.state || '').toLowerCase())).length;

  const guides = useMemo(() => ([
    { q: '某个 session 为什么这样下结论？', a: '进入调查复盘台', link: '/v2/replay' },
    { q: '最近 TimeoutError 变多，是模型还是系统问题？', a: '进入运行治理中心', link: '/v2/governance' },
    { q: '改了 prompt 后命中率有没有回退？', a: '进入质量评估中心', link: '/v2/benchmark' },
    { q: '工具结果不可信，想确认连接状态', a: '进入工具中心', link: '/v2/tools' },
  ]), []);
  const subCenters = useMemo(
    () => [
      {
        key: '/v2/tools',
        title: '工具中心',
        desc: '查看连接器健康、工具清单和调用审计。',
      },
      {
        key: '/v2/replay',
        title: '调查回放',
        desc: '按 session 回放关键决策路径与证据引用。',
      },
      {
        key: '/v2/benchmark',
        title: 'Benchmark',
        desc: '评估 Top1/Top3、超时率与回归风险。',
      },
      {
        key: '/v2/governance',
        title: '治理中心',
        desc: '处理修复动作、审批流与执行结果审计。',
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        title="高级控制中心"
        desc="这里不再放假摘要，只做真实入口汇总：治理、评测、工具和复盘四个子中心的当前状态。"
        actions={
          <>
            <button className="btn" onClick={() => navigate('/v2/governance')}>进入治理中心</button>
            <button className="btn primary" onClick={() => navigate('/v2/tools')}>进入工具中心</button>
          </>
        }
      />

      <section className="grid-4" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        <div className="metric-card"><span className="eyebrow">Top1</span><strong>{(top1 * 100).toFixed(1)}%</strong><p>最近 Benchmark</p></div>
        <div className="metric-card"><span className="eyebrow">Timeout</span><strong>{(timeoutRate * 100).toFixed(1)}%</strong><p>最近超时率</p></div>
        <div className="metric-card"><span className="eyebrow">Connectors</span><strong>{connectors.length - unhealthyConnectors}/{connectors.length}</strong><p>健康连接器</p></div>
        <div className="metric-card"><span className="eyebrow">Actions</span><strong>{pendingActions}</strong><p>待处理修复动作</p></div>
      </section>

      <section className="grid-4" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        {subCenters.map((item) => (
          <Panel key={item.key} title={item.title} subtitle={item.desc}>
            <button className="btn primary" onClick={() => navigate(item.key)}>进入 {item.title}</button>
          </Panel>
        ))}
      </section>

      <section className="data-grid">
        <Panel title="场景指引" subtitle="保留入口语义，但每条指引都对应真实中心。">
          <div className="kv-list">
            {guides.map((item) => (
              <div key={item.link} className="kv-item"><h5>{item.q}</h5><p><button className="v2-plain-link" onClick={() => navigate(item.link)}>{item.a}</button></p></div>
            ))}
          </div>
        </Panel>
        <Panel title="运行摘要" subtitle="来自真实 benchmark / governance / connector 数据。">
          <div className="status-grid scroll-region compact-scroll">
            <div className="status-row"><div><div className="status-name">治理状态</div><div className="status-meta">{pendingActions > 0 ? `有 ${pendingActions} 个修复动作待处理` : '当前无待处理修复动作'}</div></div><Badge tone={pendingActions > 0 ? 'amber' : 'teal'}>{pendingActions > 0 ? 'watch' : 'healthy'}</Badge></div>
            <div className="status-row"><div><div className="status-name">评测状态</div><div className="status-meta">Top1 {(top1 * 100).toFixed(1)}%，timeout {(timeoutRate * 100).toFixed(1)}%</div></div><Badge tone={top1 >= 0.75 && timeoutRate <= 0.08 ? 'teal' : 'amber'}>{top1 >= 0.75 && timeoutRate <= 0.08 ? 'healthy' : 'watch'}</Badge></div>
            <div className="status-row"><div><div className="status-name">工具状态</div><div className="status-meta">{connectors.length} connectors，异常 {unhealthyConnectors}</div></div><Badge tone={unhealthyConnectors > 0 ? 'amber' : 'teal'}>{unhealthyConnectors > 0 ? 'watch' : 'healthy'}</Badge></div>
          </div>
        </Panel>
      </section>
    </>
  );
};

export default AdvancedV2;
