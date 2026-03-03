import React, { useMemo, useState } from 'react';
import { Button, Card, Col, Empty, Input, List, message, Row, Space, Statistic, Table, Tag, Typography } from 'antd';
import { lineageApi, reportApi, type LineageRecord, type LineageResponse, type ReportDiff, type ReportVersion } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Text, Title } = Typography;

const InvestigationWorkbenchPage: React.FC = () => {
  const [sessionId, setSessionId] = useState('');
  const [incidentId, setIncidentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [records, setRecords] = useState<LineageRecord[]>([]);
  const [summary, setSummary] = useState<LineageResponse | null>(null);
  const [rendered, setRendered] = useState<string[]>([]);
  const [keyDecisions, setKeyDecisions] = useState<Array<Record<string, any>>>([]);
  const [evidenceRefs, setEvidenceRefs] = useState<string[]>([]);
  const [reportVersions, setReportVersions] = useState<ReportVersion[]>([]);
  const [reportDiff, setReportDiff] = useState<ReportDiff | null>(null);

  const load = async () => {
    const id = sessionId.trim();
    if (!id) {
      message.warning('请输入会话ID');
      return;
    }
    setLoading(true);
    try {
      const [lineage, replay] = await Promise.all([lineageApi.get(id, 300), lineageApi.replay(id, 120)]);
      setRecords(lineage.items || []);
      setSummary(lineage);
      setRendered(replay.rendered_steps || []);
      setKeyDecisions((replay.key_decisions || []) as Array<Record<string, any>>);
      setEvidenceRefs((replay.evidence_refs || []) as string[]);
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

  const columns = useMemo(
    () => [
      { title: '序号', dataIndex: 'seq', key: 'seq', width: 80 },
      { title: '类型', dataIndex: 'kind', key: 'kind', width: 120, render: (v: string) => <Tag>{v}</Tag> },
      { title: 'Agent', dataIndex: 'agent_name', key: 'agent_name', width: 180 },
      { title: '事件', dataIndex: 'event_type', key: 'event_type', width: 220 },
      {
        title: '时间',
        dataIndex: 'timestamp',
        key: 'timestamp',
        width: 220,
        render: (value: string) => formatBeijingDateTime(value),
      },
      {
        title: '概要',
        key: 'summary',
        render: (_: unknown, row: LineageRecord) => {
          const output = row.output_summary || {};
          return <Text type="secondary">{String(output.conclusion || row.payload?.message || '').slice(0, 120)}</Text>;
        },
      },
    ],
    [],
  );

  return (
    <div>
      <Card className="module-card">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            调查工作台
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
            <Input
              value={incidentId}
              onChange={(e) => setIncidentId(e.target.value)}
              placeholder="incident_id（用于报告对比）"
              style={{ width: 260 }}
            />
            <Button onClick={() => void loadReportVersions()}>加载报告版本</Button>
          </Space>
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="记录数" value={Number(summary?.records || 0)} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="事件数" value={Number(summary?.events || 0)} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="工具调用" value={Number(summary?.tools || 0)} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="Agent数" value={Array.isArray(summary?.agents) ? summary?.agents?.length : 0} />
          </Card>
        </Col>
      </Row>

      <Card className="module-card" title="事件时间线" style={{ marginTop: 16 }}>
        <Table rowKey={(row: LineageRecord) => `${row.seq}-${row.event_type}`} columns={columns} dataSource={records} pagination={{ pageSize: 8 }} />
      </Card>

      <Card className="module-card" title="回放步骤" style={{ marginTop: 16 }}>
        {rendered.length === 0 ? (
          <Empty description="暂无回放数据，先输入会话ID加载" />
        ) : (
          <List
            size="small"
            dataSource={rendered}
            renderItem={(item) => (
              <List.Item>
                <Text>{item}</Text>
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
                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 180, overflow: 'auto', margin: 0 }}>
                  {reportDiff.diff_lines.slice(0, 60).join('\n')}
                </pre>
              ) : null}
            </Space>
          </Card>
        ) : null}
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
