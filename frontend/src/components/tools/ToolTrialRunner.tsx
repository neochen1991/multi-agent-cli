import React from 'react';
import { Alert, Button, Card, Col, Empty, Form, Input, Row, Space, Switch, Typography } from 'antd';
import type { ToolTrialRunResponse } from '@/services/api';

const { Text } = Typography;

const toJson = (value: unknown): string => {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value || '');
  }
};

type TrialFormValues = {
  use_tool?: boolean;
  task?: string;
  focus?: string;
  expected_output?: string;
  service_name?: string;
  trace_id?: string;
  exception_class?: string;
  error_message?: string;
  log_content?: string;
};

type Props = {
  selectedToolName: string;
  loadingTrial: boolean;
  trialResult: ToolTrialRunResponse | null;
  onRun: (values: TrialFormValues) => Promise<void>;
};

const ToolTrialRunner: React.FC<Props> = ({ selectedToolName, loadingTrial, trialResult, onRun }) => {
  const [form] = Form.useForm<TrialFormValues>();

  React.useEffect(() => {
    if (!selectedToolName) return;
    form.setFieldsValue({
      use_tool: true,
      task: `请调用 ${selectedToolName} 获取故障证据`,
      focus: selectedToolName,
      expected_output: '返回关键证据摘要和原始片段',
    });
  }, [form, selectedToolName]);

  return (
    <Card className="module-card" title="参数试跑">
      {!selectedToolName ? (
        <Empty description="请选择工具后再进行试跑" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Row gutter={[12, 12]}>
          <Col xs={24} md={12}>
            <Form form={form} layout="vertical" initialValues={{ use_tool: true }}>
              <Form.Item label="允许工具调用" name="use_tool" valuePropName="checked">
                <Switch checkedChildren="允许" unCheckedChildren="禁用" />
              </Form.Item>
              <Form.Item label="任务描述" name="task" rules={[{ required: true, message: '请输入任务描述' }]}>
                <Input placeholder="例如：请读取日志并定位超时主因" />
              </Form.Item>
              <Form.Item label="关注点" name="focus">
                <Input placeholder="例如：/orders 502、connection pool timeout" />
              </Form.Item>
              <Form.Item label="期望输出" name="expected_output">
                <Input placeholder="例如：返回命中文件与关键证据片段" />
              </Form.Item>
              <Form.Item label="服务名" name="service_name">
                <Input placeholder="可选" />
              </Form.Item>
              <Form.Item label="Trace ID" name="trace_id">
                <Input placeholder="可选" />
              </Form.Item>
              <Form.Item label="异常类型" name="exception_class">
                <Input placeholder="可选" />
              </Form.Item>
              <Form.Item label="错误摘要" name="error_message">
                <Input placeholder="可选" />
              </Form.Item>
              <Form.Item label="日志样本" name="log_content">
                <Input.TextArea rows={6} placeholder="可选，建议粘贴核心错误日志片段" />
              </Form.Item>
              <Button
                type="primary"
                loading={loadingTrial}
                onClick={() => {
                  void form.validateFields().then((values) => onRun(values));
                }}
              >
                运行试跑
              </Button>
            </Form>
          </Col>
          <Col xs={24} md={12}>
            {!trialResult ? (
              <Empty description="试跑结果将在这里展示" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Alert
                  type={trialResult.status === 'ok' ? 'success' : trialResult.status === 'error' ? 'error' : 'info'}
                  message={`${trialResult.agent_name} / ${trialResult.tool_name}`}
                  description={
                    <Space direction="vertical" size={4}>
                      <Text>{trialResult.summary}</Text>
                      <Text type="secondary">
                        used={String(trialResult.used)} · enabled={String(trialResult.enabled)} · status={trialResult.status}
                      </Text>
                    </Space>
                  }
                />
                <Text type="secondary">工具返回：</Text>
                <pre className="dialogue-content">{toJson(trialResult.data || {})}</pre>
                <Text type="secondary">命令门禁：</Text>
                <pre className="dialogue-content">{toJson(trialResult.command_gate || {})}</pre>
                <Text type="secondary">审计记录：</Text>
                <pre className="dialogue-content">{toJson(trialResult.audit_log || [])}</pre>
              </Space>
            )}
          </Col>
        </Row>
      )}
    </Card>
  );
};

export default ToolTrialRunner;
