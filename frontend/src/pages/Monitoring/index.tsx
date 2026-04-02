import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  monitoringApi,
  type MonitorStatusResponse,
  type MonitorTarget,
  type MonitorTargetCreatePayload,
} from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Text, Title } = Typography;

const severityColor: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'gold',
  low: 'green',
};

type TargetFormValues = {
  name: string;
  url: string;
  service_name: string;
  environment: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  check_interval_sec: number;
  timeout_sec: number;
  cooldown_sec: number;
  enabled: boolean;
  cookie_header: string;
  tags_text: string;
};

const splitTagText = (value: string): string[] =>
  String(value || '')
    .split(/[,，;\n；、|]+/)
    .map((item) => item.trim())
    .filter(Boolean);

const MonitoringPage: React.FC = () => {
  const [form] = Form.useForm<TargetFormValues>();
  const [status, setStatus] = useState<MonitorStatusResponse | null>(null);
  const [targets, setTargets] = useState<MonitorTarget[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [creating, setCreating] = useState(false);
  const [scanningId, setScanningId] = useState('');
  const [updatingId, setUpdatingId] = useState('');
  const [eventsTarget, setEventsTarget] = useState<MonitorTarget | null>(null);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);
  const [createTrace, setCreateTrace] = useState<{
    status: 'idle' | 'running' | 'success' | 'error';
    startedAt?: number;
    endedAt?: number;
    httpStatus?: number;
    message?: string;
  }>({ status: 'idle' });

  const loadAll = async (options?: { silent?: boolean }) => {
    const silent = Boolean(options?.silent);
    if (!silent) {
      setLoading(true);
    }
    try {
      const [statusData, targetData] = await Promise.all([
        monitoringApi.getStatus(),
        monitoringApi.listTargets(false),
      ]);
      setStatus(statusData);
      setTargets(targetData || []);
    } catch (error: any) {
      if (!silent) {
        message.error(error?.response?.data?.detail || error?.message || '加载监控配置失败');
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      // 中文注释：后台轮询使用静默刷新，避免“刷新按钮/表格一直 loading”的观感问题。
      void loadAll({ silent: true });
    }, 10000);
    return () => window.clearInterval(timer);
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await loadAll();
    } finally {
      setRefreshing(false);
    }
  };

  const handleStart = async () => {
    setStarting(true);
    try {
      await monitoringApi.start();
      message.success('页面巡检服务已启动');
      await loadAll();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '启动失败');
    } finally {
      setStarting(false);
    }
  };

  const handleStop = async () => {
    setStopping(true);
    try {
      await monitoringApi.stop();
      message.success('页面巡检服务已停止');
      await loadAll();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '停止失败');
    } finally {
      setStopping(false);
    }
  };

  const handleCreate = async (values: TargetFormValues) => {
    if (creating) {
      return;
    }
    setCreating(true);
    const startedAt = Date.now();
    setCreateTrace({ status: 'running', startedAt, message: '正在提交创建请求...' });
    // 中文注释：兜底定时器，防止极端情况下 Promise 状态异常导致按钮一直转圈。
    const creatingWatchdog = window.setTimeout(() => {
      setCreating(false);
      setCreateTrace({
        status: 'error',
        startedAt,
        endedAt: Date.now(),
        message: '创建请求超时（12s），请检查后端/API 代理后重试',
      });
      message.warning('创建请求超时，请检查后端可用性后重试');
    }, 12000);
    const payload: MonitorTargetCreatePayload = {
      name: values.name.trim(),
      url: values.url.trim(),
      service_name: values.service_name.trim(),
      environment: values.environment.trim() || 'prod',
      severity: values.severity,
      check_interval_sec: values.check_interval_sec,
      timeout_sec: values.timeout_sec,
      cooldown_sec: values.cooldown_sec,
      enabled: values.enabled,
      cookie_header: String(values.cookie_header || '').trim(),
      tags: splitTagText(values.tags_text),
      metadata: {},
    };
    try {
      const created = await Promise.race([
        monitoringApi.createTarget(payload),
        new Promise<never>((_, reject) => {
          window.setTimeout(() => reject(new Error('创建请求超时（8s）')), 8000);
        }),
      ]);
      message.success('巡检目标创建成功');
      setCreateTrace({
        status: 'success',
        startedAt,
        endedAt: Date.now(),
        httpStatus: 201,
        message: `创建成功：${created.id}`,
      });
      // 中文注释：先本地回填新目标，确保用户立刻看到新增结果，不依赖下一次轮询刷新。
      setTargets((prev) => [created, ...prev.filter((item) => item.id !== created.id)]);
      form.resetFields();
      form.setFieldsValue({
        enabled: true,
        severity: 'high',
        environment: 'prod',
        check_interval_sec: 60,
        timeout_sec: 20,
        cooldown_sec: 300,
        cookie_header: '',
      });
      void loadAll({ silent: true });
    } catch (error: any) {
      const detail = error?.response?.data?.detail || error?.message || '创建失败';
      const httpStatus = Number(error?.response?.status || 0) || undefined;
      setCreateTrace({
        status: 'error',
        startedAt,
        endedAt: Date.now(),
        httpStatus,
        message: String(detail),
      });
      message.error(detail);
    } finally {
      window.clearTimeout(creatingWatchdog);
      setCreating(false);
    }
  };

  const handleSwitchEnabled = async (row: MonitorTarget, checked: boolean) => {
    setUpdatingId(row.id);
    try {
      await monitoringApi.updateTarget(row.id, { enabled: checked });
      message.success(`已${checked ? '启用' : '停用'}目标`);
      await loadAll({ silent: true });
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '更新失败');
    } finally {
      setUpdatingId('');
    }
  };

  const handleDelete = async (row: MonitorTarget) => {
    setUpdatingId(row.id);
    try {
      await monitoringApi.deleteTarget(row.id);
      message.success('巡检目标已删除');
      await loadAll({ silent: true });
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '删除失败');
    } finally {
      setUpdatingId('');
    }
  };

  const handleScan = async (row: MonitorTarget) => {
    setScanningId(row.id);
    try {
      // 中文注释：手动巡检后立即刷新目标列表与事件流，保证用户留在当前页也能看到最新分析入口。
      const result = await monitoringApi.scanTarget(row.id);
      if (result.finding.has_error) {
        message.warning('检测到异常，系统已自动拉起故障分析流程');
      } else {
        message.success('巡检完成，未发现异常');
      }
      await Promise.all([loadAll({ silent: true }), openEvents(row)]);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '巡检失败');
    } finally {
      setScanningId('');
    }
  };

  const openEvents = async (row: MonitorTarget) => {
    setEventsTarget(row);
    setEventsLoading(true);
    try {
      const data = await monitoringApi.listEvents(row.id, 50);
      setEvents(Array.isArray(data.items) ? data.items : []);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载巡检事件失败');
      setEvents([]);
    } finally {
      setEventsLoading(false);
    }
  };

  const columns: ColumnsType<MonitorTarget> = [
    {
      title: '目标',
      key: 'name',
      render: (_, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{row.name}</Text>
          <Text type="secondary">{row.service_name || '-'}</Text>
        </Space>
      ),
    },
    {
      title: 'URL',
      dataIndex: 'url',
      key: 'url',
      ellipsis: true,
      render: (value: string) => <Text copyable={{ text: value }}>{value}</Text>,
    },
    {
      title: '环境',
      dataIndex: 'environment',
      key: 'environment',
      width: 90,
      render: (value: string) => <Tag>{String(value || 'prod').toUpperCase()}</Tag>,
    },
    {
      title: '告警级别',
      dataIndex: 'severity',
      key: 'severity',
      width: 104,
      render: (value: string) => <Tag color={severityColor[value] || 'default'}>{String(value || '').toUpperCase()}</Tag>,
    },
    {
      title: '巡检间隔',
      dataIndex: 'check_interval_sec',
      key: 'check_interval_sec',
      width: 106,
      render: (value: number) => `${value}s`,
    },
    {
      title: '最近巡检',
      dataIndex: 'last_checked_at',
      key: 'last_checked_at',
      width: 170,
      render: (value?: string) => formatBeijingDateTime(value, '-').replace(' (北京时间)', ''),
    },
    {
      title: '最近触发分析',
      dataIndex: 'last_triggered_at',
      key: 'last_triggered_at',
      width: 170,
      render: (value?: string) => formatBeijingDateTime(value, '-').replace(' (北京时间)', ''),
    },
    {
      title: '登录态',
      dataIndex: 'cookie_header',
      key: 'cookie_header',
      width: 88,
      render: (value: string) => (String(value || '').trim() ? <Tag color="blue">已配置</Tag> : <Tag>未配置</Tag>),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 72,
      render: (value: boolean, row) => (
        <Switch
          size="small"
          checked={Boolean(value)}
          loading={updatingId === row.id}
          onChange={(checked) => {
            void handleSwitchEnabled(row, checked);
          }}
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_, row) => (
        <Space size={4}>
          <Button
            size="small"
            loading={scanningId === row.id}
            onClick={() => {
              void handleScan(row);
            }}
          >
            立即巡检
          </Button>
          <Button
            size="small"
            onClick={() => {
              void openEvents(row);
            }}
          >
            查看事件
          </Button>
          <Button
            size="small"
            danger
            loading={updatingId === row.id}
            onClick={() => {
              void handleDelete(row);
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const eventDataSource = useMemo(
    () =>
      events.map((item, index) => ({
        key: `${index}`,
        checked_at: String(item.checked_at || ''),
        summary: String(item.summary || '-'),
        has_error: Boolean(item.has_error),
        frontend_errors: Array.isArray(item.frontend_errors) ? item.frontend_errors : [],
        api_errors: Array.isArray(item.api_errors) ? item.api_errors : [],
        browser_error: String(item.browser_error || ''),
      })),
    [events],
  );

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Title level={3} style={{ margin: 0 }}>自动监控中心</Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            监控指定业务页面，发现前端报错或接口异常后自动创建故障并拉起多 Agent 根因分析。
          </Paragraph>
          <Space wrap>
            <Tag color={status?.running ? 'success' : 'default'}>
              服务状态：{status?.running ? '运行中' : '已停止'}
            </Tag>
            <Tag>巡检目标：{status?.active_targets ?? 0}</Tag>
            <Tag>巡检周期：{status?.tick_seconds ?? '-'}s</Tag>
            <Tag>最近轮询：{formatBeijingDateTime(status?.last_loop_at, '-').replace(' (北京时间)', '')}</Tag>
          </Space>
          <Space wrap>
            <Button type="primary" loading={starting} onClick={() => void handleStart()}>
              启动巡检
            </Button>
            <Button loading={stopping} onClick={() => void handleStop()}>
              停止巡检
            </Button>
            <Button loading={refreshing} onClick={() => void handleRefresh()}>
              刷新
            </Button>
          </Space>
          <Alert
            type="info"
            showIcon
            message="异常触发后会自动创建 Incident、发起 Debate 会话，并引用知识库案例生成初始修复建议。"
          />
        </Space>
      </Card>

      <Card title="新增巡检目标">
        <Form<TargetFormValues>
          form={form}
          layout="vertical"
          initialValues={{
            enabled: true,
            severity: 'high',
            environment: 'prod',
            check_interval_sec: 60,
            timeout_sec: 20,
            cooldown_sec: 300,
            cookie_header: '',
          }}
          onFinish={(values) => {
            void handleCreate(values);
          }}
        >
          <Space align="start" wrap style={{ width: '100%' }}>
            <Form.Item label="名称" name="name" rules={[{ required: true, message: '请输入监控目标名称' }]}>
              <Input placeholder="例如：订单页 /checkout" style={{ width: 220 }} />
            </Form.Item>
            <Form.Item label="URL" name="url" rules={[{ required: true, message: '请输入页面 URL' }]}>
              <Input placeholder="https://example.com/checkout" style={{ width: 340 }} />
            </Form.Item>
            <Form.Item label="服务名" name="service_name">
              <Input placeholder="order-web" style={{ width: 180 }} />
            </Form.Item>
            <Form.Item label="环境" name="environment">
              <Input placeholder="prod" style={{ width: 120 }} />
            </Form.Item>
            <Form.Item label="严重程度" name="severity">
              <Select
                style={{ width: 120 }}
                options={[
                  { label: 'CRITICAL', value: 'critical' },
                  { label: 'HIGH', value: 'high' },
                  { label: 'MEDIUM', value: 'medium' },
                  { label: 'LOW', value: 'low' },
                ]}
              />
            </Form.Item>
            <Form.Item label="巡检间隔(秒)" name="check_interval_sec">
              <InputNumber min={15} max={3600} style={{ width: 130 }} />
            </Form.Item>
            <Form.Item label="超时(秒)" name="timeout_sec">
              <InputNumber min={5} max={120} style={{ width: 110 }} />
            </Form.Item>
            <Form.Item label="冷却(秒)" name="cooldown_sec">
              <InputNumber min={30} max={7200} style={{ width: 130 }} />
            </Form.Item>
            <Form.Item label="标签" name="tags_text">
              <Input placeholder="payment, checkout" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item label="Cookie(登录态)" name="cookie_header">
              <Input
                placeholder="例如：sessionid=xxx; token=yyy"
                style={{ width: 340 }}
              />
            </Form.Item>
            <Form.Item label="启用" name="enabled" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item label=" " colon={false}>
              <Button type="primary" htmlType="submit" loading={creating}>
                添加目标
              </Button>
            </Form.Item>
            <Form.Item label=" " colon={false}>
              <Text type={createTrace.status === 'error' ? 'danger' : 'secondary'}>
                最近提交：
                {createTrace.status === 'idle' ? '尚未提交' : ''}
                {createTrace.status === 'running' ? '提交中...' : ''}
                {createTrace.status === 'success' ? `成功（${createTrace.httpStatus || 201}）` : ''}
                {createTrace.status === 'error' ? `失败（${createTrace.httpStatus || '-'}）` : ''}
                {createTrace.message ? ` · ${createTrace.message}` : ''}
                {createTrace.startedAt && createTrace.endedAt
                  ? ` · ${createTrace.endedAt - createTrace.startedAt}ms`
                  : ''}
              </Text>
            </Form.Item>
          </Space>
        </Form>
      </Card>

      <Card title="巡检目标列表">
        <Table<MonitorTarget>
          loading={loading}
          rowKey="id"
          dataSource={targets}
          columns={columns}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          locale={{
            emptyText: <Empty description="暂无巡检目标，先添加一个页面开始监控" />,
          }}
          scroll={{ x: 1300 }}
        />
      </Card>

      <Drawer
        width={640}
        title={eventsTarget ? `巡检事件：${eventsTarget.name}` : '巡检事件'}
        open={Boolean(eventsTarget)}
        onClose={() => {
          setEventsTarget(null);
          setEvents([]);
        }}
      >
        <Table
          loading={eventsLoading}
          rowKey="key"
          dataSource={eventDataSource}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          columns={[
            {
              title: '时间',
              dataIndex: 'checked_at',
              key: 'checked_at',
              width: 160,
              render: (value: string) => formatBeijingDateTime(value, '-').replace(' (北京时间)', ''),
            },
            {
              title: '状态',
              dataIndex: 'has_error',
              key: 'has_error',
              width: 72,
              render: (value: boolean) => (value ? <Tag color="error">异常</Tag> : <Tag color="success">正常</Tag>),
            },
            {
              title: '摘要',
              dataIndex: 'summary',
              key: 'summary',
              render: (value: string, row: any) => (
                <Space direction="vertical" size={2}>
                  <Text>{value || '-'}</Text>
                  {row.frontend_errors?.length > 0 ? (
                    <Text type="danger">前端：{String(row.frontend_errors[0] || '')}</Text>
                  ) : null}
                  {row.api_errors?.length > 0 ? (
                    <Text type="danger">接口：{String(row.api_errors[0] || '')}</Text>
                  ) : null}
                  {row.browser_error ? <Text type="secondary">浏览器：{row.browser_error}</Text> : null}
                </Space>
              ),
            },
          ]}
        />
      </Drawer>
    </Space>
  );
};

export default MonitoringPage;
