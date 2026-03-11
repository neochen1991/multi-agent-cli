import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, InputNumber, List, Row, Space, Statistic, Table, Tabs, Tag, Typography, message } from 'antd';
import { benchmarkApi, type BaselineFile, type BenchmarkRunResult } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Text, Title } = Typography;

const percentValue = (value: unknown) => Number(value || 0) * 100;
const percentText = (value: unknown, precision = 1) => `${percentValue(value).toFixed(precision)}%`;

const metricTone = (value: number, good: number, warning: number, inverse = false) => {
  if (inverse) {
    if (value <= good) return 'healthy';
    if (value <= warning) return 'watch';
    return 'risk';
  }
  if (value >= good) return 'healthy';
  if (value >= warning) return 'watch';
  return 'risk';
};

const toneLabel = (tone: string) => {
  if (tone === 'healthy') return '健康';
  if (tone === 'watch') return '关注';
  return '风险';
};

const BenchmarkCenterPage: React.FC = () => {
  const [limit, setLimit] = useState(3);
  const [timeoutSeconds, setTimeoutSeconds] = useState(240);
  const [loading, setLoading] = useState(false);
  const [latest, setLatest] = useState<BaselineFile | null>(null);
  const [history, setHistory] = useState<BaselineFile[]>([]);
  const [lastRun, setLastRun] = useState<BenchmarkRunResult | null>(null);

  const loadHistory = async () => {
    try {
      const [latestRes, listRes] = await Promise.all([benchmarkApi.latest(), benchmarkApi.list(20)]);
      setLatest(latestRes);
      setHistory(listRes || []);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '加载评测数据失败');
    }
  };

  const runBenchmark = async () => {
    setLoading(true);
    try {
      const result = await benchmarkApi.run(limit, timeoutSeconds);
      setLastRun(result);
      message.success('benchmark 执行完成');
      await loadHistory();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || 'benchmark 执行失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadHistory();
  }, []);

  const summary = lastRun?.summary || latest?.summary;
  const top1Rate = Number(summary?.top1_rate || 0);
  const overlapScore = Number(summary?.avg_overlap_score || 0);
  const timeoutRate = Number(summary?.timeout_rate || 0);
  const emptyConclusionRate = Number(summary?.empty_conclusion_rate || 0);
  const claimGraphQuality = Number(summary?.avg_claim_graph_quality_score || 0);
  const claimGraphSupportRate = Number(summary?.claim_graph_support_rate || 0);
  const claimGraphExclusionRate = Number(summary?.claim_graph_exclusion_rate || 0);
  const claimGraphMissingCheckRate = Number(summary?.claim_graph_missing_check_rate || 0);
  const latestFixtures = lastRun?.fixtures || 0;

  const top1Tone = metricTone(top1Rate, 0.75, 0.6);
  const overlapTone = metricTone(overlapScore, 0.65, 0.45);
  const timeoutTone = metricTone(timeoutRate, 0.08, 0.15, true);
  const emptyTone = metricTone(emptyConclusionRate, 0.05, 0.12, true);
  const claimGraphTone = metricTone(claimGraphQuality, 0.7, 0.5);

  const summaryCards = [
    {
      title: 'Top1 命中率',
      value: percentValue(top1Rate),
      precision: 1,
      suffix: '%',
      tone: top1Tone,
      hint: top1Tone === 'healthy' ? '根因命中表现稳定' : top1Tone === 'watch' ? '质量可用，但需继续关注' : '命中率偏低，建议先看样本明细',
    },
    {
      title: '平均重叠分',
      value: overlapScore,
      precision: 3,
      tone: overlapTone,
      hint: overlapTone === 'healthy' ? '预测结论与基线更接近' : overlapTone === 'watch' ? '部分 case 仍存在偏差' : '结论偏差较大，建议先复盘失败样本',
    },
    {
      title: '超时率',
      value: percentValue(timeoutRate),
      precision: 1,
      suffix: '%',
      tone: timeoutTone,
      hint: timeoutTone === 'healthy' ? '响应路径基本稳定' : timeoutTone === 'watch' ? '超时开始抬头，注意链路阻塞' : '超时偏高，策略或工具链可能不稳定',
    },
    {
      title: '空结论率',
      value: percentValue(emptyConclusionRate),
      precision: 1,
      suffix: '%',
      tone: emptyTone,
      hint: emptyTone === 'healthy' ? '结论完整性正常' : emptyTone === 'watch' ? '部分 case 结论不完整' : '空结论偏多，当前结果可信度下降',
    },
    {
      title: '最近运行样本数',
      value: latestFixtures || history.length || 0,
      tone: 'info',
      hint: lastRun ? '当前首屏指标来自本次运行结果' : '当前首屏指标来自最近基线文件',
    },
    {
      title: 'Claim Graph 质量',
      value: claimGraphQuality,
      precision: 3,
      tone: claimGraphTone,
      hint:
        claimGraphTone === 'healthy'
          ? '支持证据、排除项和待验证项整体较完整'
          : claimGraphTone === 'watch'
            ? '结构化证据图已可用，但仍有缺口'
            : '结构化证据图偏弱，建议优先看 supports / exclusions',
    },
  ];

  const recommendation = useMemo(() => {
    if (!summary) {
      return {
        tone: 'info',
        title: '先运行一次小样本 benchmark',
        description: '当前还没有可解读的质量摘要。建议先用 3 到 5 个样本快速跑一轮，确认质量和超时是否在可接受范围内。',
      };
    }
    if (timeoutTone === 'risk') {
      return {
        tone: 'risk',
        title: '先排查超时样本与上游依赖',
        description: `当前超时率为 ${percentText(timeoutRate)}，说明分析链路稳定性已经影响结果可信度。优先看“样本明细”里的 timeout case。`,
      };
    }
    if (emptyTone === 'risk' || top1Tone === 'risk') {
      return {
        tone: 'watch',
        title: '先复盘失败样本，再决定是否信任当前策略',
        description: '命中率或结论完整性已经出现明显下滑。建议先看失败样本，再去治理中心确认是否需要切策略。',
      };
    }
    return {
      tone: 'healthy',
      title: '当前质量基本稳定，可继续使用默认策略',
      description: '首屏指标没有明显异常。若准备变更模型、规则或策略，再运行一轮 benchmark 做回归校验。',
    };
  }, [emptyTone, summary, timeoutRate, timeoutTone, top1Tone]);

  const historyTrend = history.slice(0, 6).reverse().map((item) => ({
    label: String(item.generated_at || '').slice(5, 10),
    top1: Number(item.summary?.top1_rate || 0),
    timeout: Number(item.summary?.timeout_rate || 0),
    empty: Number(item.summary?.empty_conclusion_rate || 0),
  }));

  const baselineTop1 = Number(latest?.summary?.top1_rate || 0);
  const baselineTimeout = Number(latest?.summary?.timeout_rate || 0);
  const baselineEmpty = Number(latest?.summary?.empty_conclusion_rate || 0);
  const baselineClaimGraphQuality = Number(latest?.summary?.avg_claim_graph_quality_score || 0);

  const comparisonText = useMemo(() => {
    if (!lastRun || !latest?.summary) return null;
    const latestSummary = latest.summary;
    const top1Delta = top1Rate - Number(latestSummary.top1_rate || 0);
    const timeoutDelta = timeoutRate - Number(latestSummary.timeout_rate || 0);
    return `相对最近基线：Top1 ${top1Delta >= 0 ? '+' : ''}${(top1Delta * 100).toFixed(1)}%，timeout ${timeoutDelta >= 0 ? '+' : ''}${(timeoutDelta * 100).toFixed(1)}%`;
  }, [lastRun, latest?.summary, timeoutRate, top1Rate]);

  const tabs = [
    {
      key: 'overview',
      label: '结果总览',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="module-card ops-section-card" size="small">
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                如何读这页
              </Title>
              <Text type="secondary">
                先看首屏四个质量信号，再看下面的解释。如果首屏已经是红色，不要急着跑更多 benchmark，先确认是策略问题还是工具链超时。
              </Text>
              {comparisonText ? <Alert type="info" showIcon message="与最近基线对比" description={comparisonText} /> : null}
            </Space>
          </Card>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card className="module-card ops-section-card" size="small">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    当前判断
                  </Title>
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={[
                      `Top1 命中率：${percentText(top1Rate)}，状态为${toneLabel(top1Tone)}。`,
                      `平均重叠分：${overlapScore.toFixed(3)}，越高表示预测结论越接近基线。`,
                      `超时率：${percentText(timeoutRate)}，偏高时先看慢链路和工具调用。`,
                      `空结论率：${percentText(emptyConclusionRate)}，偏高时说明答案完整性下降。`,
                    ]}
                    renderItem={(item) => <List.Item>{item}</List.Item>}
                  />
                </Space>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card className="module-card ops-section-card" size="small">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    当前数据来源
                  </Title>
                  <Text type="secondary">
                    {lastRun
                      ? `本次运行生成于 ${formatBeijingDateTime(lastRun.generated_at)}，样本数 ${lastRun.fixtures}。`
                      : latest
                        ? `当前展示的是最近基线 ${formatBeijingDateTime(latest.generated_at)}。`
                        : '当前还没有基线文件。'}
                  </Text>
                  {latest ? (
                    <Alert
                      type="info"
                      showIcon
                      message="最近基线"
                      description={`${latest.file} · Top1 ${percentText(latest.summary.top1_rate)} · timeout ${percentText(latest.summary.timeout_rate)}`}
                    />
                  ) : null}
                  <Card size="small" className="ops-subtle-block mini-chart-card">
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      <Text strong>最近基线趋势</Text>
                      <div className="mini-trend-strip">
                        {historyTrend.length === 0 ? (
                          <Text type="secondary">暂无趋势数据</Text>
                        ) : (
                          historyTrend.map((item) => (
                            <div key={item.label} className="mini-trend-group">
                              <div className="mini-trend-stack">
                                <div className="mini-trend-segment tone-healthy" style={{ height: `${Math.max(10, item.top1 * 80)}px` }} />
                                <div className="mini-trend-segment tone-watch" style={{ height: `${Math.max(6, item.timeout * 80)}px` }} />
                                <div className="mini-trend-segment tone-risk" style={{ height: `${Math.max(6, item.empty * 80)}px` }} />
                              </div>
                              <Text type="secondary">{item.label}</Text>
                            </div>
                          ))
                        )}
                      </div>
                    </Space>
                  </Card>
                  <Card size="small" className="ops-subtle-block mini-chart-card">
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      <Text strong>结构化证据图质量</Text>
                      <List
                        size="small"
                        className="ops-list-tight"
                        dataSource={[
                          `平均质量分：${claimGraphQuality.toFixed(3)}`,
                          `支持证据达标率：${percentText(claimGraphSupportRate)}`,
                          `排除项达标率：${percentText(claimGraphExclusionRate)}`,
                          `待验证项达标率：${percentText(claimGraphMissingCheckRate)}`,
                        ]}
                        renderItem={(item) => <List.Item>{item}</List.Item>}
                      />
                    </Space>
                  </Card>
                </Space>
              </Card>
            </Col>
          </Row>

          <Card className="module-card ops-section-card" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                本次结果与最近基线对比
              </Title>
              <div className="mini-bar-list">
                {[
                  { label: 'Top1 命中率', current: top1Rate, baseline: baselineTop1, inverse: false },
                  { label: '超时率', current: timeoutRate, baseline: baselineTimeout, inverse: true },
                  { label: '空结论率', current: emptyConclusionRate, baseline: baselineEmpty, inverse: true },
                  { label: 'Claim Graph 质量', current: claimGraphQuality, baseline: baselineClaimGraphQuality, inverse: false },
                ].map((item) => (
                  <div key={item.label} className="mini-compare-row">
                    <div className="mini-bar-label-wrap">
                      <Text strong>{item.label}</Text>
                      <Text type="secondary">
                        当前 {percentText(item.current)} / 基线 {percentText(item.baseline)}
                      </Text>
                    </div>
                    <div className="mini-compare-bars">
                      <div className="mini-bar-track">
                        <div className={`mini-bar-fill ${item.inverse ? 'tone-watch' : 'tone-healthy'}`} style={{ width: `${Math.max(8, item.current * 100)}%` }} />
                      </div>
                      <div className="mini-bar-track muted">
                        <div className="mini-bar-fill tone-info" style={{ width: `${Math.max(8, item.baseline * 100)}%` }} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Space>
          </Card>
        </Space>
      ),
    },
    {
      key: 'cases',
      label: '样本明细',
      children: (
        <Card className="module-card ops-section-card" size="small">
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Title level={5} style={{ margin: 0 }}>
              最近运行结果
            </Title>
            <Text type="secondary">先看 status 和 overlap score，再看根因摘要，优先找 timeout、empty 或 overlap 低的样本。</Text>
            <Table
              rowKey={(row: any) => String(row.fixture_id || row.session_id || Math.random())}
              dataSource={lastRun?.cases || []}
              pagination={{ pageSize: 6 }}
              columns={[
                { title: '样本', dataIndex: 'fixture_id', key: 'fixture_id', width: 160 },
                {
                  title: '状态',
                  dataIndex: 'status',
                  key: 'status',
                  width: 120,
                  render: (v: string) => <Tag color={v === 'timeout' ? 'red' : v === 'ok' ? 'green' : 'default'}>{v}</Tag>,
                },
                { title: '命中分', dataIndex: 'overlap_score', key: 'overlap_score', width: 120 },
                { title: '耗时(ms)', dataIndex: 'duration_ms', key: 'duration_ms', width: 140 },
                { title: '根因摘要', dataIndex: 'predicted_root_cause', key: 'predicted_root_cause' },
              ]}
              locale={{ emptyText: '先运行一次 benchmark，样本明细才会出现。' }}
            />
          </Space>
        </Card>
      ),
    },
    {
      key: 'history',
      label: '历史趋势',
      children: (
        <Card className="module-card ops-section-card" size="small">
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Title level={5} style={{ margin: 0 }}>
              历史基线
            </Title>
            <Text type="secondary">这里不是单纯文件列表，而是用来判断最近几次质量是否在退化。</Text>
            <List
              size="small"
              className="ops-list-tight"
              dataSource={history}
              renderItem={(item, index) => {
                const itemTop1 = Number(item.summary?.top1_rate || 0);
                const itemTimeout = Number(item.summary?.timeout_rate || 0);
                const tone = metricTone(itemTop1, 0.75, 0.6);
                return (
                  <List.Item>
                    <Space direction="vertical" size={2}>
                      <Space wrap>
                        <Text strong>{item.file}</Text>
                        {index === 0 ? <Tag color="blue">最近基线</Tag> : null}
                        <Tag color={tone === 'healthy' ? 'green' : tone === 'watch' ? 'orange' : 'red'}>{toneLabel(tone)}</Tag>
                      </Space>
                      <Text type="secondary">
                        {formatBeijingDateTime(item.generated_at)} · Top1 {percentText(itemTop1)} · timeout {percentText(itemTimeout)} ·
                        空结论 {percentText(item.summary?.empty_conclusion_rate)}
                      </Text>
                    </Space>
                  </List.Item>
                );
              }}
            />
          </Space>
        </Card>
      ),
    },
  ];

  return (
    <div className="benchmark-page">
      <Card className="module-card ops-hero-card">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="blue">值班 SRE</Tag>
            <Tag color="default">平台治理负责人</Tag>
          </Space>
          <div>
            <Title level={3} style={{ margin: 0 }}>
              质量评估
            </Title>
            <Paragraph className="ops-hero-description">
              这页用来判断最近分析质量有没有变差、当前结果值不值得信任、以及模型或策略变更后是否出现回归。
            </Paragraph>
            <Text type="secondary">
              最近基线：{latest ? formatBeijingDateTime(latest.generated_at) : '暂无'} · 当前运行配置：样本 {limit}，超时 {timeoutSeconds} 秒
            </Text>
          </div>
          <div className="ops-question-list">
            <Tag>最近质量是否变差</Tag>
            <Tag>当前空结论和超时是否可接受</Tag>
            <Tag>是否需要复盘失败样本</Tag>
          </div>
        </Space>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {summaryCards.map((card) => (
          <Col xs={24} sm={12} xl={8} key={card.title}>
            <Card className={`module-card ops-summary-card tone-${card.tone}`} size="small">
              <Statistic title={card.title} value={card.value as any} precision={card.precision as any} suffix={card.suffix as any} />
              <Text className="ops-summary-hint">{card.hint}</Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={17}>
          <Card className={`module-card ops-recommend-card tone-${recommendation.tone}`}>
            <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Text strong>处置建议</Text>
              <Title level={5} style={{ margin: 0 }}>
                {recommendation.title}
              </Title>
              <Text type="secondary">{recommendation.description}</Text>
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={7}>
          <Card className="module-card ops-action-card benchmark-run-card">
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <div>
                <Title level={5} style={{ margin: 0 }}>
                  运行 Benchmark
                </Title>
                <Text type="secondary">准备变更模型、策略、prompt 或规则时，再跑一轮 benchmark 做回归校验。</Text>
              </div>
              <Space wrap>
                <Text>样本数</Text>
                <InputNumber min={1} max={20} value={limit} onChange={(v) => setLimit(Number(v || 3))} />
              </Space>
              <Space wrap>
                <Text>超时(秒)</Text>
                <InputNumber min={30} max={1200} value={timeoutSeconds} onChange={(v) => setTimeoutSeconds(Number(v || 240))} />
              </Space>
              <Button type="primary" loading={loading} onClick={() => void runBenchmark()}>
                运行 Benchmark
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>

      <div style={{ marginTop: 16 }}>
        <Tabs className="incident-workspace-tabs" items={tabs} />
      </div>
    </div>
  );
};

export default BenchmarkCenterPage;
