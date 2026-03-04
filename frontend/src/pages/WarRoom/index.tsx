import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Input,
  List,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  debateApi,
  incidentApi,
  lineageApi,
  settingsApi,
  type DebateResult,
  type LineageRecord,
  type ToolAuditResponse,
} from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Text, Title } = Typography;

type SessionOption = {
  value: string;
  label: string;
  incidentId: string;
  status: string;
};

const WarRoomPage: React.FC = () => {
  const [sessionId, setSessionId] = useState('');
  const [loading, setLoading] = useState(false);
  const [bootstrapLoading, setBootstrapLoading] = useState(false);
  const [sessionOptions, setSessionOptions] = useState<SessionOption[]>([]);
  const [timeline, setTimeline] = useState<LineageRecord[]>([]);
  const [toolAudit, setToolAudit] = useState<ToolAuditResponse | null>(null);
  const [result, setResult] = useState<DebateResult | null>(null);
  const [keyConclusions, setKeyConclusions] = useState<string[]>([]);
  const [decisionFilter, setDecisionFilter] = useState<string>('');

  const load = async (targetSessionId?: string) => {
    const sid = String(targetSessionId ?? sessionId).trim();
    if (!sid) {
      message.warning('请输入 session_id');
      return;
    }
    setSessionId(sid);
    setLoading(true);
    try {
      const [lineage, audit, debateResult, detail] = await Promise.all([
        lineageApi.get(sid, 300),
        settingsApi.getToolAudit(sid),
        debateApi.getResult(sid).catch(() => null),
        debateApi.get(sid).catch(() => null),
      ]);
      setTimeline(lineage.items || []);
      setToolAudit(audit || null);
      setResult(debateResult);

      const conclusions: string[] = [];
      const rounds = Array.isArray(detail?.rounds) ? detail?.rounds : [];
      for (const row of rounds) {
        const output = (row.output_content || {}) as Record<string, unknown>;
        const conclusion = String(output.conclusion || output.analysis || '').trim();
        if (conclusion) conclusions.push(`${row.agent_name}: ${conclusion.slice(0, 200)}`);
      }
      setKeyConclusions(conclusions.slice(-8));
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || '战情数据加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const bootstrap = async () => {
      setBootstrapLoading(true);
      try {
        const recent = await incidentApi.list(1, 40);
        const options = (recent.items || [])
          .filter((item) => String(item.debate_session_id || '').startsWith('deb_'))
          .map((item) => ({
            value: String(item.debate_session_id),
            label: `${item.debate_session_id} · ${item.title}`,
            incidentId: item.id,
            status: String(item.status || '-'),
          }));
        setSessionOptions(options);
        if (!sessionId && options.length > 0) {
          void load(options[0].value);
        }
      } catch {
        // ignore bootstrap errors, keep manual mode
      } finally {
        setBootstrapLoading(false);
      }
    };
    void bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const evidenceLines = useMemo(() => {
    const rows = Array.isArray(result?.evidence_chain) ? result?.evidence_chain : [];
    return rows.map((row, idx) => {
      return `${idx + 1}. ${row.description}（${row.source}${row.source_ref ? ` / ${row.source_ref}` : ''}）`;
    });
  }, [result]);

  const filteredTimeline = useMemo(() => {
    const q = String(decisionFilter || '').trim().toLowerCase();
    if (!q) return timeline;
    return timeline.filter((row) => {
      const text = `${row.agent_name || ''} ${row.phase || ''} ${row.event_type || ''}`.toLowerCase();
      return text.includes(q);
    });
  }, [timeline, decisionFilter]);

  const currentSessionMeta = useMemo(
    () => sessionOptions.find((item) => item.value === sessionId) || null,
    [sessionId, sessionOptions],
  );

  return (
    <div className="war-room-page">
      <Card className="module-card">
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            实时战情页
          </Title>
          <Text type="secondary">
            同屏查看调查时间线、证据链、工具调用与关键结论。支持从最近会话快速进入，避免空白页。
          </Text>
          {sessionOptions.length === 0 && !bootstrapLoading ? (
            <Alert
              type="info"
              showIcon
              message="当前没有可用会话。先在首页创建分析任务，或手工输入 session_id 再加载。"
            />
          ) : null}
          <Space wrap>
            <Select
              showSearch
              allowClear
              placeholder="选择最近会话"
              value={sessionId || undefined}
              style={{ minWidth: 420 }}
              loading={bootstrapLoading}
              options={sessionOptions.map((item) => ({ value: item.value, label: item.label }))}
              onChange={(value) => setSessionId(String(value || ''))}
            />
            <Input
              placeholder="输入会话ID（deb_xxx）"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              style={{ width: 280 }}
            />
            <Button type="primary" loading={loading} onClick={() => void load(sessionId)}>
              加载战情
            </Button>
            <Button loading={bootstrapLoading} onClick={() => void load()}>
              刷新
            </Button>
          </Space>
          {currentSessionMeta ? (
            <Space wrap>
              <Tag color="processing">Incident: {currentSessionMeta.incidentId}</Tag>
              <Tag color="blue">状态: {currentSessionMeta.status}</Tag>
            </Space>
          ) : null}
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="时间线事件" value={timeline.length} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="工具调用" value={toolAudit?.items?.length || 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="证据条数" value={Array.isArray(result?.evidence_chain) ? result?.evidence_chain.length : 0} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic
              title="结论置信度"
              value={result ? Number((Number(result.confidence || 0) * 100).toFixed(1)) : 0}
              suffix="%"
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card className="module-card" title="实时时间线" style={{ height: 360, overflow: 'auto' }}>
            {filteredTimeline.length === 0 ? (
              <Empty description="暂无时间线数据，请先加载会话" />
            ) : (
              <List
                size="small"
                dataSource={filteredTimeline.slice(0, 80)}
                renderItem={(row) => (
                  <List.Item>
                    <Space direction="vertical" size={0}>
                      <Text strong>
                        [{formatBeijingDateTime(row.timestamp)}] {row.event_type || row.kind}
                      </Text>
                      <Text type="secondary">
                        {row.agent_name || '-'} · {row.phase || '-'}
                      </Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card className="module-card" title="证据链" style={{ height: 360, overflow: 'auto' }}>
            {evidenceLines.length === 0 ? (
              <Empty description="暂无证据链" />
            ) : (
              <List
                size="small"
                dataSource={evidenceLines}
                renderItem={(line) => (
                  <List.Item>
                    <Text>{line}</Text>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card className="module-card" title="工具调用" style={{ height: 340, overflow: 'auto' }}>
            {toolAudit?.items?.length ? (
              <List
                size="small"
                dataSource={toolAudit.items}
                renderItem={(row) => (
                  <List.Item>
                    <Space direction="vertical" size={0}>
                      <Text strong>{String(row.event_type || 'tool_call')}</Text>
                      <Text type="secondary">
                        {formatBeijingDateTime(String(row.timestamp || ''))} · agent={String(row.agent_name || '-')}
                      </Text>
                    </Space>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="该会话暂无工具调用记录" />
            )}
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card className="module-card" title="关键结论" style={{ height: 340, overflow: 'auto' }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <div>
                <Tag color="processing">最终根因</Tag>
                <Text>{String(result?.root_cause || '暂无')}</Text>
              </div>
              <div>
                <Tag color="success">置信度</Tag>
                <Text>{result ? `${(Number(result.confidence || 0) * 100).toFixed(1)}%` : '-'}</Text>
              </div>
              {keyConclusions.length > 0 ? (
                <List
                  size="small"
                  dataSource={keyConclusions}
                  renderItem={(line) => (
                    <List.Item>
                      <Space direction="vertical" size={2} style={{ width: '100%' }}>
                        <Text>{line}</Text>
                        <Button
                          size="small"
                          type="link"
                          style={{ paddingInline: 0 }}
                          onClick={() => {
                            const keyword = String(line.split(':')[0] || '').trim();
                            setDecisionFilter(keyword);
                          }}
                        >
                          跳转到时间线
                        </Button>
                      </Space>
                    </List.Item>
                  )}
                />
              ) : (
                <Empty description="暂无关键结论" />
              )}
              {decisionFilter ? (
                <Button size="small" onClick={() => setDecisionFilter('')}>
                  清除时间线过滤：{decisionFilter}
                </Button>
              ) : null}
            </Space>
          </Card>
        </Col>
        <Col xs={24}>
          <Card className="module-card" title="报告摘要">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Text strong>{String(result?.root_cause || '暂无最终结论')}</Text>
              <Text type="secondary">
                证据数：{Array.isArray(result?.evidence_chain) ? result?.evidence_chain?.length : 0} · 根因候选：
                {Array.isArray(result?.root_cause_candidates) ? result?.root_cause_candidates?.length : 0}
              </Text>
              {!result ? (
                <Empty description="暂无报告结果，请先完成辩论" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <Descriptions bordered column={1} size="small">
                  <Descriptions.Item label="根因候选（TopK）">
                    {Array.isArray(result.root_cause_candidates) && result.root_cause_candidates.length > 0
                      ? result.root_cause_candidates
                          .slice(0, 3)
                          .map((item) => `#${item.rank} ${item.summary}（${(item.confidence * 100).toFixed(1)}%）`)
                          .join('；')
                      : '暂无'}
                  </Descriptions.Item>
                  <Descriptions.Item label="验证计划">
                    {Array.isArray(result.verification_plan) && result.verification_plan.length > 0
                      ? result.verification_plan
                          .slice(0, 3)
                          .map((item) => String(item.title || item.check || item.description || '-'))
                          .join('；')
                      : '暂无'}
                  </Descriptions.Item>
                  <Descriptions.Item label="修复建议">
                    {String(result.fix_recommendation?.summary || '暂无')}
                  </Descriptions.Item>
                </Descriptions>
              )}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default WarRoomPage;
