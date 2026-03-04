import React, { useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Divider, Empty, Input, List, Row, Select, Space, Table, Tag, Typography, message } from 'antd';
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

const { Text, Title } = Typography;

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
    const summaryAgents = Array.isArray(summary?.agents) ? summary?.agents.map((item) => String(item || '').trim()) : [];
    const decisionAgents = keyDecisions.map((row) => String(row.agent || '').trim()).filter(Boolean);
    const agents = [...summaryAgents, ...decisionAgents].filter(Boolean);
    return [...all, ...Array.from(new Set(agents))];
  }, [summary, keyDecisions]);

  return (
    <div>
      <Card className="module-card">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            调查复盘台
          </Title>
          <Alert
            type="info"
            showIcon
            message="本页已整合实时战情 + 调查复盘，无需在两个页面来回切换。"
          />
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
            <Input
              value={incidentId}
              onChange={(e) => setIncidentId(e.target.value)}
              placeholder="incident_id（用于报告对比）"
              style={{ width: 260 }}
            />
            <Button onClick={() => void loadReportVersions()}>加载报告版本</Button>
          </Space>
          <Space wrap>
            <Tag color="processing">谱系记录：{Number(summary?.records || 0)}</Tag>
            <Tag color="blue">事件：{Number(summary?.events || 0)}</Tag>
            <Tag color="gold">工具调用：{Number(summary?.tools || 0)}</Tag>
            <Tag color="purple">关键决策：{keyDecisions.length}</Tag>
            <Tag color="geekblue">证据引用：{evidenceRefs.length}</Tag>
            <Tag color="cyan">报告候选：{Array.isArray(debateResult?.root_cause_candidates) ? debateResult?.root_cause_candidates.length : 0}</Tag>
          </Space>
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card className="module-card" title="实时时间线（统一工作台）">
            {Array.isArray(summary?.items) && summary.items.length > 0 ? (
              <List
                size="small"
                dataSource={summary.items.slice(0, 80)}
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
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card className="module-card" title="工具调用（统一工作台）">
            {toolAudit?.items?.length ? (
              <List
                size="small"
                dataSource={toolAudit.items.slice(0, 60)}
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
          </Card>
        </Col>
        <Col xs={24}>
          <Card className="module-card" title="关键结论与证据链（统一工作台）">
            {!debateResult ? (
              <Empty description="暂无辩论结论，请先加载会话或等待分析完成" />
            ) : (
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <Text strong>{String(debateResult.root_cause || '暂无根因')}</Text>
                <Space wrap>
                  <Tag color="processing">置信度 {(Number(debateResult.confidence || 0) * 100).toFixed(1)}%</Tag>
                  <Tag color={debateResult.cross_source_passed ? 'green' : 'orange'}>
                    跨源证据{debateResult.cross_source_passed ? '通过' : '未通过'}
                  </Tag>
                  <Tag color="blue">Top-K {Array.isArray(debateResult.root_cause_candidates) ? debateResult.root_cause_candidates.length : 0}</Tag>
                </Space>
                {Array.isArray(debateResult.evidence_chain) && debateResult.evidence_chain.length > 0 ? (
                  <List
                    size="small"
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
            )}
          </Card>
        </Col>
      </Row>

      <Card className="module-card" title="回放步骤（决策剧本）" style={{ marginTop: 16 }}>
        {rendered.length === 0 ? (
          <Empty description="暂无回放数据，先输入会话ID加载" />
        ) : (
          <List
            size="small"
            dataSource={rendered}
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
      </Card>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card className="module-card" title="关键决策路径">
            {keyDecisions.length === 0 ? (
              <Empty description="暂无关键决策数据" />
            ) : (
              <List
                size="small"
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
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card className="module-card" title="证据引用">
            {evidenceRefs.length === 0 ? (
              <Empty description="暂无证据引用" />
            ) : (
              <List
                size="small"
                dataSource={evidenceRefs}
                renderItem={(item) => (
                  <List.Item>
                    <Text code>{item}</Text>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>

      <Card className="module-card" title="报告版本对比" style={{ marginTop: 16 }}>
        {reportDiff ? (
          <Card size="small" style={{ marginBottom: 12 }}>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text strong>{reportDiff.summary}</Text>
              <Text type="secondary">
                base={reportDiff.base_report_id || '-'} / target={reportDiff.target_report_id || '-'}
              </Text>
              {reportDiff.diff_lines?.length ? (
                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', margin: 0 }}>
                  {reportDiff.diff_lines.slice(0, 60).join('\n')}
                </pre>
              ) : null}
            </Space>
          </Card>
        ) : null}
        <Divider style={{ margin: '8px 0 12px' }} />
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
    </div>
  );
};

export default InvestigationWorkbenchPage;
