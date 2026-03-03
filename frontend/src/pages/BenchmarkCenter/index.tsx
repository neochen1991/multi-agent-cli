import React, { useEffect, useState } from 'react';
import { Button, Card, Col, InputNumber, List, message, Row, Space, Statistic, Table, Tag, Typography } from 'antd';
import { benchmarkApi, type BaselineFile, type BenchmarkRunResult } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Title, Text } = Typography;

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

  return (
    <div>
      <Card className="module-card">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            评测中心
          </Title>
          <Space wrap>
            <Text>样本数</Text>
            <InputNumber min={1} max={20} value={limit} onChange={(v) => setLimit(Number(v || 3))} />
            <Text>超时(秒)</Text>
            <InputNumber min={30} max={1200} value={timeoutSeconds} onChange={(v) => setTimeoutSeconds(Number(v || 240))} />
            <Button type="primary" loading={loading} onClick={() => void runBenchmark()}>
              运行 Benchmark
            </Button>
          </Space>
          {latest ? <Text type="secondary">最近基线：{formatBeijingDateTime(latest.generated_at)}</Text> : null}
        </Space>
      </Card>

      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="Top1 命中率" value={Number(summary?.top1_rate || 0) * 100} suffix="%" precision={1} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="平均重叠分" value={Number(summary?.avg_overlap_score || 0)} precision={3} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="超时率" value={Number(summary?.timeout_rate || 0) * 100} suffix="%" precision={1} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card className="module-card compact-card">
            <Statistic title="空结论率" value={Number(summary?.empty_conclusion_rate || 0) * 100} suffix="%" precision={1} />
          </Card>
        </Col>
      </Row>

      <Card className="module-card" title="最近运行结果" style={{ marginTop: 16 }}>
        <Table
          rowKey={(row: any) => String(row.fixture_id || row.session_id || Math.random())}
          dataSource={lastRun?.cases || []}
          pagination={{ pageSize: 6 }}
          columns={[
            { title: '样本', dataIndex: 'fixture_id', key: 'fixture_id', width: 160 },
            { title: '状态', dataIndex: 'status', key: 'status', width: 120, render: (v: string) => <Tag>{v}</Tag> },
            { title: '命中分', dataIndex: 'overlap_score', key: 'overlap_score', width: 120 },
            { title: '耗时(ms)', dataIndex: 'duration_ms', key: 'duration_ms', width: 140 },
            { title: '根因摘要', dataIndex: 'predicted_root_cause', key: 'predicted_root_cause' },
          ]}
        />
      </Card>

      <Card className="module-card" title="历史基线文件" style={{ marginTop: 16 }}>
        <List
          size="small"
          dataSource={history}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={2}>
                <Text>{item.file}</Text>
                <Text type="secondary">
                  {formatBeijingDateTime(item.generated_at)} · Top1 {(Number(item.summary?.top1_rate || 0) * 100).toFixed(1)}%
                </Text>
              </Space>
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
};

export default BenchmarkCenterPage;

