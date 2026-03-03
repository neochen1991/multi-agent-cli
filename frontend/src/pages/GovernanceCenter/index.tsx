import React, { useEffect, useState } from 'react';
import { Button, Card, Col, Input, InputNumber, List, Row, Select, Space, Statistic, Typography, message } from 'antd';
import { governanceApi } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Title, Text } = Typography;

const GovernanceCenterPage: React.FC = () => {
  const [systemCard, setSystemCard] = useState<Record<string, any>>({});
  const [quality, setQuality] = useState<Array<Record<string, any>>>([]);
  const [costCaseCount, setCostCaseCount] = useState(100);
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
  const [remediationSummary, setRemediationSummary] = useState('');

  const load = async () => {
    try {
      const [card, trend, estimate, feedback, learning, tenantRes, remediationRes, externalRes] = await Promise.all([
        governanceApi.systemCard(),
        governanceApi.qualityTrend(30),
        governanceApi.costEstimate(costCaseCount),
        governanceApi.listFeedback(20),
        governanceApi.feedbackLearningCandidates(200),
        governanceApi.listTenants(),
        governanceApi.listRemediation(30),
        governanceApi.listExternalSync(30),
      ]);
      setSystemCard(card as Record<string, any>);
      setQuality((trend?.items || []) as Array<Record<string, any>>);
      setCost(estimate as Record<string, any>);
      setFeedbackItems((feedback?.items || []) as Array<Record<string, any>>);
      setLearningCandidates(learning as Record<string, any>);
      setTenants((tenantRes?.items || []) as Array<Record<string, any>>);
      setRemediationItems((remediationRes?.items || []) as Array<Record<string, any>>);
      setExternalItems((externalRes?.items || []) as Array<Record<string, any>>);
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '治理数据加载失败');
    }
  };

  useEffect(() => {
    void load();
  }, [costCaseCount]);

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

  return (
    <div>
      <Card className="module-card">
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            治理中心
          </Title>
          <Text type="secondary">
            系统：{String(systemCard?.system?.name || '')} · 模型：{String(systemCard?.system?.llm_model || '')}
          </Text>
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={24} md={8}>
          <Card className="module-card compact-card">
            <Space direction="vertical" size={6}>
              <Text>成本估算样本数</Text>
              <InputNumber min={1} max={5000} value={costCaseCount} onChange={(v) => setCostCaseCount(Number(v || 100))} />
              <Statistic title="估算 Tokens" value={Number(cost.estimated_tokens || 0)} />
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="module-card compact-card">
            <Statistic title="租户数" value={tenants.length} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card className="module-card compact-card">
            <Statistic title="修复动作" value={remediationItems.length} />
          </Card>
        </Col>
      </Row>

      <Card className="module-card" title="系统边界与安全控制" style={{ marginTop: 16 }}>
        <List
          size="small"
          dataSource={[...(systemCard.boundaries || []), ...(systemCard.safety_controls || [])] as string[]}
          renderItem={(item) => <List.Item>{item}</List.Item>}
        />
      </Card>

      <Card className="module-card" title="A/B 评测与质量趋势" style={{ marginTop: 16 }}>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Button onClick={() => void runAbEval()}>执行 A/B 评测</Button>
          {Object.keys(abResult).length > 0 ? (
            <Text>
              {String(abResult.summary || '-')} · top1Δ={String((abResult.comparison || {}).top1_rate_delta ?? '-')} · timeoutΔ=
              {String((abResult.comparison || {}).timeout_rate_delta ?? '-')}
            </Text>
          ) : null}
          <List
            size="small"
            dataSource={quality}
            renderItem={(item) => (
              <List.Item>
                <Text type="secondary">
                  {formatBeijingDateTime(String(item.generated_at || ''))} · Top1{' '}
                  {(Number((item.summary || {}).top1_rate || 0) * 100).toFixed(1)}%
                </Text>
              </List.Item>
            )}
          />
        </Space>
      </Card>

      <Card className="module-card" title="反馈学习流水线" style={{ marginTop: 16 }}>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
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
            <Input value={feedbackComment} onChange={(e) => setFeedbackComment(e.target.value)} placeholder="反馈说明" style={{ width: 360 }} />
            <Button type="primary" onClick={() => void submitFeedback()}>
              提交反馈
            </Button>
          </Space>
          <Text type="secondary">反馈统计：{JSON.stringify(learningCandidates.summary || {})}</Text>
          <List
            size="small"
            dataSource={(learningCandidates.prompt_candidates || []) as Array<Record<string, any>>}
            renderItem={(item) => (
              <List.Item>
                <Text>
                  {String(item.title || '-')}：{String(item.suggestion || '-')}
                </Text>
              </List.Item>
            )}
          />
          <List
            size="small"
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

      <Card className="module-card" title="可控自治修复（状态机）" style={{ marginTop: 16 }}>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space wrap>
            <Input
              value={remediationSummary}
              onChange={(e) => setRemediationSummary(e.target.value)}
              placeholder="修复提案摘要"
              style={{ width: 420 }}
            />
            <Button onClick={() => void proposeRemediation()}>创建修复提案</Button>
          </Space>
          <List
            size="small"
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

      <Card className="module-card" title="多租户治理与外部协同" style={{ marginTop: 16 }}>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Button onClick={() => void emitExternalSync()}>写入外部协同记录（Jira）</Button>
          <List
            size="small"
            header={<Text strong>租户策略</Text>}
            dataSource={tenants}
            renderItem={(item) => (
              <List.Item>
                <Text>
                  tenant={String(item.tenant_id || '-')} · budget={String(((item.budget || {}) as Record<string, any>).monthly_token_budget || '-')} · quota=
                  {String(((item.quota || {}) as Record<string, any>).max_concurrent_sessions || '-')}
                </Text>
              </List.Item>
            )}
          />
          <List
            size="small"
            header={<Text strong>外部协同记录</Text>}
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
        </Space>
      </Card>
    </div>
  );
};

export default GovernanceCenterPage;

