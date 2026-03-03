import React, { useMemo, useState } from 'react';
import { Button, Card, Col, Empty, Input, List, Row, Space, Tag, Typography, message } from 'antd';
import {
  debateApi,
  lineageApi,
  settingsApi,
  type DebateResult,
  type LineageRecord,
  type ToolAuditResponse,
} from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Text, Title } = Typography;

const WarRoomPage: React.FC = () => {
  const [sessionId, setSessionId] = useState('');
  const [loading, setLoading] = useState(false);
  const [timeline, setTimeline] = useState<LineageRecord[]>([]);
  const [toolAudit, setToolAudit] = useState<ToolAuditResponse | null>(null);
  const [result, setResult] = useState<DebateResult | null>(null);
  const [keyConclusions, setKeyConclusions] = useState<string[]>([]);

  const load = async () => {
    const sid = sessionId.trim();
    if (!sid) {
      message.warning('请输入 session_id');
      return;
    }
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

  const evidenceLines = useMemo(() => {
    const rows = Array.isArray(result?.evidence_chain) ? result?.evidence_chain : [];
    return rows.map((row, idx) => {
      return `${idx + 1}. ${row.description}（${row.source}${row.source_ref ? ` / ${row.source_ref}` : ''}）`;
    });
  }, [result]);

  return (
    <div>
      <Card className="module-card">
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            战情页 v1
          </Title>
          <Space wrap>
            <Input
              placeholder="输入会话ID（deb_xxx）"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              style={{ width: 360 }}
            />
            <Button type="primary" loading={loading} onClick={() => void load()}>
              加载战情
            </Button>
          </Space>
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card className="module-card" title="实时时间线" style={{ height: 360, overflow: 'auto' }}>
            {timeline.length === 0 ? (
              <Empty description="暂无时间线，先输入会话ID加载" />
            ) : (
              <List
                size="small"
                dataSource={timeline.slice(0, 80)}
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
                      <Text>{line}</Text>
                    </List.Item>
                  )}
                />
              ) : (
                <Empty description="暂无关键结论" />
              )}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default WarRoomPage;
