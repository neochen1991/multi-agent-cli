import React, { useEffect, useState } from 'react';
import { message } from 'antd';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { benchmarkApi, type BaselineFile, type BenchmarkRunResult } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const BenchmarkV2: React.FC = () => {
  const [limit, setLimit] = useState(3);
  const [timeoutSeconds, setTimeoutSeconds] = useState(240);
  const [loading, setLoading] = useState(false);
  const [latest, setLatest] = useState<BaselineFile | null>(null);
  const [history, setHistory] = useState<BaselineFile[]>([]);
  const [lastRun, setLastRun] = useState<BenchmarkRunResult | null>(null);

  const load = async () => {
    try {
      const [latestRes, listRes] = await Promise.all([benchmarkApi.latest(), benchmarkApi.list(20)]);
      setLatest(latestRes);
      setHistory(listRes || []);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载 Benchmark 数据失败');
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const runBenchmark = async () => {
    setLoading(true);
    try {
      const result = await benchmarkApi.run(limit, timeoutSeconds);
      setLastRun(result);
      message.success('Benchmark 执行完成');
      await load();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || 'Benchmark 执行失败');
    } finally {
      setLoading(false);
    }
  };

  const summary = lastRun?.summary || latest?.summary;
  const top1 = Number(summary?.top1_rate || 0);
  const timeoutRate = Number(summary?.timeout_rate || 0);
  const emptyRate = Number(summary?.empty_conclusion_rate || 0);
  const recommendation = top1 >= 0.75 && timeoutRate <= 0.08 ? '当前质量稳定，可继续使用默认策略。' : timeoutRate > 0.15 ? '超时偏高，优先排查链路与工具调用。' : '命中率或完整性一般，建议先看样本明细。';

  return (
    <>
      <PageHeader
        title="质量评估中心"
        desc="真实读取 benchmark 基线与最近运行结果。先给出当前判断，再展开趋势和样本。"
        actions={
          <>
            <button className="btn" onClick={() => void load()}>查看最近基线</button>
            <button className="btn primary" onClick={() => void runBenchmark()} disabled={loading}>{loading ? '运行中...' : '运行 Benchmark'}</button>
          </>
        }
      />

      <Panel title="运行参数" subtitle="真实运行 benchmark，不再使用静态样例。">
        <div className="toolbar">
          <input className="v2-input" value={String(limit)} onChange={(e) => setLimit(Number(e.target.value || 1))} placeholder="样本数" />
          <input className="v2-input" value={String(timeoutSeconds)} onChange={(e) => setTimeoutSeconds(Number(e.target.value || 240))} placeholder="超时秒数" />
        </div>
      </Panel>

      <section className="grid-4">
        <div className="metric-card"><span className="eyebrow">Top1</span><strong>{(top1 * 100).toFixed(1)}%</strong><p>根因命中率</p></div>
        <div className="metric-card"><span className="eyebrow">Timeout</span><strong>{(timeoutRate * 100).toFixed(1)}%</strong><p>超时率</p></div>
        <div className="metric-card"><span className="eyebrow">Empty</span><strong>{(emptyRate * 100).toFixed(1)}%</strong><p>空结论率</p></div>
        <div className="metric-card"><span className="eyebrow">Fixtures</span><strong>{lastRun?.fixtures || 0}</strong><p>最近运行样本数</p></div>
      </section>

      <section className="data-grid">
        <Panel title="当前判断" subtitle="把指标翻译成可执行判断。" extra={<Badge tone={top1 >= 0.75 && timeoutRate <= 0.08 ? 'teal' : timeoutRate > 0.15 ? 'red' : 'amber'}>{summary ? 'real data' : 'empty'}</Badge>}>
          <div className="kv-list">
            <div className="kv-item"><h5>结论</h5><p>{recommendation}</p></div>
            <div className="kv-item"><h5>Gate 建议</h5><p>{timeoutRate > 0.15 || emptyRate > 0.12 ? '建议阻断回归并先复盘失败样本。' : '当前不建议阻断发布。'}</p></div>
            <div className="kv-item"><h5>数据来源</h5><p>{lastRun ? `本次运行：${formatBeijingDateTime(lastRun.generated_at)}` : latest ? `最近基线：${formatBeijingDateTime(latest.generated_at)}` : '暂无数据'}</p></div>
          </div>
        </Panel>
        <Panel title="最近基线趋势" subtitle="基于真实 baseline 列表渲染。">
          <div className="three-col scroll-region compact-scroll">
            {history.length === 0 ? <div className="empty-note">暂无 baseline 历史。</div> : history.slice(0, 6).map((item) => (
              <div key={item.file} className="mini-panel"><h4>{String(item.generated_at || '').slice(5, 10)}</h4><p>Top1 {(Number(item.summary?.top1_rate || 0) * 100).toFixed(1)}%<br />timeout {(Number(item.summary?.timeout_rate || 0) * 100).toFixed(1)}%</p></div>
            ))}
          </div>
        </Panel>
      </section>

      <Panel title="样本明细" subtitle="真实运行后展示 case 结果，过多时内部滚动。">
        <div className="table-scroll compact-scroll">
          <table className="table">
            <thead><tr><th>样本</th><th>状态</th><th>重叠分</th><th>耗时</th><th>根因摘要</th></tr></thead>
            <tbody>
              {(lastRun?.cases || []).map((item: any, index) => (
                <tr key={`${item.fixture_id || index}`}><td>{String(item.fixture_id || item.session_id || index)}</td><td>{String(item.status || '-')}</td><td>{String(item.overlap_score || '-')}</td><td>{String(item.duration_ms || '-')}</td><td>{String(item.predicted_root_cause || '-')}</td></tr>
              ))}
            </tbody>
          </table>
          {!(lastRun?.cases || []).length ? <div className="empty-note">先运行一次 Benchmark，样本明细才会出现。</div> : null}
        </div>
      </Panel>
    </>
  );
};

export default BenchmarkV2;
