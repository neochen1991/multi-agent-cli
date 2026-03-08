import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Row, Space, Statistic, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import { debateApi, incidentApi, type Incident } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Text, Title } = Typography;

const statusColor: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  analyzing: 'processing',
  debating: 'blue',
  waiting: 'gold',
  retrying: 'orange',
  resolved: 'success',
  completed: 'success',
  failed: 'error',
  cancelled: 'default',
  closed: 'default',
};

const severityColor: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'gold',
  low: 'green',
};

const HistoryPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<Incident[]>([]);
  const [sessionMeta, setSessionMeta] = useState<
    Record<
      string,
      {
        mode: string;
        currentPhase: string;
        reviewStatus: string;
        reviewReason: string;
        confidence: number | null;
        limitedAnalysis: boolean;
        evidenceGap: boolean;
        evidenceCoverage: {
          ok: number;
          degraded: number;
          missing: number;
        };
      }
    >
  >({});

  const loadIncidents = async () => {
    setLoading(true);
    try {
      const data = await incidentApi.list(1, 50);
      setItems(data.items || []);
      const sessionIds = (data.items || [])
        .map((row) => String(row.debate_session_id || '').trim())
        .filter(Boolean)
        .slice(0, 20);
      if (sessionIds.length > 0) {
        const details = await Promise.all(
          sessionIds.map((sid) =>
            debateApi.get(sid).catch(() => null),
          ),
        );
        const results = await Promise.all(
          sessionIds.map((sid) =>
            debateApi.getResult(sid).catch(() => null),
          ),
        );
        const nextMeta: Record<
          string,
          {
            mode: string;
            currentPhase: string;
            reviewStatus: string;
            reviewReason: string;
            confidence: number | null;
            limitedAnalysis: boolean;
            evidenceGap: boolean;
            evidenceCoverage: {
              ok: number;
              degraded: number;
              missing: number;
            };
          }
        > = {};
        details.forEach((detail, idx) => {
          if (!detail) return;
          const sid = sessionIds[idx];
          const result = results[idx];
          const mode = String((detail.context || {}).execution_mode || 'standard');
          const currentPhase = String(detail.current_phase || '');
          const humanReview =
            detail.context && typeof detail.context.human_review === 'object' && !Array.isArray(detail.context.human_review)
              ? (detail.context.human_review as Record<string, unknown>)
              : {};
          const eventLog = Array.isArray((detail.context || {}).event_log) ? ((detail.context || {}).event_log as Array<Record<string, any>>) : [];
          const keyAgents = ['LogAgent', 'CodeAgent', 'DatabaseAgent', 'MetricsAgent'];
          const latestEvidenceStatus = new Map<string, string>();
          const limitedAnalysis = eventLog.some((row) => {
            const event = row && typeof row.event === 'object' && !Array.isArray(row.event)
              ? (row.event as Record<string, unknown>)
              : {};
            if (String(event.type || '').toLowerCase() === 'agent_command_feedback') {
              const agentName = String(event.agent_name || event.agent || '').trim();
              if (agentName && keyAgents.includes(agentName)) {
                latestEvidenceStatus.set(agentName, String(event.evidence_status || '').toLowerCase().trim() || 'collected');
              }
            }
            return String(event.type || '').toLowerCase() === 'agent_command_feedback'
              && String(event.evidence_status || '').toLowerCase() === 'inferred_without_tool';
          });
          const evidenceCoverage = { ok: 0, degraded: 0, missing: 0 };
          keyAgents.forEach((agentName) => {
            const status = latestEvidenceStatus.get(agentName);
            if (status === 'missing') {
              evidenceCoverage.missing += 1;
            } else if (status === 'degraded' || status === 'inferred_without_tool') {
              evidenceCoverage.degraded += 1;
            } else if (status) {
              evidenceCoverage.ok += 1;
            }
          });
          const riskFactors = Array.isArray(result?.risk_assessment?.risk_factors)
            ? result?.risk_assessment?.risk_factors
            : [];
          const evidenceGap = riskFactors.some((item: string) => String(item || '').includes('关键证据不足'));
          nextMeta[sid] = {
            mode,
            currentPhase,
            reviewStatus: String(humanReview.status || ''),
            reviewReason: String(humanReview.reason || ''),
            confidence: typeof result?.confidence === 'number' ? result.confidence : null,
            limitedAnalysis,
            evidenceGap,
            evidenceCoverage,
          };
        });
        setSessionMeta(nextMeta);
      } else {
        setSessionMeta({});
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '加载历史失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadIncidents();
  }, []);

  useEffect(() => {
    const hasActive = items.some((item) =>
      ['pending', 'running', 'analyzing', 'debating', 'waiting', 'retrying'].includes(item.status),
    );
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      void loadIncidents();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [items]);

  const summary = useMemo(() => {
    const running = items.filter((item) => ['pending', 'running', 'analyzing', 'debating', 'waiting', 'retrying'].includes(item.status)).length;
    const completed = items.filter((item) => ['resolved', 'completed', 'closed'].includes(item.status)).length;
    const failed = items.filter((item) => item.status === 'failed').length;
    return { total: items.length, running, completed, failed };
  }, [items]);

  const columns: ColumnsType<Incident> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 160 },
    { title: '标题', dataIndex: 'title', key: 'title' },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 120,
      render: (severity: string) =>
        severity ? <Tag color={severityColor[severity] || 'default'}>{severity.toUpperCase()}</Tag> : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 160,
      render: (status: string, record) => {
        const sid = String(record.debate_session_id || '');
        const reviewStatus = sid ? String(sessionMeta[sid]?.reviewStatus || '').toLowerCase() : '';
        if (status === 'waiting' && reviewStatus === 'pending') {
          return <Tag color="warning">waiting_review</Tag>;
        }
        if (status === 'waiting' && reviewStatus === 'approved') {
          return <Tag color="processing">waiting_resume</Tag>;
        }
        return <Tag color={statusColor[status] || 'default'}>{status}</Tag>;
      },
    },
    {
      title: '审核',
      key: 'review',
      width: 180,
      render: (_: unknown, record) => {
        const sid = String(record.debate_session_id || '');
        const reviewStatus = sid ? String(sessionMeta[sid]?.reviewStatus || '').toLowerCase() : '';
        const reviewReason = sid ? String(sessionMeta[sid]?.reviewReason || '') : '';
        if (!reviewStatus) return '-';
        if (reviewStatus === 'pending') {
          return <Tag color="warning" title={reviewReason || '等待人工审核'}>待人工审核</Tag>;
        }
        if (reviewStatus === 'approved') {
          return <Tag color="processing" title={reviewReason || '审核已通过'}>已批准待恢复</Tag>;
        }
        if (reviewStatus === 'rejected') {
          return <Tag color="error" title={reviewReason || '审核已驳回'}>人工已驳回</Tag>;
        }
        return <Tag>{reviewStatus}</Tag>;
      },
    },
    {
      title: '模式',
      key: 'mode',
      width: 120,
      render: (_: unknown, record) => {
        const sid = String(record.debate_session_id || '');
        const mode = sid ? String(sessionMeta[sid]?.mode || 'standard') : '-';
        return <Tag>{mode}</Tag>;
      },
    },
    {
      title: '分析质量',
      key: 'quality',
      width: 220,
      render: (_: unknown, record) => {
        const sid = String(record.debate_session_id || '');
        if (!sid || !sessionMeta[sid]) return '-';
        const meta = sessionMeta[sid];
        const confidence =
          typeof meta.confidence === 'number' ? `${(meta.confidence * 100).toFixed(1)}%` : '-';
        return (
          <div className="history-quality-cell">
            <Space wrap size={4}>
              <Tag>{`置信度 ${confidence}`}</Tag>
              {meta.limitedAnalysis ? <Tag color="gold">受限分析</Tag> : null}
              {meta.evidenceGap ? <Tag color="volcano">关键证据不足</Tag> : null}
            </Space>
            {(meta.evidenceCoverage.ok + meta.evidenceCoverage.degraded + meta.evidenceCoverage.missing) > 0 ? (
              <div className="history-evidence-coverage">
                <div className="history-evidence-coverage-bar">
                  <div
                    className="history-evidence-coverage-segment ok"
                    style={{ width: `${(meta.evidenceCoverage.ok / (meta.evidenceCoverage.ok + meta.evidenceCoverage.degraded + meta.evidenceCoverage.missing)) * 100}%` }}
                  />
                  <div
                    className="history-evidence-coverage-segment degraded"
                    style={{ width: `${(meta.evidenceCoverage.degraded / (meta.evidenceCoverage.ok + meta.evidenceCoverage.degraded + meta.evidenceCoverage.missing)) * 100}%` }}
                  />
                  <div
                    className="history-evidence-coverage-segment missing"
                    style={{ width: `${(meta.evidenceCoverage.missing / (meta.evidenceCoverage.ok + meta.evidenceCoverage.degraded + meta.evidenceCoverage.missing)) * 100}%` }}
                  />
                </div>
                <Text type="secondary">{`证据覆盖 成功${meta.evidenceCoverage.ok}/受限${meta.evidenceCoverage.degraded}/缺失${meta.evidenceCoverage.missing}`}</Text>
              </div>
            ) : null}
          </div>
        );
      },
    },
    {
      title: '预计耗时',
      key: 'eta',
      width: 140,
      render: (_: unknown, record) => {
        const sid = String(record.debate_session_id || '');
        const mode = sid ? String(sessionMeta[sid]?.mode || 'standard') : 'standard';
        if (['resolved', 'completed', 'closed', 'failed', 'cancelled'].includes(record.status)) {
          return '-';
        }
        if (mode === 'quick') return '1-3 分钟';
        if (mode === 'background' || mode === 'async') return '3-8 分钟';
        return '2-6 分钟';
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 250,
      render: (value: string) => formatBeijingDateTime(value),
    },
    {
      title: '操作',
      key: 'action',
      width: 240,
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/incident/${record.id}`)}>
            进入详情
          </Button>
          {(record.status === 'resolved' || record.status === 'closed' || record.status === 'completed') ? (
            <Button size="small" type="primary" onClick={() => navigate(`/incident/${record.id}?view=report`)}>
              查看结论
            </Button>
          ) : (
            <Button size="small" type="primary" onClick={() => navigate(`/incident/${record.id}?view=analysis`)}>
              继续处理
            </Button>
          )}
          {record.debate_session_id && ['pending', 'running', 'analyzing', 'debating', 'waiting', 'retrying'].includes(record.status) ? (
            <Button
              size="small"
              danger
              onClick={async () => {
                try {
                  await debateApi.cancel(String(record.debate_session_id || ''));
                  message.success('会话已取消');
                  await loadIncidents();
                } catch (e: any) {
                  message.error(e?.response?.data?.detail || e?.message || '取消失败');
                }
              }}
            >
              取消
            </Button>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <div className="history-page history-page-fixed">
      <Card className="module-card" style={{ marginBottom: 16 }}>
        <Space
          direction="vertical"
          size="middle"
          style={{ width: '100%' }}
        >
          <Space style={{ justifyContent: 'space-between', width: '100%' }} wrap>
            <div>
              <Title level={4} style={{ margin: 0 }}>
                历史记录
              </Title>
              <Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
                这里展示已创建故障的历史队列。你可以回看状态、继续分析进行中的会话，或者查看已完成的结论。
              </Paragraph>
            </div>
            <Space wrap>
              <Button type="primary" onClick={() => navigate('/incident')}>
                新建分析
              </Button>
              <Button onClick={() => void loadIncidents()} loading={loading}>
                刷新
              </Button>
            </Space>
          </Space>
          <Text type="secondary">
            推荐路径：先到“故障分析”创建任务，再回到这里跟踪状态、进入详情查看证据和结论。
          </Text>
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }} className="history-summary-row">
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="总事件" value={summary.total} />
            
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="进行中" value={summary.running} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="已完成" value={summary.completed} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="失败" value={summary.failed} valueStyle={{ color: '#cf1322' }} />
          </Card>
        </Col>
      </Row>

      <Card className="module-card history-table-card">
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          scroll={{ y: 'calc(100vh - 430px)', x: 1200 }}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: '暂无历史记录，点击“新建分析”创建第一条任务。' }}
        />
      </Card>
    </div>
  );
};

export default HistoryPage;
