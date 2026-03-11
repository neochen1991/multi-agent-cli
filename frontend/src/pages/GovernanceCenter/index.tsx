import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Input,
  InputNumber,
  List,
  Row,
  Select,
  Space,
  Statistic,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import { governanceApi } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';
import { useNavigate } from 'react-router-dom';

const { Paragraph, Text, Title } = Typography;

const percent = (value: unknown, precision = 1) => `${(Number(value || 0) * 100).toFixed(precision)}%`;
const currency = (value: unknown) => `${Number(value || 0).toFixed(4)} CNY`;

const latestQualityInterpretation = (top1Rate: number) => {
  if (top1Rate >= 0.75) return { tone: 'healthy', text: '最近质量稳定，可继续信任默认策略' };
  if (top1Rate >= 0.6) return { tone: 'watch', text: '最近质量可用，但建议关注回退和超时情况' };
  return { tone: 'risk', text: '最近质量偏弱，建议先看评测结果与关键 session 回放' };
};

const claimGraphInterpretation = (qualityScore: number) => {
  if (qualityScore >= 0.7) return { tone: 'healthy', text: '结构化证据图质量稳定，支持证据和排除项较完整' };
  if (qualityScore >= 0.5) return { tone: 'watch', text: '结构化证据图可用，但支持证据或待验证项仍有缺口' };
  return { tone: 'risk', text: '结构化证据图偏弱，建议优先复盘 supports / exclusions / missing checks' };
};

const activeRiskInterpretation = (pendingRemediation: number, timeoutRate: number) => {
  if (pendingRemediation > 0) return { tone: 'risk', text: '存在待处理修复动作，建议优先确认风险级别和审批状态' };
  if (timeoutRate >= 0.15) return { tone: 'watch', text: '最近超时率偏高，建议先查看团队治理指标和热点' };
  return { tone: 'healthy', text: '当前没有明显治理阻塞项，可按默认节奏运行' };
};

const GovernanceCenterPage: React.FC = () => {
  const navigate = useNavigate();
  const [systemCard, setSystemCard] = useState<Record<string, any>>({});
  const [quality, setQuality] = useState<Array<Record<string, any>>>([]);
  const [costCaseCount] = useState(100);
  const [cost, setCost] = useState<Record<string, any>>({});
  const [feedbackIncident, setFeedbackIncident] = useState('');
  const [feedbackSession, setFeedbackSession] = useState('');
  const [feedbackVerdict, setFeedbackVerdict] = useState<'adopt' | 'reject' | 'revise'>('adopt');
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackItems, setFeedbackItems] = useState<Array<Record<string, any>>>([]);
  const [learningCandidates, setLearningCandidates] = useState<Record<string, any>>({});
  const [abResult, setAbResult] = useState<Record<string, any>>({});
  const [tenants, setTenants] = useState<Array<Record<string, any>>>([]);
  const [remediationItems, setRemediationItems] = useState<Array<Record<string, any>>>([]);
  const [externalItems, setExternalItems] = useState<Array<Record<string, any>>>([]);
  const [externalSyncSettings, setExternalSyncSettings] = useState<Record<string, any>>({});
  const [externalSyncTemplates, setExternalSyncTemplates] = useState<Record<string, any>>({});
  const [remediationSummary, setRemediationSummary] = useState('');
  const [metricsWindowDays, setMetricsWindowDays] = useState(7);
  const [teamMetrics, setTeamMetrics] = useState<Array<Record<string, any>>>([]);
  const [teamMetricsMeta, setTeamMetricsMeta] = useState<Record<string, any>>({});
  const [replaySessionId, setReplaySessionId] = useState('');
  const [replayResult, setReplayResult] = useState<Record<string, any>>({});
  const [replayLoading, setReplayLoading] = useState(false);
  const [runtimeProfiles, setRuntimeProfiles] = useState<Array<Record<string, any>>>([]);
  const [runtimeActiveProfile, setRuntimeActiveProfile] = useState<string>('balanced');
  const [humanReviewItems, setHumanReviewItems] = useState<Array<Record<string, any>>>([]);
  const [humanReviewSummary, setHumanReviewSummary] = useState<Record<string, any>>({});
  const [humanReviewFilter, setHumanReviewFilter] = useState<'all' | 'pending' | 'approved'>('pending');
  const [humanReviewOperator, setHumanReviewOperator] = useState('sre-oncall');
  const [humanReviewApproveComment, setHumanReviewApproveComment] = useState('');
  const [humanReviewRejectReason, setHumanReviewRejectReason] = useState('证据不足，暂不放行');
  const [humanReviewActionLoading, setHumanReviewActionLoading] = useState<string>('');

  const load = async () => {
    try {
      const [
        card,
        trend,
        estimate,
        feedback,
        learning,
        tenantRes,
        remediationRes,
        externalRes,
        teamMetricsRes,
        syncSettings,
        syncTemplates,
        runtimeProfilesRes,
        runtimeActiveRes,
        humanReviewRes,
      ] = await Promise.all([
        governanceApi.systemCard(),
        governanceApi.qualityTrend(30),
        governanceApi.costEstimate(costCaseCount),
        governanceApi.listFeedback(20),
        governanceApi.feedbackLearningCandidates(200),
        governanceApi.listTenants(),
        governanceApi.listRemediation(30),
        governanceApi.listExternalSync(30),
        governanceApi.teamMetrics(metricsWindowDays, 100),
        governanceApi.externalSyncSettings(),
        governanceApi.externalSyncTemplates(),
        governanceApi.runtimeStrategies(),
        governanceApi.runtimeStrategyActive(),
        governanceApi.listHumanReview(50),
      ]);
      setSystemCard(card as Record<string, any>);
      setQuality((trend?.items || []) as Array<Record<string, any>>);
      setCost(estimate as Record<string, any>);
      setFeedbackItems((feedback?.items || []) as Array<Record<string, any>>);
      setLearningCandidates(learning as Record<string, any>);
      setTenants((tenantRes?.items || []) as Array<Record<string, any>>);
      setRemediationItems((remediationRes?.items || []) as Array<Record<string, any>>);
      setExternalItems((externalRes?.items || []) as Array<Record<string, any>>);
      setExternalSyncSettings((syncSettings || {}) as Record<string, any>);
      setExternalSyncTemplates((syncTemplates || {}) as Record<string, any>);
      setTeamMetrics((teamMetricsRes?.items || []) as Array<Record<string, any>>);
      setTeamMetricsMeta((teamMetricsRes || {}) as Record<string, any>);
      setRuntimeProfiles((runtimeProfilesRes.items || []) as Array<Record<string, any>>);
      setRuntimeActiveProfile(String(runtimeActiveRes.active_profile || 'balanced'));
      setHumanReviewItems((humanReviewRes.items || []) as Array<Record<string, any>>);
      setHumanReviewSummary((humanReviewRes.summary || {}) as Record<string, any>);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '治理数据加载失败');
    }
  };

  useEffect(() => {
    void load();
  }, [costCaseCount, metricsWindowDays]);

  const submitFeedback = async () => {
    try {
      await governanceApi.submitFeedback({
        incident_id: feedbackIncident.trim(),
        session_id: feedbackSession.trim(),
        verdict: feedbackVerdict,
        comment: feedbackComment.trim(),
      });
      message.success('反馈已提交');
      setFeedbackComment('');
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '反馈提交失败');
    }
  };

  const runAbEval = async () => {
    try {
      const result = await governanceApi.abEvaluate('baseline', 'candidate');
      setAbResult(result);
      message.success('A/B 评测完成');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || 'A/B 评测失败');
    }
  };

  const proposeRemediation = async () => {
    if (!feedbackIncident.trim() || !feedbackSession.trim() || !remediationSummary.trim()) {
      message.warning('请输入 incident_id、session_id 和修复摘要');
      return;
    }
    try {
      await governanceApi.proposeRemediation({
        incident_id: feedbackIncident.trim(),
        session_id: feedbackSession.trim(),
        summary: remediationSummary.trim(),
        steps: ['模拟验证修复动作', '灰度执行', '对比执行前后 SLO'],
        risk_level: 'high',
        pre_slo: { error_rate: 0.12, p95_latency_ms: 820 },
      });
      message.success('修复提案已创建');
      setRemediationSummary('');
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '修复提案创建失败');
    }
  };

  const approveRemediation = async (actionId: string) => {
    try {
      await governanceApi.approveRemediation(actionId, 'sre-oncall', '治理中心审批通过');
      message.success('已审批');
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '审批失败');
    }
  };

  const executeRemediation = async (actionId: string) => {
    try {
      await governanceApi.executeRemediation(actionId, 'sre-oncall', { error_rate: 0.08, p95_latency_ms: 730 });
      message.success('执行成功');
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '执行失败（可能被 No-Regression Gate 拦截）');
    }
  };

  const rollbackRemediation = async (actionId: string) => {
    try {
      await governanceApi.rollbackRemediation(actionId, '自动回滚演练', false);
      message.success('已生成回滚方案');
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '回滚方案生成失败');
    }
  };

  const emitExternalSync = async () => {
    try {
      await governanceApi.syncExternal({
        provider: 'jira',
        direction: 'outbound',
        action: 'create_ticket',
        payload: { title: 'RCA result synced', incident_id: feedbackIncident || 'inc_demo' },
      });
      message.success('已写入外部协同记录');
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '外部协同记录失败');
    }
  };

  const updateExternalAutoSync = async (enabled: boolean) => {
    try {
      await governanceApi.updateExternalSyncSettings({
        enabled,
        providers: externalSyncSettings.providers || ['jira', 'servicenow', 'slack', 'feishu', 'pagerduty'],
      });
      message.success('自动同步设置已更新');
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '自动同步设置更新失败');
    }
  };

  const updateRuntimeStrategy = async (profile: string) => {
    try {
      await governanceApi.updateRuntimeStrategyActive(profile);
      setRuntimeActiveProfile(profile);
      message.success('运行策略已更新');
      await load();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '运行策略更新失败');
    }
  };

  const loadSessionReplay = async () => {
    const sid = replaySessionId.trim();
    if (!sid) {
      message.warning('请输入 session_id');
      return;
    }
    setReplayLoading(true);
    try {
      const payload = await governanceApi.sessionReplay(sid, 160);
      setReplayResult(payload as Record<string, any>);
      message.success('回放加载完成');
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '回放加载失败');
    } finally {
      setReplayLoading(false);
    }
  };

  const latestQuality = quality[0] || {};
  const latestQualityTop1 = Number((latestQuality.summary || {}).top1_rate || 0);
  const latestClaimGraphQuality = Number((latestQuality.summary || {}).avg_claim_graph_quality_score || 0);
  const latestClaimGraphSupportRate = Number((latestQuality.summary || {}).claim_graph_support_rate || 0);
  const latestClaimGraphExclusionRate = Number((latestQuality.summary || {}).claim_graph_exclusion_rate || 0);
  const latestClaimGraphMissingCheckRate = Number((latestQuality.summary || {}).claim_graph_missing_check_rate || 0);
  const qualityState = latestQualityInterpretation(latestQualityTop1);
  const claimGraphState = claimGraphInterpretation(latestClaimGraphQuality);
  const pendingRemediationItems = remediationItems.filter((item) => {
    const state = String(item.state || '').toLowerCase();
    return !['executed', 'rolled_back', 'closed'].includes(state);
  });
  const pendingHumanReviewCount = Number(humanReviewSummary.pending || 0);
  const approvedHumanReviewCount = Number(humanReviewSummary.approved || 0);
  const pendingRemediationCount = pendingRemediationItems.length;
  const worstTeamTimeoutRate = teamMetrics.reduce((max, item) => Math.max(max, Number(item.timeout_rate || 0)), 0);
  const worstTeamQueueTimeoutRate = teamMetrics.reduce(
    (max, item) => Math.max(max, Number(item.queue_timeout_rate || 0)),
    0,
  );
  const worstLimitedAnalysisRate = teamMetrics.reduce(
    (max, item) => Math.max(max, Number(item.limited_analysis_rate || 0)),
    0,
  );
  const worstEvidenceGapRate = teamMetrics.reduce(
    (max, item) => Math.max(max, Number(item.evidence_gap_rate || 0)),
    0,
  );
  const riskState = activeRiskInterpretation(pendingRemediationCount, worstTeamTimeoutRate);
  const activeProfile = runtimeProfiles.find((item) => String(item.name || '') === runtimeActiveProfile) || {};
  const replayReady = Object.keys(replayResult).length > 0;
  const filteredHumanReviewItems = humanReviewItems.filter((item) => {
    if (humanReviewFilter === 'all') return true;
    return String(item.review_status || '').toLowerCase() === humanReviewFilter;
  });

  useEffect(() => {
    if (pendingHumanReviewCount <= 0 && approvedHumanReviewCount <= 0) {
      return;
    }
    const timer = window.setInterval(() => {
      void load();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [approvedHumanReviewCount, pendingHumanReviewCount]);

  const recommendedAction = useMemo(() => {
    if (pendingHumanReviewCount > 0) {
      return {
        tone: 'risk',
        title: '先处理待人工审核会话',
        description: `当前有 ${pendingHumanReviewCount} 个会话等待人工审核，建议先确认根因结论是否可放行，再决定是否进入修复治理。`,
      };
    }
    if (pendingRemediationCount > 0) {
      return {
        tone: 'risk',
        title: '先处理待审批或待执行的修复动作',
        description: `当前有 ${pendingRemediationCount} 个修复动作未闭环，建议先进入“治理动作”确认风险和审批状态。`,
      };
    }
    if (worstTeamQueueTimeoutRate >= 0.1) {
      return {
        tone: 'watch',
        title: '先查看 LLM 队列超时热点',
        description: `最近 ${metricsWindowDays} 天最高 queue timeout rate 为 ${percent(
          worstTeamQueueTimeoutRate,
        )}，建议先检查并发策略和高峰时段的收口链路。`,
      };
    }
    if (worstLimitedAnalysisRate >= 0.15) {
      return {
        tone: 'watch',
        title: '先查看受限分析占比',
        description: `最近 ${metricsWindowDays} 天最高受限分析占比为 ${percent(
          worstLimitedAnalysisRate,
        )}，说明工具未执行但模型仍在推理，建议优先排查工具开关和数据源可用性。`,
      };
    }
    if (worstEvidenceGapRate >= 0.2) {
      return {
        tone: 'watch',
        title: '先查看关键证据覆盖缺口',
        description: `最近 ${metricsWindowDays} 天最高关键证据缺口会话占比为 ${percent(
          worstEvidenceGapRate,
        )}，建议先复盘低置信度结论和关键 Agent 降级情况。`,
      };
    }
    if (worstTeamTimeoutRate >= 0.15) {
      return {
        tone: 'watch',
        title: '先查看团队超时热点',
        description: `最近 ${metricsWindowDays} 天最高 timeout rate 为 ${percent(worstTeamTimeoutRate)}，建议先在“状态总览”排查热点团队与工具失败。`,
      };
    }
    if (latestQualityTop1 > 0 && latestQualityTop1 < 0.6) {
      return {
        tone: 'watch',
        title: '先交叉核对质量趋势和关键 session',
        description: '最近质量趋势偏弱，建议从“回放与审计”复盘关键 session，再决定是否切换运行策略。',
      };
    }
    if (latestClaimGraphQuality > 0 && latestClaimGraphQuality < 0.5) {
      return {
        tone: 'watch',
        title: '先补结构化证据图质量',
        description: '最近 benchmark 的 claim graph 偏弱，建议优先看支持证据、排除项和待验证项是否成形。',
      };
    }
    return {
      tone: 'healthy',
      title: '当前可以按默认策略继续值班',
      description: '没有明显治理阻塞项。优先关注新进 incident，必要时再进入策略或回放区做定向排查。',
    };
  }, [
    latestQualityTop1,
    metricsWindowDays,
    pendingHumanReviewCount,
    pendingRemediationCount,
    latestClaimGraphQuality,
    worstEvidenceGapRate,
    worstLimitedAnalysisRate,
    worstTeamQueueTimeoutRate,
    worstTeamTimeoutRate,
  ]);

  const governanceSummaryCards = [
    {
      title: '当前运行策略',
      value: runtimeActiveProfile || 'balanced',
      hint: String(activeProfile.description || '控制回合数、截断和历史压缩的默认运行策略'),
      tone: 'info',
    },
    {
      title: '最近质量趋势',
      value: latestQualityTop1 ? percent(latestQualityTop1) : '暂无',
      hint: qualityState.text,
      tone: qualityState.tone,
    },
    {
      title: 'Claim Graph 质量',
      value: latestClaimGraphQuality ? latestClaimGraphQuality.toFixed(3) : '暂无',
      hint: claimGraphState.text,
      tone: claimGraphState.tone,
    },
    {
      title: '待人工审核会话',
      value: pendingHumanReviewCount,
      hint: pendingHumanReviewCount > 0 ? '这些会话还没有被人工放行，建议优先处理。' : '当前没有待人工审核会话',
      tone: pendingHumanReviewCount > 0 ? 'risk' : 'healthy',
    },
    {
      title: '待处理修复动作',
      value: pendingRemediationCount,
      hint: riskState.text,
      tone: riskState.tone,
    },
    {
      title: '最高团队超时率',
      value: percent(worstTeamTimeoutRate),
      hint: worstTeamTimeoutRate >= 0.15 ? '超时偏高，建议先看热点和回放' : '暂无明显超时压力',
      tone: worstTeamTimeoutRate >= 0.15 ? 'watch' : 'healthy',
    },
    {
      title: '最高队列超时率',
      value: percent(worstTeamQueueTimeoutRate),
      hint: worstTeamQueueTimeoutRate >= 0.1 ? 'LLM 排队压力偏高，优先检查分析批次和收口链路' : '暂无明显排队拥塞',
      tone: worstTeamQueueTimeoutRate >= 0.1 ? 'watch' : 'healthy',
    },
    {
      title: '最高受限分析率',
      value: percent(worstLimitedAnalysisRate),
      hint: worstLimitedAnalysisRate >= 0.15 ? '工具未执行但仍在推理，建议优先检查工具接入与命令门禁' : '暂无明显受限分析堆积',
      tone: worstLimitedAnalysisRate >= 0.15 ? 'watch' : 'healthy',
    },
    {
      title: '最高证据缺口率',
      value: percent(worstEvidenceGapRate),
      hint: worstEvidenceGapRate >= 0.2 ? '关键证据覆盖偏弱，建议先复盘低置信度 session' : '暂无明显关键证据缺口',
      tone: worstEvidenceGapRate >= 0.2 ? 'watch' : 'healthy',
    },
    {
      title: '自动外部同步',
      value: Boolean(externalSyncSettings.enabled) ? '开启' : '关闭',
      hint: Boolean(externalSyncSettings.enabled) ? '治理结果会同步到外部系统' : '目前只保留本地协同记录',
      tone: Boolean(externalSyncSettings.enabled) ? 'healthy' : 'info',
    },
    {
      title: '回放工具状态',
      value: replayReady ? '已加载' : '待输入 session',
      hint: replayReady ? '可以直接查看关键决策链路' : '输入 session_id 后可回放主流程',
      tone: replayReady ? 'healthy' : 'info',
    },
  ];

  const timeoutBars = teamMetrics
    .slice()
    .sort((a, b) => Number(b.timeout_rate || 0) - Number(a.timeout_rate || 0))
    .slice(0, 5)
    .map((item) => ({
      label: String(item.team || '-'),
      value: Number(item.timeout_rate || 0),
      text: percent(item.timeout_rate),
    }));

  const queueTimeoutBars = teamMetrics
    .slice()
    .sort((a, b) => Number(b.queue_timeout_rate || 0) - Number(a.queue_timeout_rate || 0))
    .slice(0, 5)
    .map((item) => ({
      label: String(item.team || '-'),
      value: Number(item.queue_timeout_rate || 0),
      text: percent(item.queue_timeout_rate),
    }));

  const limitedAnalysisBars = teamMetrics
    .slice()
    .sort((a, b) => Number(b.limited_analysis_rate || 0) - Number(a.limited_analysis_rate || 0))
    .slice(0, 5)
    .map((item) => ({
      label: String(item.team || '-'),
      value: Number(item.limited_analysis_rate || 0),
      text: percent(item.limited_analysis_rate),
    }));

  const costTrendBars = (((teamMetricsMeta.token_cost_trend || []) as Array<Record<string, any>>).slice(-6)).map((item) => ({
    label: String(item.day || '-').slice(5),
    value: Number(item.estimated_model_cost || 0),
    text: currency(item.estimated_model_cost),
  }));

  const toolFailureBars = (((teamMetricsMeta.tool_failure_topn || []) as Array<Record<string, any>>).slice(0, 5)).map((item) => ({
    label: String(item.tool_name || '-'),
    value: Number(item.count || 0),
    text: String(item.count || 0),
  }));

  const tabs = [
    {
      key: 'human-review',
      label: '人工审核',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="module-card ops-section-card" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                人工审核队列
              </Title>
              <Text type="secondary">这里处理 production_governed 下等待人工确认的会话。先确认结论是否可信，再决定放行或驳回。</Text>
              <Space wrap>
                <Tag color={pendingHumanReviewCount > 0 ? 'warning' : 'default'}>待审核 {pendingHumanReviewCount}</Tag>
                <Tag color={approvedHumanReviewCount > 0 ? 'processing' : 'default'}>已批准待恢复 {approvedHumanReviewCount}</Tag>
              </Space>
              <Space wrap>
                <Select
                  value={humanReviewFilter}
                  style={{ width: 150 }}
                  options={[
                    { label: '只看待审核', value: 'pending' },
                    { label: '只看已批准', value: 'approved' },
                    { label: '查看全部', value: 'all' },
                  ]}
                  onChange={(value) => setHumanReviewFilter(value)}
                />
                <Input
                  value={humanReviewOperator}
                  onChange={(e) => setHumanReviewOperator(e.target.value)}
                  placeholder="审核人"
                  style={{ width: 160 }}
                />
                <Input
                  value={humanReviewApproveComment}
                  onChange={(e) => setHumanReviewApproveComment(e.target.value)}
                  placeholder="批准备注"
                  style={{ width: 220 }}
                />
                <Input
                  value={humanReviewRejectReason}
                  onChange={(e) => setHumanReviewRejectReason(e.target.value)}
                  placeholder="驳回原因"
                  style={{ width: 240 }}
                />
                <Button onClick={() => void load()}>刷新队列</Button>
              </Space>
            </Space>
          </Card>

          <List
            className="ops-list-tight"
            dataSource={filteredHumanReviewItems}
            locale={{ emptyText: '当前没有待人工审核会话' }}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button
                    key="approve"
                    size="small"
                    type="primary"
                    disabled={String(item.review_status || '') === 'approved'}
                    loading={humanReviewActionLoading === `approve:${String(item.session_id || '')}`}
                    onClick={async () => {
                      try {
                        setHumanReviewActionLoading(`approve:${String(item.session_id || '')}`);
                        await governanceApi.approveHumanReview(
                          String(item.session_id || ''),
                          humanReviewOperator || 'sre-oncall',
                          humanReviewApproveComment,
                        );
                        message.success('已批准人工审核');
                        await load();
                      } catch (e: any) {
                        message.error(e?.response?.data?.detail || e?.message || '批准失败');
                      } finally {
                        setHumanReviewActionLoading('');
                      }
                    }}
                  >
                    批准
                  </Button>,
                  <Button
                    key="reject"
                    size="small"
                    danger
                    loading={humanReviewActionLoading === `reject:${String(item.session_id || '')}`}
                    onClick={async () => {
                      try {
                        setHumanReviewActionLoading(`reject:${String(item.session_id || '')}`);
                        await governanceApi.rejectHumanReview(
                          String(item.session_id || ''),
                          humanReviewOperator || 'sre-oncall',
                          humanReviewRejectReason || 'manual_reject',
                        );
                        message.success('已驳回人工审核');
                        await load();
                      } catch (e: any) {
                        message.error(e?.response?.data?.detail || e?.message || '驳回失败');
                      } finally {
                        setHumanReviewActionLoading('');
                      }
                    }}
                  >
                    驳回
                  </Button>,
                  <Button
                    key="resume"
                    size="small"
                    disabled={String(item.review_status || '') !== 'approved'}
                    loading={humanReviewActionLoading === `resume:${String(item.session_id || '')}`}
                    onClick={async () => {
                      try {
                        setHumanReviewActionLoading(`resume:${String(item.session_id || '')}`);
                        const result = await governanceApi.resumeHumanReview(
                          String(item.session_id || ''),
                          humanReviewOperator || 'sre-oncall',
                        );
                        message.success(`已提交恢复任务: ${String(result.task_id || '-')}`);
                        await load();
                      } catch (e: any) {
                        message.error(e?.response?.data?.detail || e?.message || '恢复执行失败');
                      } finally {
                        setHumanReviewActionLoading('');
                      }
                    }}
                  >
                    恢复执行
                  </Button>,
                  <Button
                    key="open"
                    size="small"
                    onClick={() => {
                      navigate(`/incident/${String(item.incident_id || '')}?view=analysis`);
                    }}
                  >
                    打开故障分析
                  </Button>,
                ]}
              >
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <Space wrap>
                    <Text strong>{String(item.session_id || '-')}</Text>
                    <Tag color={String(item.review_status || '') === 'approved' ? 'processing' : 'warning'}>
                      {String(item.review_status || '') === 'approved' ? '已批准待恢复' : '待人工审核'}
                    </Tag>
                    <Tag>{String(item.execution_mode || '-')}</Tag>
                    <Tag>{String(item.deployment_profile || '-')}</Tag>
                  </Space>
                  <Text type="secondary">
                    incident={String(item.incident_id || '-')} · confidence={percent(item.confidence)} · requested=
                    {formatBeijingDateTime(String(item.requested_at || item.updated_at || ''))}
                  </Text>
                  <Text>{String(item.review_reason || '未提供审核原因')}</Text>
                  {String(item.root_cause || '').trim() ? (
                    <Text type="secondary">根因摘要：{String(item.root_cause || '').slice(0, 180)}</Text>
                  ) : null}
                </Space>
              </List.Item>
            )}
          />
        </Space>
      ),
    },
    {
      key: 'overview',
      label: '状态总览',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="module-card ops-section-card" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                系统边界与安全控制
              </Title>
              <Text type="secondary">先确认这套系统的运行边界和门禁，再决定是否信任自动分析和修复动作。</Text>
              <List
                size="small"
                className="ops-list-tight"
                dataSource={[...(systemCard.boundaries || []), ...(systemCard.safety_controls || [])] as string[]}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </Space>
          </Card>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={15}>
              <Card className="module-card ops-section-card" size="small">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
                    <div>
                      <Title level={5} style={{ margin: 0 }}>
                        团队治理指标
                      </Title>
                      <Text type="secondary">看最近一段时间哪个团队、哪类问题、哪个工具最拖慢分析闭环。</Text>
                    </div>
                    <Space wrap>
                      <Text type="secondary">时间窗（天）</Text>
                      <InputNumber min={1} max={90} value={metricsWindowDays} onChange={(v) => setMetricsWindowDays(Number(v || 7))} />
                    </Space>
                  </Space>
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={teamMetrics}
                    locale={{ emptyText: '暂无团队指标数据' }}
                    renderItem={(item) => (
                      <List.Item>
                        <Space direction="vertical" size={2}>
                          <Text strong>
                            {String(item.team || '-')} · sessions={String(item.sessions || 0)} · success={percent(item.success_rate)}
                          </Text>
                          <Text type="secondary">
                            timeout={percent(item.timeout_rate)} · tool_fail={percent(item.tool_failure_rate)} · 估算成本=
                            {currency(item.estimated_model_cost)}
                          </Text>
                          <Text type="secondary">
                            claim_graph={Number(item.avg_claim_graph_quality_score || 0).toFixed(3)} · supports=
                            {percent(item.claim_graph_support_rate)} · exclusions={percent(item.claim_graph_exclusion_rate)}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                  <Card size="small" className="ops-subtle-block">
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Text strong>Session SLA</Text>
                      <Text type="secondary">
                        首条证据延迟={String(((teamMetricsMeta.sla || {}) as Record<string, any>).first_evidence_latency_ms || 0)}ms ·
                        首结论延迟={String(((teamMetricsMeta.sla || {}) as Record<string, any>).first_conclusion_latency_ms || 0)}ms ·
                        完整报告延迟={String(((teamMetricsMeta.sla || {}) as Record<string, any>).report_latency_ms || 0)}ms
                      </Text>
                    </Space>
                  </Card>
                </Space>
              </Card>
            </Col>

            <Col xs={24} xl={9}>
              <Space direction="vertical" size={16} style={{ width: '100%' }}>
                <Card className="module-card ops-section-card" size="small">
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Title level={5} style={{ margin: 0 }}>
                      Token 成本趋势
                    </Title>
                    <div className="mini-bar-list">
                      {costTrendBars.map((item) => (
                        <div key={item.label} className="mini-bar-row">
                          <div className="mini-bar-label-wrap">
                            <Text strong>{item.label}</Text>
                            <Text type="secondary">{item.text}</Text>
                          </div>
                          <div className="mini-bar-track">
                            <div
                              className="mini-bar-fill tone-info"
                              style={{ width: `${Math.max(10, (item.value / Math.max(...costTrendBars.map((bar) => bar.value), 1)) * 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                    <List
                      size="small"
                      className="ops-list-tight"
                      dataSource={(teamMetricsMeta.token_cost_trend || []) as Array<Record<string, any>>}
                      locale={{ emptyText: '暂无趋势数据' }}
                      renderItem={(item) => (
                        <List.Item>
                          <Text type="secondary">
                            {String(item.day || '-')} · tokens={String(item.estimated_tokens || 0)} · cost={currency(item.estimated_model_cost)}
                          </Text>
                        </List.Item>
                      )}
                    />
                  </Space>
                </Card>

                <Card className="module-card ops-section-card" size="small">
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Title level={5} style={{ margin: 0 }}>
                      热点与失败点
                    </Title>
                    <Card size="small" className="ops-subtle-block mini-chart-card">
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Text strong>团队超时分布</Text>
                        <div className="mini-bar-list">
                          {timeoutBars.map((item) => (
                            <div key={item.label} className="mini-bar-row">
                              <div className="mini-bar-label-wrap">
                                <Text strong>{item.label}</Text>
                                <Text type="secondary">{item.text}</Text>
                              </div>
                              <div className="mini-bar-track">
                                <div className="mini-bar-fill tone-watch" style={{ width: `${Math.max(8, item.value * 100)}%` }} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </Space>
                    </Card>
                    <Card size="small" className="ops-subtle-block mini-chart-card">
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Text strong>LLM 队列超时分布</Text>
                        <div className="mini-bar-list">
                          {queueTimeoutBars.map((item) => (
                            <div key={item.label} className="mini-bar-row">
                              <div className="mini-bar-label-wrap">
                                <Text strong>{item.label}</Text>
                                <Text type="secondary">{item.text}</Text>
                              </div>
                              <div className="mini-bar-track">
                                <div className="mini-bar-fill tone-watch" style={{ width: `${Math.max(8, item.value * 100)}%` }} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </Space>
                    </Card>
                    <Card size="small" className="ops-subtle-block mini-chart-card">
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Text strong>工具失败集中度</Text>
                        <div className="mini-bar-list">
                          {toolFailureBars.map((item) => (
                            <div key={item.label} className="mini-bar-row">
                              <div className="mini-bar-label-wrap">
                                <Text strong>{item.label}</Text>
                                <Text type="secondary">{item.text} 次</Text>
                              </div>
                              <div className="mini-bar-track">
                                <div
                                  className="mini-bar-fill tone-risk"
                                  style={{ width: `${Math.max(10, (item.value / Math.max(...toolFailureBars.map((bar) => bar.value), 1)) * 100)}%` }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </Space>
                    </Card>
                    <Card size="small" className="ops-subtle-block mini-chart-card">
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <Text strong>受限分析占比</Text>
                        <div className="mini-bar-list">
                          {limitedAnalysisBars.map((item) => (
                            <div key={item.label} className="mini-bar-row">
                              <div className="mini-bar-label-wrap">
                                <Text strong>{item.label}</Text>
                                <Text type="secondary">{item.text}</Text>
                              </div>
                              <div className="mini-bar-track">
                                <div className="mini-bar-fill tone-watch" style={{ width: `${Math.max(8, item.value * 100)}%` }} />
                              </div>
                            </div>
                          ))}
                        </div>
                      </Space>
                    </Card>
                    <List
                      size="small"
                      header={<Text strong>队列超时热点</Text>}
                      className="ops-list-tight"
                      dataSource={(teamMetricsMeta.queue_timeout_hotspots || []) as Array<Record<string, any>>}
                      locale={{ emptyText: '暂无队列超时热点' }}
                      renderItem={(item) => (
                        <List.Item>
                          <Text type="secondary">
                            {String(item.key || '-')} · count={String(item.count || 0)}
                          </Text>
                        </List.Item>
                      )}
                    />
                    <List
                      size="small"
                      header={<Text strong>受限分析热点</Text>}
                      className="ops-list-tight"
                      dataSource={(teamMetricsMeta.limited_analysis_hotspots || []) as Array<Record<string, any>>}
                      locale={{ emptyText: '暂无受限分析热点' }}
                      renderItem={(item) => (
                        <List.Item>
                          <Text type="secondary">
                            {String(item.key || '-')} · count={String(item.count || 0)}
                          </Text>
                        </List.Item>
                      )}
                    />
                    <List
                      size="small"
                      header={<Text strong>超时热点</Text>}
                      className="ops-list-tight"
                      dataSource={(teamMetricsMeta.timeout_hotspots || []) as Array<Record<string, any>>}
                      locale={{ emptyText: '暂无超时热点' }}
                      renderItem={(item) => (
                        <List.Item>
                          <Text type="secondary">
                            {String(item.key || '-')} · count={String(item.count || 0)}
                          </Text>
                        </List.Item>
                      )}
                    />
                    <List
                      size="small"
                      header={<Text strong>工具失败</Text>}
                      className="ops-list-tight"
                      dataSource={(teamMetricsMeta.tool_failure_topn || []) as Array<Record<string, any>>}
                      locale={{ emptyText: '暂无工具失败热点' }}
                      renderItem={(item) => (
                        <List.Item>
                          <Text type="secondary">
                            {String(item.tool_name || '-')} · count={String(item.count || 0)}
                          </Text>
                        </List.Item>
                      )}
                    />
                  </Space>
                </Card>
              </Space>
            </Col>
          </Row>
        </Space>
      ),
    },
    {
      key: 'strategy',
      label: '运行策略',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="module-card ops-section-card" size="small">
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <div>
                <Title level={5} style={{ margin: 0 }}>
                  当前策略与切换入口
                </Title>
                <Text type="secondary">这里控制多 Agent 的回合数、截断、压缩和防 doom loop 策略。先看解释，再切换配置。</Text>
              </div>
              <Space wrap align="center">
                <Tag color="blue">当前策略：{runtimeActiveProfile || 'balanced'}</Tag>
                <Select
                  value={runtimeActiveProfile}
                  style={{ width: 240 }}
                  options={runtimeProfiles.map((item) => ({
                    label: `${String(item.name || '-')}: ${String(item.description || '').slice(0, 24)}`,
                    value: String(item.name || 'balanced'),
                  }))}
                  onChange={(value) => void updateRuntimeStrategy(value)}
                />
                <Button onClick={() => void runAbEval()}>执行 A/B 评测</Button>
              </Space>
              {Object.keys(abResult).length > 0 ? (
                <Alert
                  type="info"
                  showIcon
                  message={String(abResult.summary || 'A/B 评测已完成')}
                  description={`top1Δ=${String((abResult.comparison || {}).top1_rate_delta ?? '-')}，timeoutΔ=${String((abResult.comparison || {}).timeout_rate_delta ?? '-')}`}
                />
              ) : null}
            </Space>
          </Card>

          <Row gutter={[16, 16]}>
            {runtimeProfiles.map((item) => (
              <Col xs={24} md={12} xl={8} key={String(item.name || Math.random())}>
                <Card className="module-card ops-summary-card" size="small">
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    <Space align="center" style={{ justifyContent: 'space-between', width: '100%' }}>
                      <Text strong>{String(item.name || '-')}</Text>
                      {String(item.name || '') === runtimeActiveProfile ? <Tag color="blue">当前</Tag> : null}
                    </Space>
                    <Text type="secondary">{String(item.description || '未提供说明')}</Text>
                    <Text className="ops-summary-hint">
                      rounds={String(item.suggested_max_rounds || '-')} · doomLoop={String(item.doom_loop_max_repeat || '-')}
                    </Text>
                    <Collapse
                      size="small"
                      ghost
                      items={[
                        {
                          key: 'detail',
                          label: '查看详细参数',
                          children: (
                            <Text type="secondary">
                              compaction={String(item.compaction_max_messages || '-')} · prune={String(item.prune_history_limit || '-')} ·
                              truncation={String(item.truncation_max_chars || '-')}
                            </Text>
                          ),
                        },
                      ]}
                    />
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>

          <Card className="module-card ops-section-card" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                最近质量趋势
              </Title>
              <Text type="secondary">如果想切策略，先看最近趋势，不要只凭单个 case 的感受切换。</Text>
              <List
                size="small"
                className="ops-list-tight"
                dataSource={quality}
                renderItem={(item) => (
                  <List.Item>
                    <Text type="secondary">
                      {formatBeijingDateTime(String(item.generated_at || ''))} · Top1 {percent((item.summary || {}).top1_rate)} · timeout{' '}
                      {percent((item.summary || {}).timeout_rate)} · claim graph{' '}
                      {Number((item.summary || {}).avg_claim_graph_quality_score || 0).toFixed(3)}
                    </Text>
                  </List.Item>
                )}
              />
              <Card size="small" className="ops-subtle-block mini-chart-card">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Text strong>最近结构化证据图指标</Text>
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={[
                      `平均质量分：${latestClaimGraphQuality.toFixed(3)}`,
                      `支持证据达标率：${percent(latestClaimGraphSupportRate)}`,
                      `排除项达标率：${percent(latestClaimGraphExclusionRate)}`,
                      `待验证项达标率：${percent(latestClaimGraphMissingCheckRate)}`,
                    ]}
                    renderItem={(entry) => <List.Item>{entry}</List.Item>}
                  />
                </Space>
              </Card>
            </Space>
          </Card>
        </Space>
      ),
    },
    {
      key: 'actions',
      label: '治理动作',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card className="module-card ops-action-card" size="small">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <div>
                    <Title level={5} style={{ margin: 0 }}>
                      反馈学习
                    </Title>
                    <Text type="secondary">把本次分析结果标记为采纳、驳回或修订，让平台积累后续优化线索。</Text>
                  </div>
                  <Space wrap>
                    <Input value={feedbackIncident} onChange={(e) => setFeedbackIncident(e.target.value)} placeholder="incident_id" style={{ width: 180 }} />
                    <Input value={feedbackSession} onChange={(e) => setFeedbackSession(e.target.value)} placeholder="session_id" style={{ width: 220 }} />
                    <Select
                      value={feedbackVerdict}
                      onChange={(v) => setFeedbackVerdict(v)}
                      options={[
                        { label: '采纳', value: 'adopt' },
                        { label: '驳回', value: 'reject' },
                        { label: '修订', value: 'revise' },
                      ]}
                      style={{ width: 120 }}
                    />
                    <Input value={feedbackComment} onChange={(e) => setFeedbackComment(e.target.value)} placeholder="反馈说明" style={{ width: 280 }} />
                    <Button type="primary" onClick={() => void submitFeedback()}>
                      提交反馈
                    </Button>
                  </Space>
                  <Alert
                    type="info"
                    showIcon
                    message={`反馈统计：${JSON.stringify(learningCandidates.summary || {})}`}
                    description="先提交一条高质量反馈，再看下方推荐的 prompt 或规则改进候选。"
                  />
                  <List
                    size="small"
                    className="ops-list-tight"
                    header={<Text strong>推荐改进候选</Text>}
                    dataSource={(learningCandidates.prompt_candidates || []) as Array<Record<string, any>>}
                    renderItem={(item) => (
                      <List.Item>
                        <Text>
                          {String(item.title || '-')}：{String(item.suggestion || '-')}
                        </Text>
                      </List.Item>
                    )}
                  />
                </Space>
              </Card>
            </Col>

            <Col xs={24} xl={12}>
              <Card className="module-card ops-action-card" size="small">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <div>
                    <Title level={5} style={{ margin: 0 }}>
                      修复治理
                    </Title>
                    <Text type="secondary">高风险修复必须先走提案、审批和执行闭环，再决定是否生成回滚方案。</Text>
                  </div>
                  <Space wrap>
                    <Input
                      value={remediationSummary}
                      onChange={(e) => setRemediationSummary(e.target.value)}
                      placeholder="修复提案摘要"
                      style={{ width: 360 }}
                    />
                    <Button onClick={() => void proposeRemediation()}>创建修复提案</Button>
                  </Space>
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={remediationItems}
                    renderItem={(item) => (
                      <List.Item
                        actions={[
                          <Button key="approve" size="small" onClick={() => void approveRemediation(String(item.id || ''))}>
                            审批
                          </Button>,
                          <Button key="execute" size="small" onClick={() => void executeRemediation(String(item.id || ''))}>
                            执行
                          </Button>,
                          <Button key="rollback" size="small" onClick={() => void rollbackRemediation(String(item.id || ''))}>
                            回滚方案
                          </Button>,
                        ]}
                      >
                        <Space direction="vertical" size={0}>
                          <Text strong>
                            {String(item.id || '-')} · {String(item.state || '-')} · risk={String(item.risk_level || '-')}
                          </Text>
                          <Text type="secondary">{String(item.summary || '')}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Space>
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card className="module-card ops-action-card" size="small">
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <div>
                    <Title level={5} style={{ margin: 0 }}>
                      外部协同
                    </Title>
                    <Text type="secondary">把 RCA 结果同步到 Jira、ServiceNow、Slack 或飞书等外部系统。</Text>
                  </div>
                  <Space wrap>
                    <Text>自动同步</Text>
                    <Select
                      value={Boolean(externalSyncSettings.enabled) ? 'enabled' : 'disabled'}
                      style={{ width: 160 }}
                      options={[
                        { label: '开启', value: 'enabled' },
                        { label: '关闭', value: 'disabled' },
                      ]}
                      onChange={(value) => void updateExternalAutoSync(value === 'enabled')}
                    />
                    <Button onClick={() => void emitExternalSync()}>写入一条 Jira 协同记录</Button>
                  </Space>
                  <List
                    size="small"
                    className="ops-list-tight"
                    header={<Text strong>最近协同记录</Text>}
                    dataSource={externalItems}
                    renderItem={(item) => (
                      <List.Item>
                        <Text type="secondary">
                          {formatBeijingDateTime(String(item.at || ''))} · {String(item.provider || '-')} · {String(item.direction || '-')} ·{' '}
                          {String(item.action || '-')}
                        </Text>
                      </List.Item>
                    )}
                  />
                  <Collapse
                    size="small"
                    ghost
                    items={[
                      {
                        key: 'mapping',
                        label: '查看字段映射模板',
                        children: (
                          <List
                            size="small"
                            className="ops-list-tight"
                            dataSource={Object.entries(externalSyncTemplates || {})}
                            renderItem={([provider, mapping]) => (
                              <List.Item>
                                <Text type="secondary">
                                  {provider}: {JSON.stringify(mapping).slice(0, 220)}
                                </Text>
                              </List.Item>
                            )}
                          />
                        ),
                      },
                    ]}
                  />
                </Space>
              </Card>
            </Col>

            <Col xs={24} xl={12}>
              <Card className="module-card ops-section-card" size="small">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Title level={5} style={{ margin: 0 }}>
                    多租户治理
                  </Title>
                  <Text type="secondary">看不同租户的预算和并发配额，判断当前策略是否需要按租户收紧。</Text>
                  <List
                    size="small"
                    className="ops-list-tight"
                    dataSource={tenants}
                    renderItem={(item) => (
                      <List.Item>
                        <Text>
                          tenant={String(item.tenant_id || '-')} · budget=
                          {String(((item.budget || {}) as Record<string, any>).monthly_token_budget || '-')} · quota=
                          {String(((item.quota || {}) as Record<string, any>).max_concurrent_sessions || '-')}
                        </Text>
                      </List.Item>
                    )}
                  />
                  <List
                    size="small"
                    className="ops-list-tight"
                    header={<Text strong>最近反馈记录</Text>}
                    dataSource={feedbackItems}
                    renderItem={(item) => (
                      <List.Item>
                        <Space direction="vertical" size={0}>
                          <Text>
                            [{String(item.verdict || '-')}] incident={String(item.incident_id || '-')}, session={String(item.session_id || '-')}
                          </Text>
                          <Text type="secondary">
                            {formatBeijingDateTime(String(item.created_at || ''))} · {String(item.comment || '')}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Space>
              </Card>
            </Col>
          </Row>
        </Space>
      ),
    },
    {
      key: 'replay',
      label: '回放与审计',
      children: (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="module-card ops-action-card" size="small">
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <div>
                <Title level={5} style={{ margin: 0 }}>
                  Session 回放
                </Title>
                <Text type="secondary">输入一个 session_id，回放主 Agent 的关键决策路径、证据引用和结论收敛过程。</Text>
              </div>
              <Space wrap>
                <Input
                  value={replaySessionId}
                  onChange={(e) => setReplaySessionId(e.target.value)}
                  placeholder="输入 session_id（deb_xxx）"
                  style={{ width: 280 }}
                />
                <Button loading={replayLoading} type="primary" onClick={() => void loadSessionReplay()}>
                  加载回放
                </Button>
              </Space>
            </Space>
          </Card>

          {Object.keys(replayResult).length > 0 ? (
            <Row gutter={[16, 16]}>
              <Col xs={24} xl={10}>
                <Card className="module-card ops-section-card" size="small">
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Title level={5} style={{ margin: 0 }}>
                      回放摘要
                    </Title>
                    <Text>
                      session={String(replayResult.session_id || '-')} · status={String(replayResult.session_status || '-')} · incident=
                      {String(replayResult.incident_id || '-')}
                    </Text>
                    <Text type="secondary">
                      root_cause={String(replayResult.root_cause || '暂无')} · confidence={percent(replayResult.confidence)}
                    </Text>
                    <Alert
                      type="info"
                      showIcon
                      message="回放适合做什么"
                      description="当你想确认一次分析为什么得出当前根因、证据链是否完整、或某个专家 Agent 是否偏航时，优先看这里。"
                    />
                  </Space>
                </Card>
              </Col>

              <Col xs={24} xl={14}>
                <Card className="module-card ops-section-card" size="small">
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Title level={5} style={{ margin: 0 }}>
                      关键决策与时间线
                    </Title>
                    <List
                      size="small"
                      className="ops-list-tight"
                      header={<Text strong>关键决策</Text>}
                      dataSource={(replayResult.key_decisions || []) as Array<Record<string, any>>}
                      locale={{ emptyText: '暂无关键决策' }}
                      renderItem={(item) => (
                        <List.Item>
                          <Text>
                            [{String(item.agent || '-')}] {String(item.conclusion || '-')}
                          </Text>
                        </List.Item>
                      )}
                    />
                    <List
                      size="small"
                      className="ops-list-tight"
                      header={<Text strong>时间线步骤</Text>}
                      dataSource={(replayResult.rendered_steps || []) as string[]}
                      locale={{ emptyText: '暂无步骤' }}
                      renderItem={(line) => (
                        <List.Item>
                          <Text type="secondary">{line}</Text>
                        </List.Item>
                      )}
                    />
                  </Space>
                </Card>
              </Col>
            </Row>
          ) : (
            <Card className="module-card ops-section-card" size="small">
              <Text type="secondary">输入 session_id 后可回放主流程关键决策与证据引用。</Text>
            </Card>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div className="governance-page">
      <Card className="module-card ops-hero-card">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="blue">值班 SRE</Tag>
            <Tag color="default">平台治理负责人</Tag>
          </Space>
          <div>
            <Title level={3} style={{ margin: 0 }}>
              运行治理
            </Title>
            <Paragraph className="ops-hero-description">
              这页用来判断多 Agent 系统现在是否可信、当前策略是否合适、以及是否存在待处理治理动作。先看状态，再做动作。
            </Paragraph>
            <Text type="secondary">
              系统：{String(systemCard?.system?.name || '-')} · 模型：{String(systemCard?.system?.llm_model || '-')} · 估算样本数：
              {costCaseCount}
            </Text>
          </div>
          <div className="ops-question-list">
            <Tag>当前系统是否可信</Tag>
            <Tag>当前策略是否过于激进或保守</Tag>
            <Tag>是否有待人工审核会话</Tag>
            <Tag>是否有待处理的治理动作</Tag>
          </div>
        </Space>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {governanceSummaryCards.map((card) => (
          <Col xs={24} sm={12} xl={8} key={card.title}>
            <Card className={`module-card ops-summary-card tone-${card.tone}`} size="small">
              <Statistic title={card.title} value={card.value as any} />
              <Text className="ops-summary-hint">{card.hint}</Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Card className={`module-card ops-recommend-card tone-${recommendedAction.tone}`} style={{ marginTop: 16 }}>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Text strong>处置建议</Text>
          <Title level={5} style={{ margin: 0 }}>
            {recommendedAction.title}
          </Title>
          <Text type="secondary">{recommendedAction.description}</Text>
        </Space>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={18}>
          <Tabs className="incident-workspace-tabs" items={tabs} />
        </Col>
        <Col xs={24} xl={6}>
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Card className="module-card ops-section-card" size="small">
              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                <Title level={5} style={{ margin: 0 }}>
                  快速判断
                </Title>
                <Text type="secondary">如果你只想先看一眼当前状态，优先看下面三项。</Text>
                <Tag color={qualityState.tone === 'risk' ? 'red' : qualityState.tone === 'watch' ? 'orange' : 'green'}>
                  质量趋势：{qualityState.text}
                </Tag>
                <Tag color={riskState.tone === 'risk' ? 'red' : riskState.tone === 'watch' ? 'orange' : 'green'}>
                  活跃风险：{riskState.text}
                </Tag>
                <Tag color="blue">估算 Tokens：{String(cost.estimated_tokens || 0)}</Tag>
              </Space>
            </Card>

            <Card className="module-card ops-section-card" size="small">
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Title level={5} style={{ margin: 0 }}>
                  什么时候来这页
                </Title>
                <List
                  size="small"
                  className="ops-list-tight"
                  dataSource={[
                    '感觉最近分析质量变差，想确认是策略、模型还是工具问题。',
                    '有会话卡在待人工审核，想集中批准或驳回后再恢复执行。',
                    '需要审批或执行修复动作，确认是否触发 No-Regression Gate。',
                    '想复盘某个 session 为什么得出当前根因结论。',
                  ]}
                  renderItem={(item) => <List.Item>{item}</List.Item>}
                />
              </Space>
            </Card>
          </Space>
        </Col>
      </Row>
    </div>
  );
};

export default GovernanceCenterPage;
