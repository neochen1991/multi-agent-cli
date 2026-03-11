import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, Col, Row, Space, Statistic, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import { debateApi, incidentApi, type Incident } from '@/services/api';
import { formatBeijingDateTime, formatElapsedDuration } from '@/utils/dateTime';

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

const ACTIVE_STATUSES = ['pending', 'running', 'analyzing', 'debating', 'waiting', 'retrying'];
const TERMINAL_STATUSES = ['resolved', 'completed', 'closed', 'failed', 'cancelled'];
const RESULT_READY_STATUSES = ['resolved', 'completed'];
const compactBeijingDateTime = (value?: string): string =>
  formatBeijingDateTime(value, '--').replace(' (北京时间)', '');
const compactElapsedDuration = (value: string): string => value.replace(/^进行中\s*[·•]\s*/, '');
const resolveTaskStartTime = (
  record: Incident,
  meta?: {
    createdAt: string;
  } | null,
): string => {
  // 历史页里的“开始时间”优先展示分析任务真正启动的会话时间，缺失时再回退到事件创建时间。
  return String(meta?.createdAt || record.created_at || '');
};

const HistoryPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<Incident[]>([]);
  const [nowTs, setNowTs] = useState(() => Date.now());
  const missingResultSessionsRef = useRef<Set<string>>(new Set());
  const loadInFlightRef = useRef(false);
  const sessionMetaRef = useRef<
    Record<
      string,
      {
        mode: string;
        currentPhase: string;
        reviewStatus: string;
        reviewReason: string;
        createdAt: string;
        completedAt: string;
        updatedAt: string;
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
  const [sessionMeta, setSessionMeta] = useState<
    Record<
      string,
        {
          mode: string;
          currentPhase: string;
          reviewStatus: string;
          reviewReason: string;
          createdAt: string;
          completedAt: string;
          updatedAt: string;
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

  useEffect(() => {
    sessionMetaRef.current = sessionMeta;
  }, [sessionMeta]);

  const loadIncidents = async () => {
    // React StrictMode 下 effect 会重复触发，这里用 in-flight 门禁避免同一时间打出重复请求。
    if (loadInFlightRef.current) {
      return;
    }
    loadInFlightRef.current = true;
    setLoading(true);
    try {
      const data = await incidentApi.list(1, 50);
      setItems(data.items || []);
      const sessionIds = (data.items || [])
        .map((row) => String(row.debate_session_id || '').trim())
        .filter(Boolean)
        .slice(0, 20);
      if (sessionIds.length > 0) {
        const cachedMeta = sessionMetaRef.current;
        const itemBySessionId = new Map(
          (data.items || [])
            .map((row) => [String(row.debate_session_id || '').trim(), row] as const)
            .filter(([sid]) => Boolean(sid)),
        );
        // 终态会话的详情和结果在页面上基本不再变化，命中缓存后不再重复拉取，减少后台轮询噪声。
        const sessionIdsToRefresh = sessionIds.filter((sid) => {
          const incident = itemBySessionId.get(sid);
          const normalizedStatus = String(incident?.status || '').toLowerCase();
          if (ACTIVE_STATUSES.includes(normalizedStatus)) {
            return true;
          }
          return !cachedMeta[sid];
        });
        const details = await Promise.all(
          sessionIdsToRefresh.map((sid) =>
            debateApi.get(sid).catch(() => null),
          ),
        );
        const results = await Promise.all(
          sessionIdsToRefresh.map(async (sid) => {
            const incident = itemBySessionId.get(sid);
            const normalizedStatus = String(incident?.status || '').toLowerCase();
            // 只有明确产出了最终结论的会话才请求 result，避免 closed/failed 历史数据持续打 404。
            if (!incident || !RESULT_READY_STATUSES.includes(normalizedStatus)) {
              return null;
            }
            if (missingResultSessionsRef.current.has(sid)) {
              return null;
            }
            try {
              return await debateApi.getResult(sid);
            } catch (error: any) {
              if (error?.response?.status === 404) {
                missingResultSessionsRef.current.add(sid);
                return null;
              }
              return null;
            }
          }),
        );
        const nextMeta: Record<
          string,
          {
            mode: string;
            currentPhase: string;
            reviewStatus: string;
            reviewReason: string;
            createdAt: string;
            completedAt: string;
            updatedAt: string;
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
        // 只保留当前列表中需要展示的缓存，避免会话离开列表后继续占用内存。
        sessionIds.forEach((sid) => {
          if (cachedMeta[sid]) {
            nextMeta[sid] = cachedMeta[sid];
          }
        });
        details.forEach((detail, idx) => {
          if (!detail) return;
          const sid = sessionIdsToRefresh[idx];
          const result = results[idx];
          const context = (detail.context || {}) as Record<string, unknown>;
          const mode = String(context.requested_execution_mode || context.execution_mode || 'standard');
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
            createdAt: String(detail.created_at || ''),
            completedAt: String(detail.completed_at || ''),
            updatedAt: String(detail.updated_at || ''),
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
      loadInFlightRef.current = false;
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadIncidents();
  }, []);

  useEffect(() => {
    const hasActive = items.some((item) => ACTIVE_STATUSES.includes(item.status));
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      void loadIncidents();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [items]);

  useEffect(() => {
    const hasActive = items.some((item) => ACTIVE_STATUSES.includes(item.status));
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      setNowTs(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [items]);

  const summary = useMemo(() => {
    const running = items.filter((item) => ACTIVE_STATUSES.includes(item.status)).length;
    const completed = items.filter((item) => ['resolved', 'completed', 'closed'].includes(item.status)).length;
    const failed = items.filter((item) => item.status === 'failed').length;
    return { total: items.length, running, completed, failed };
  }, [items]);

  const columns: ColumnsType<Incident> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 122,
      ellipsis: true,
      render: (value: string) => <Text className="history-id-text">{value || '-'}</Text>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 220,
      ellipsis: true,
      render: (value: string) => <Text className="history-title-text" title={value}>{value || '-'}</Text>,
    },
    {
      title: '严重程度',
      dataIndex: 'severity',
      key: 'severity',
      width: 86,
      render: (severity: string) =>
        severity ? <Tag color={severityColor[severity] || 'default'}>{severity.toUpperCase()}</Tag> : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 94,
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
      width: 110,
      responsive: ['xxl'],
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
      width: 100,
      responsive: ['xxl'],
      render: (_: unknown, record) => {
        const sid = String(record.debate_session_id || '');
        const mode = sid ? String(sessionMeta[sid]?.mode || 'standard') : '-';
        return <Tag>{mode}</Tag>;
      },
    },
    {
      title: '分析质量',
      key: 'quality',
      width: 134,
      render: (_: unknown, record) => {
        const sid = String(record.debate_session_id || '');
        if (!sid || !sessionMeta[sid]) return '-';
        const meta = sessionMeta[sid];
        const confidence =
          typeof meta.confidence === 'number' ? `${(meta.confidence * 100).toFixed(1)}%` : '-';
        const totalCoverage =
          meta.evidenceCoverage.ok + meta.evidenceCoverage.degraded + meta.evidenceCoverage.missing;
        return (
          <div className="history-quality-cell">
            <div className="history-quality-tags">
              <Tag>{confidence}</Tag>
              {meta.limitedAnalysis ? <Tag color="gold">受限</Tag> : null}
              {meta.evidenceGap ? <Tag color="volcano">缺口</Tag> : null}
            </div>
            {totalCoverage > 0 ? (
              <div className="history-evidence-coverage">
                <div className="history-evidence-coverage-bar">
                  <div
                    className="history-evidence-coverage-segment ok"
                    style={{ width: `${(meta.evidenceCoverage.ok / totalCoverage) * 100}%` }}
                  />
                  <div
                    className="history-evidence-coverage-segment degraded"
                    style={{ width: `${(meta.evidenceCoverage.degraded / totalCoverage) * 100}%` }}
                  />
                  <div
                    className="history-evidence-coverage-segment missing"
                    style={{ width: `${(meta.evidenceCoverage.missing / totalCoverage) * 100}%` }}
                  />
                </div>
                <Text type="secondary">{`覆盖 ${meta.evidenceCoverage.ok}/${meta.evidenceCoverage.degraded}/${meta.evidenceCoverage.missing}`}</Text>
              </div>
            ) : null}
          </div>
        );
      },
    },
    {
      title: '分析耗时',
      key: 'duration',
      width: 116,
      render: (_: unknown, record) => {
        const sid = String(record.debate_session_id || '');
        const running = ACTIVE_STATUSES.includes(record.status);
        const meta = sid ? sessionMeta[sid] : null;
        if (meta) {
          const endAt = meta.completedAt || (running ? new Date(nowTs).toISOString() : meta.updatedAt);
          return compactElapsedDuration(formatElapsedDuration(meta.createdAt, endAt, running, '-'));
        }
        if (TERMINAL_STATUSES.includes(record.status)) return '-';
        return compactElapsedDuration(
          formatElapsedDuration(record.created_at, running ? new Date(nowTs).toISOString() : record.updated_at, running, '-'),
        );
      },
    },
    {
      title: '开始时间',
      key: 'started_at',
      width: 144,
      responsive: ['xl'],
      render: (_: unknown, record) => {
        const sid = String(record.debate_session_id || '');
        return compactBeijingDateTime(resolveTaskStartTime(record, sid ? sessionMeta[sid] : null));
      },
    },
    {
      title: '事件创建',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 144,
      responsive: ['xxl'],
      render: (value: string) => compactBeijingDateTime(value),
    },
    {
      title: '操作',
      key: 'action',
      width: 130,
      render: (_, record) => (
        <div className="history-action-links">
          <Button type="link" size="small" onClick={() => navigate(`/incident/${record.id}`)}>
            详情
          </Button>
          {(record.status === 'resolved' || record.status === 'closed' || record.status === 'completed') ? (
            <Button type="link" size="small" onClick={() => navigate(`/incident/${record.id}?view=report`)}>
              结论
            </Button>
          ) : (
            <Button type="link" size="small" onClick={() => navigate(`/incident/${record.id}?view=analysis`)}>
              继续
            </Button>
          )}
          {record.debate_session_id && ACTIVE_STATUSES.includes(record.status) ? (
            <Button
              size="small"
              type="link"
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
        </div>
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
          size="small"
          tableLayout="fixed"
          scroll={{ y: 'calc(100vh - 452px)', x: 900 }}
          pagination={{ pageSize: 10, size: 'small', showSizeChanger: false }}
          locale={{ emptyText: '暂无历史记录，点击“新建分析”创建第一条任务。' }}
        />
      </Card>
    </div>
  );
};

export default HistoryPage;
