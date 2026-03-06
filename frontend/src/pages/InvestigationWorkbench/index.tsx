import React, { useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Empty, Input, List, Row, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd';
import {
  debateApi,
  lineageApi,
  reportApi,
  settingsApi,
  type DebateResult,
  type LineageResponse,
  type ReportDiff,
  type ReportVersion,
  type ToolAuditResponse,
} from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Text, Title } = Typography;

const percent = (value: unknown, precision = 1) => `${(Number(value || 0) * 100).toFixed(precision)}%`;

const InvestigationWorkbenchPage: React.FC = () => {
  const [sessionId, setSessionId] = useState('');
  const [incidentId, setIncidentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<LineageResponse | null>(null);
  const [rendered, setRendered] = useState<string[]>([]);
  const [keyDecisions, setKeyDecisions] = useState<Array<Record<string, any>>>([]);
  const [evidenceRefs, setEvidenceRefs] = useState<string[]>([]);
  const [toolAudit, setToolAudit] = useState<ToolAuditResponse | null>(null);
  const [debateResult, setDebateResult] = useState<DebateResult | null>(null);
  const [reportVersions, setReportVersions] = useState<ReportVersion[]>([]);
  const [reportDiff, setReportDiff] = useState<ReportDiff | null>(null);
  const [replayPhaseFilter, setReplayPhaseFilter] = useState<string>('all');
  const [replayAgentFilter, setReplayAgentFilter] = useState<string>('all');

  const load = async () => {
    const id = sessionId.trim();
    if (!id) {
      message.warning('请输入会话ID');
      return;
    }
    setLoading(true);
    try {
      const [lineage, replay, audit, result] = await Promise.all([
        lineageApi.get(id, 300),
        lineageApi.replay(id, 120, {
          phase: replayPhaseFilter === 'all' ? '' : replayPhaseFilter,
          agent: replayAgentFilter === 'all' ? '' : replayAgentFilter,
        }),
        settingsApi.getToolAudit(id).catch(() => null),
        debateApi.getResult(id).catch(() => null),
      ]);
      setSummary(lineage);
      setRendered(replay.rendered_steps || []);
      setKeyDecisions((replay.key_decisions || []) as Array<Record<string, any>>);
      setEvidenceRefs((replay.evidence_refs || []) as string[]);
      setToolAudit(audit);
      setDebateResult(result);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '加载调查数据失败');
    } finally {
      setLoading(false);
    }
  };

  const loadReportVersions = async () => {
    const id = incidentId.trim();
    if (!id) {
      message.warning('请输入 incident_id');
      return;
    }
    try {
      const items = await reportApi.compare(id);
      setReportVersions(items || []);
      const diff = await reportApi.compareDiff(id);
      setReportDiff(diff);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '报告版本加载失败');
    }
  };

  const replayAgentOptions = useMemo(() => {
    const all = ['all'];
    const summaryAgents = Array.isArray(summary?.agents) ? summary.agents.map((item) => String(item || '').trim()) : [];
    const decisionAgents = keyDecisions.map((row) => String(row.agent || '').trim()).filter(Boolean);
    const agents = [...summaryAgents, ...decisionAgents].filter(Boolean);
    return [...all, ...Array.from(new Set(agents))];
  }, [summary, keyDecisions]);

  const sessionStatus = String((debateResult as any)?.status || '');
  const confidence = Number(debateResult?.confidence || 0);
  const crossSourcePassed = Boolean(debateResult?.cross_source_passed);
  const toolCallCount = Number(toolAudit?.items?.length || 0);
  const reportVersionCount = reportVersions.length;
  const timelineCount = Number(summary?.items?.length || 0);
  const replayLoaded = Boolean(summary || debateResult || rendered.length || keyDecisions.length);
  const firstReplaySteps = rendered.slice(0, 6);
  const firstTimelineItems = Array.isArray(summary?.items) ? summary.items.slice(0, 60) : [];
  const firstToolItems = toolAudit?.items?.slice(0, 60) || [];
  const phaseDistribution = Array.isArray(summary?.items)
    ? Object.entries(
        summary.items.reduce<Record<string, number>>((acc, row) => {
          const phase = String((row as any).phase || 'unknown');
          acc[phase] = (acc[phase] || 0) + 1;
          return acc;
        }, {}),
      )
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .map(([label, value]) => ({ label, value }))
    : [];

  const recommendation = useMemo(() => {
    if (reportDiff) {
      return {
        tone: 'watch',
        title: '先看报告版本差异',
        description: '当前已经有报告 diff，优先确认不同版本是否在根因判断或结论措辞上出现明显偏差。',
      };
    }
    if (debateResult && (!crossSourcePassed || confidence < 0.7)) {
      return {
        tone: 'risk',
        title: '先看关键决策',
        description: '当前置信度偏低或跨源证据未通过，建议优先复盘关键决策和时间线，确认主 Agent 是否在证据不足时过早收敛。',
      };
    }
    if (toolCallCount >= 10) {
      return {
        tone: 'watch',
        title: '先看证据与工具',
        description: '当前工具调用较多，建议优先核对工具调用记录和证据引用，确认是否有噪声调用或慢链路。',
      };
    }
    return {
      tone: 'healthy',
      title: '先看复盘总览',
      description: '当前没有明显的高风险信号，可以先看结论、证据链和前几步回放，快速理解这次 session 的主线。',
    };
  }, [confidence, crossSourcePassed, debateResult, reportDiff, toolCallCount]);

  const summaryCards = [
    {
      title: '会话状态',
      value: sessionStatus || (replayLoaded ? '已加载' : '待加载'),
      hint: replayLoaded ? '会话轨迹和复盘内容已可查看' : '先输入 session_id 加载会话',
      tone: replayLoaded ? 'info' : 'watch',
    },
    {
      title: '根因结论',
      value: String(debateResult?.root_cause || '暂无'),
      hint: debateResult ? '这是当前 session 收敛出的最终根因' : '尚未拿到最终辩论结论',
      tone: debateResult ? 'healthy' : 'watch',
    },
    {
      title: '置信度',
      value: percent(confidence),
      hint: crossSourcePassed ? '跨源证据已通过' : '跨源证据未通过，建议继续核查',
      tone: confidence >= 0.8 && crossSourcePassed ? 'healthy' : confidence >= 0.6 ? 'watch' : 'risk',
    },
    {
      title: '关键决策数',
      value: keyDecisions.length,
      hint: '用于判断主 Agent 何时下结论、是否有明显偏航',
      tone: keyDecisions.length > 0 ? 'info' : 'watch',
    },
    {
      title: '工具调用数',
      value: toolCallCount,
      hint: toolCallCount > 0 ? '用于排查慢链路和噪声调用' : '当前没有工具调用审计记录',
      tone: toolCallCount > 0 ? 'info' : 'watch',
    },
    {
      title: '报告版本数',
      value: reportVersionCount,
      hint: reportVersionCount > 0 ? '可用于对比不同报告版本差异' : '尚未加载 incident 报告版本',
      tone: reportVersionCount > 0 ? 'info' : 'watch',
    },
  ];

  const tabs = [
    {
      key: 'overview',
      label: '复盘总览',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={11}>
              <Card className="module-card ops-section-card" size="small">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    当前结论
                  </Title>
                  {!debateResult ? (
                    <Empty description="暂无辩论结论，请先加载会话或等待分析完成" />
                  ) : (
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      <Text strong>{String(debateResult.root_cause || '暂无根因')}</Text>
                      <Space wrap>
                        <Tag color="processing">置信度 {percent(confidence)}</Tag>
                        <Tag color={crossSourcePassed ? 'green' : 'orange'}>
                          跨源证据{crossSourcePassed ? '通过' : '未通过'}
                        </Tag>
                        <Tag color="blue">
                          Top-K {Array.isArray(debateResult.root_cause_candidates) ? debateResult.root_cause_candidates.length : 0}
                        </Tag>
                      </Space>
                      <Alert
                        type={crossSourcePassed && confidence >= 0.8 ? 'success' : confidence >= 0.6 ? 'warning' : 'error'}
                        showIcon
                        message="怎么看这个结论"
                        description="先看置信度和跨源状态，再决定是否继续核查关键决策或工具调用。"
                      />
                    </Space>
                  )}
                </Space>
              </Card>
            </Col>

            <Col xs={24} xl={13}>
              <Card className="module-card ops-section-card" size="small">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    关键证据链
                  </Title>
                  {Array.isArray(debateResult?.evidence_chain) && debateResult.evidence_chain.length > 0 ? (
                    <List
                      size="small"
                      className="ops-list-tight"
                      dataSource={debateResult.evidence_chain.slice(0, 8)}
                      renderItem={(item) => (
                        <List.Item>
                          <Space direction="vertical" size={0} style={{ width: '100%' }}>
                            <Text>{item.description}</Text>
                            <Text type="secondary">
                              {String(item.source || '-')} {item.source_ref ? `· ${String(item.source_ref)}` : ''}
                            </Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Alert type="info" showIcon message="暂无证据链" />
                  )}
                </Space>
              </Card>
            </Col>
          </Row>

          <Card className="module-card ops-section-card" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                前几步回放
              </Title>
              <Text type="secondary">适合第一次看这次 session 时快速建立上下文，不需要先读完整时间线。</Text>
              {firstReplaySteps.length === 0 ? (
                <Empty description="暂无回放数据，先输入会话ID加载" />
              ) : (
                <List
                  size="small"
                  className="ops-list-tight"
                  dataSource={firstReplaySteps}
                  renderItem={(item, index) => (
                    <List.Item>
                      <Space direction="vertical" size={0} style={{ width: '100%' }}>
                        <Text strong>步骤 {index + 1}</Text>
                        <Text>{item}</Text>
                      </Space>
                    </List.Item>
                  )}
                />
              )}
            </Space>
          </Card>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card className="module-card ops-section-card mini-chart-card" size="small">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    复盘密度摘要
                  </Title>
                  <div className="mini-bar-list">
                    {[
                      { label: '关键决策', value: keyDecisions.length, tone: 'tone-healthy' },
                      { label: '工具调用', value: toolCallCount, tone: 'tone-watch' },
                      { label: '时间线条目', value: timelineCount, tone: 'tone-info' },
                    ].map((item) => (
                      <div key={item.label} className="mini-bar-row">
                        <div className="mini-bar-label-wrap">
                          <Text strong>{item.label}</Text>
                          <Text type="secondary">{item.value}</Text>
                        </div>
                        <div className="mini-bar-track">
                          <div
                            className={`mini-bar-fill ${item.tone}`}
                            style={{ width: `${Math.max(10, (item.value / Math.max(keyDecisions.length, toolCallCount, timelineCount, 1)) * 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </Space>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card className="module-card ops-section-card mini-chart-card" size="small">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    阶段分布
                  </Title>
                  <div className="mini-bar-list">
                    {phaseDistribution.length === 0 ? (
                      <Text type="secondary">暂无阶段分布数据</Text>
                    ) : (
                      phaseDistribution.map((item) => (
                        <div key={item.label} className="mini-bar-row">
                          <div className="mini-bar-label-wrap">
                            <Text strong>{item.label}</Text>
                            <Text type="secondary">{item.value}</Text>
                          </div>
                          <div className="mini-bar-track">
                            <div
                              className="mini-bar-fill tone-risk"
                              style={{ width: `${Math.max(10, (item.value / Math.max(...phaseDistribution.map((row) => row.value), 1)) * 100)}%` }}
                            />
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </Space>
              </Card>
            </Col>
          </Row>
        </Space>
      ),
    },
    {
      key: 'decisions',
      label: '关键决策',
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={10}>
            <Card className="module-card ops-section-card" size="small">
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Title level={5} style={{ margin: 0 }}>
                  关键决策路径
                </Title>
                <Text type="secondary">看主 Agent 在什么阶段给出哪些判断，以及这些判断是否过早或缺证据。</Text>
                {keyDecisions.length === 0 ? (
                  <Empty description="暂无关键决策数据" />
                ) : (
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={keyDecisions}
                    renderItem={(item) => (
                      <List.Item>
                        <Space direction="vertical" size={0}>
                          <Text strong>
                            {String(item.agent || '-')} · {String(item.phase || '-')}
                          </Text>
                          <Text>{String(item.conclusion || '-')}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                )}
              </Space>
            </Card>
          </Col>
          <Col xs={24} xl={14}>
            <Card className="module-card ops-section-card" size="small">
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Title level={5} style={{ margin: 0 }}>
                  实时时间线
                </Title>
                <Text type="secondary">结合阶段和 Agent 过滤器看完整过程，确认哪一段最值得怀疑。</Text>
                {firstTimelineItems.length > 0 ? (
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={firstTimelineItems}
                    renderItem={(row) => (
                      <List.Item>
                        <Space direction="vertical" size={0} style={{ width: '100%' }}>
                          <Text strong>
                            [{formatBeijingDateTime(String(row.timestamp || ''))}] {String(row.event_type || row.kind || '-')}
                          </Text>
                          <Text type="secondary">
                            {String(row.agent_name || '-')} · {String(row.phase || '-')}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description="暂无时间线数据" />
                )}
              </Space>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'evidence-tools',
      label: '证据与工具',
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={9}>
            <Card className="module-card ops-section-card" size="small">
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Title level={5} style={{ margin: 0 }}>
                  证据引用
                </Title>
                <Text type="secondary">确认当前结论引用了哪些证据位置，是否存在关键证据缺失。</Text>
                {evidenceRefs.length === 0 ? (
                  <Empty description="暂无证据引用" />
                ) : (
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={evidenceRefs}
                    renderItem={(item) => (
                      <List.Item>
                        <Text code>{item}</Text>
                      </List.Item>
                    )}
                  />
                )}
              </Space>
            </Card>
          </Col>
          <Col xs={24} xl={15}>
            <Card className="module-card ops-section-card" size="small">
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Title level={5} style={{ margin: 0 }}>
                  工具调用记录
                </Title>
                <Text type="secondary">当你怀疑慢链路、噪声调用或工具结果不稳定时，优先看这里。</Text>
                {firstToolItems.length > 0 ? (
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={firstToolItems}
                    renderItem={(row) => (
                      <List.Item>
                        <Space direction="vertical" size={0} style={{ width: '100%' }}>
                          <Text strong>{String(row.event_type || 'tool_call')}</Text>
                          <Text type="secondary">
                            {formatBeijingDateTime(String(row.timestamp || ''))} · {String(row.agent_name || '-')}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description="暂无工具调用记录" />
                )}
              </Space>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'reports',
      label: '报告对比',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="module-card ops-action-card" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                报告版本差异
              </Title>
              <Text type="secondary">输入 incident_id 后可对比不同报告版本，确认根因结论和摘要是否发生偏移。</Text>
              {reportDiff ? (
                <Card size="small" className="ops-subtle-block">
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Text strong>{reportDiff.summary}</Text>
                    <Text type="secondary">
                      base={reportDiff.base_report_id || '-'} / target={reportDiff.target_report_id || '-'}
                    </Text>
                    {reportDiff.diff_lines?.length ? (
                      <pre className="ops-pre">
                        {reportDiff.diff_lines.slice(0, 60).join('\n')}
                      </pre>
                    ) : null}
                  </Space>
                </Card>
              ) : (
                <Alert type="info" showIcon message="暂无报告 diff，先输入 incident_id 加载报告版本。" />
              )}
            </Space>
          </Card>

          <Card className="module-card ops-section-card" size="small">
            <Table
              rowKey={(row: ReportVersion) => row.report_id}
              dataSource={reportVersions}
              pagination={{ pageSize: 6 }}
              columns={[
                { title: 'Report ID', dataIndex: 'report_id', key: 'report_id', width: 220 },
                { title: '会话', dataIndex: 'debate_session_id', key: 'debate_session_id', width: 200 },
                { title: '格式', dataIndex: 'format', key: 'format', width: 100 },
                {
                  title: '生成时间',
                  dataIndex: 'generated_at',
                  key: 'generated_at',
                  width: 220,
                  render: (v: string) => formatBeijingDateTime(v),
                },
                { title: '摘要', dataIndex: 'content_preview', key: 'content_preview' },
              ]}
              locale={{ emptyText: '输入 incident_id 后加载报告版本' }}
            />
          </Card>
        </Space>
      ),
    },
    {
      key: 'raw-audit',
      label: '原始审计',
      children: (
        <Card className="module-card ops-section-card" size="small">
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Alert
              type="warning"
              showIcon
              message="原始审计区"
              description="这一页更偏平台深度排查。只有在结论、证据或工具链路存在疑点时，才建议继续往下读。"
            />
            {firstTimelineItems.length > 0 ? (
              <List
                size="small"
                className="ops-list-tight"
                dataSource={firstTimelineItems}
                renderItem={(row) => (
                  <List.Item>
                    <Space direction="vertical" size={0} style={{ width: '100%' }}>
                      <Text strong>
                        [{formatBeijingDateTime(String(row.timestamp || ''))}] {String(row.event_type || row.kind || '-')}
                      </Text>
                      <Text type="secondary">
                        {String(row.agent_name || '-')} · {String(row.phase || '-')}
                      </Text>
                    </Space>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无原始审计数据" />
            )}
          </Space>
        </Card>
      ),
    },
  ];

  return (
    <div className="workbench-page">
      <Card className="module-card ops-hero-card">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="blue">值班 SRE</Tag>
            <Tag color="default">深度审计</Tag>
          </Space>
          <div>
            <Title level={3} style={{ margin: 0 }}>
              会话审计
            </Title>
            <Paragraph className="ops-hero-description">
              这页用来复盘一次分析为什么得出当前结论。先看结论、置信度和推荐下一步，必要时再下钻到工具审计、报告差异和原始轨迹。
            </Paragraph>
          </div>
          <div className="ops-question-list">
            <Tag>这次 session 最终怎么判</Tag>
            <Tag>为什么这么判</Tag>
            <Tag>哪一步最值得怀疑</Tag>
          </div>
        </Space>
      </Card>

      <Card className="module-card ops-action-card" style={{ marginTop: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Title level={5} style={{ margin: 0 }}>
            加载会话与报告
          </Title>
          <Space wrap>
            <Input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="输入会话ID，例如 deb_xxx 或 ags_xxx"
              style={{ width: 360 }}
            />
            <Button type="primary" loading={loading} onClick={() => void load()}>
              加载会话
            </Button>
            <Select
              value={replayPhaseFilter}
              style={{ width: 180 }}
              options={[
                { label: '全部阶段', value: 'all' },
                { label: 'analysis', value: 'analysis' },
                { label: 'coordination', value: 'coordination' },
                { label: 'critique', value: 'critique' },
                { label: 'rebuttal', value: 'rebuttal' },
                { label: 'judgment', value: 'judgment' },
                { label: 'verification', value: 'verification' },
              ]}
              onChange={setReplayPhaseFilter}
            />
            <Select
              value={replayAgentFilter}
              style={{ width: 220 }}
              options={replayAgentOptions.map((value) => ({
                label: value === 'all' ? '全部Agent' : value,
                value,
              }))}
              onChange={setReplayAgentFilter}
            />
          </Space>
          <Space wrap>
            <Input
              value={incidentId}
              onChange={(e) => setIncidentId(e.target.value)}
              placeholder="incident_id（用于报告对比）"
              style={{ width: 260 }}
            />
            <Button onClick={() => void loadReportVersions()}>加载报告版本</Button>
            <Tag color="processing">谱系记录：{Number(summary?.records || 0)}</Tag>
            <Tag color="blue">事件：{Number(summary?.events || 0)}</Tag>
            <Tag color="gold">工具调用：{toolCallCount}</Tag>
            <Tag color="purple">关键决策：{keyDecisions.length}</Tag>
            <Tag color="geekblue">证据引用：{evidenceRefs.length}</Tag>
            <Tag color="cyan">时间线：{timelineCount}</Tag>
          </Space>
        </Space>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {summaryCards.map((card) => (
          <Col xs={24} sm={12} xl={8} key={card.title}>
            <Card className={`module-card ops-summary-card tone-${card.tone}`} size="small">
              <Text type="secondary">{card.title}</Text>
              <Title level={5} style={{ margin: '4px 0 0' }}>
                {String(card.value)}
              </Title>
              <Text className="ops-summary-hint">{card.hint}</Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Card className={`module-card ops-recommend-card tone-${recommendation.tone}`} style={{ marginTop: 16 }}>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Text strong>处置建议</Text>
          <Title level={5} style={{ margin: 0 }}>
            {recommendation.title}
          </Title>
          <Text type="secondary">{recommendation.description}</Text>
        </Space>
      </Card>

      <div style={{ marginTop: 16 }}>
        <Tabs className="incident-workspace-tabs" items={tabs} />
      </div>
    </div>
  );
};

export default InvestigationWorkbenchPage;
