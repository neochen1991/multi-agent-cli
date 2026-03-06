import React from 'react';
import {
  Alert,
  Button,
  Card,
  Divider,
  Input,
  Select,
  Space,
  Tag,
  Typography,
  Upload,
  type UploadProps,
} from 'antd';

const { TextArea } = Input;
const { Text } = Typography;

type IncidentFormState = {
  title: string;
  description: string;
  severity: string;
  service_name: string;
  environment: string;
  log_content: string;
};

type LogUploadMeta = {
  name: string;
  size: number;
  lines: number;
} | null;

type Props = {
  incidentForm: IncidentFormState;
  running: boolean;
  loading: boolean;
  incidentId: string;
  sessionId: string;
  debateMaxRounds: number;
  executionMode: 'standard' | 'quick' | 'background' | 'async';
  logUploadMeta: LogUploadMeta;
  onFillDemoIncident: () => void;
  onChangeIncidentForm: (patch: Partial<IncidentFormState>) => void;
  onDebateMaxRoundsChange: (value: number) => void;
  onExecutionModeChange: (value: 'standard' | 'quick' | 'background' | 'async') => void;
  onLogFileUpload: UploadProps['beforeUpload'];
  onClearLogUploadMeta: () => void;
  onStartAnalysis: () => void;
  onCreateIncidentAndSession: () => void;
  onInitSessionForExistingIncident: () => void;
};

const IncidentOverviewPanel: React.FC<Props> = ({
  incidentForm,
  running,
  loading,
  incidentId,
  sessionId,
  debateMaxRounds,
  executionMode,
  logUploadMeta,
  onFillDemoIncident,
  onChangeIncidentForm,
  onDebateMaxRoundsChange,
  onExecutionModeChange,
  onLogFileUpload,
  onClearLogUploadMeta,
  onStartAnalysis,
  onCreateIncidentAndSession,
  onInitSessionForExistingIncident,
}) => {
  return (
    <Card
      className="module-card"
      title="概览与启动"
      extra={
        <Button onClick={onFillDemoIncident} disabled={running || loading}>
          填充示例故障
        </Button>
      }
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="填写故障标题、服务名和日志后直接启动分析；运行中去“调查过程”，完成后去“结论与行动”。"
        />

        <div className="incident-overview-status-strip">
          <Tag color={incidentId ? 'blue' : 'default'}>{incidentId ? `Incident: ${incidentId}` : '未创建事件'}</Tag>
          <Tag color={sessionId ? 'geekblue' : 'default'}>{sessionId ? `Session: ${sessionId}` : '未初始化会话'}</Tag>
          {running ? <Tag color="processing">分析进行中</Tag> : null}
          {incidentId && !sessionId ? <Tag color="gold">下一步：初始化分析会话</Tag> : null}
          {sessionId && !running ? <Tag color="cyan">可直接重新启动分析或切到其他分区查看</Tag> : null}
        </div>

        <div className="incident-overview-form-grid">
          <div>
            <Input
              placeholder="故障标题 *"
              value={incidentForm.title}
              onChange={(e) => onChangeIncidentForm({ title: e.target.value })}
            />
          </div>
          <div>
            <Input
              placeholder="故障描述"
              value={incidentForm.description}
              onChange={(e) => onChangeIncidentForm({ description: e.target.value })}
            />
          </div>
          <div>
            <Select
              value={incidentForm.severity}
              style={{ width: '100%' }}
              onChange={(value) => onChangeIncidentForm({ severity: value })}
              options={[
                { label: 'Critical', value: 'critical' },
                { label: 'High', value: 'high' },
                { label: 'Medium', value: 'medium' },
                { label: 'Low', value: 'low' },
              ]}
            />
          </div>
          <div>
            <Input
              placeholder="服务名（可选）"
              value={incidentForm.service_name}
              onChange={(e) => onChangeIncidentForm({ service_name: e.target.value })}
            />
          </div>
          <div>
            <Select
              value={debateMaxRounds}
              style={{ width: '100%' }}
              onChange={onDebateMaxRoundsChange}
              options={[
                { label: '辩论1轮', value: 1 },
                { label: '辩论2轮', value: 2 },
                { label: '辩论3轮', value: 3 },
                { label: '辩论4轮', value: 4 },
                { label: '辩论5轮', value: 5 },
                { label: '辩论6轮', value: 6 },
              ]}
            />
          </div>
          <div>
            <Select
              value={executionMode}
              style={{ width: '100%' }}
              onChange={onExecutionModeChange}
              options={[
                { label: 'Standard（实时）', value: 'standard' },
                { label: 'Quick（快速）', value: 'quick' },
                { label: 'Background（后台）', value: 'background' },
                { label: 'Async（异步）', value: 'async' },
              ]}
            />
          </div>
        </div>

        <Divider style={{ margin: 0 }} />
        <Space wrap>
          <Upload
            accept=".log,.txt,.out,.err,.trace,.stack,.json,.md"
            beforeUpload={onLogFileUpload}
            showUploadList={false}
            maxCount={1}
          >
            <Button>上传错误日志文件</Button>
          </Upload>
          {logUploadMeta && (
            <Text type="secondary">
              已上传：{logUploadMeta.name}（{Math.max(1, Math.round(logUploadMeta.size / 1024))}KB，
              {logUploadMeta.lines} 行）
            </Text>
          )}
        </Space>

        <TextArea
          rows={10}
          className="log-input-area"
          placeholder="粘贴日志内容、报错堆栈、监控现象。建议包含 traceId / URL / 状态码。"
          value={incidentForm.log_content}
          onChange={(e) => {
            const value = e.target.value;
            onChangeIncidentForm({ log_content: value });
            if (!value.trim()) {
              onClearLogUploadMeta();
            }
          }}
        />

        {!incidentId && (
          <Space>
            <Button
              type="primary"
              loading={loading || running}
              onClick={onStartAnalysis}
            >
              启动分析
            </Button>
            <Button loading={loading} onClick={onCreateIncidentAndSession}>
              仅创建故障与会话
            </Button>
          </Space>
        )}
        {incidentId && !sessionId && (
          <Space>
            <Button
              type="primary"
              loading={loading || running}
              onClick={onStartAnalysis}
            >
              初始化并启动分析
            </Button>
            <Button loading={loading} onClick={onInitSessionForExistingIncident}>
              使用当前故障初始化会话
            </Button>
          </Space>
        )}
        {incidentId && sessionId && (
          <Button type="primary" loading={loading || running} onClick={onStartAnalysis}>
            启动分析
          </Button>
        )}
      </Space>
    </Card>
  );
};

export default IncidentOverviewPanel;
