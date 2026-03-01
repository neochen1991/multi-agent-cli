import React from 'react';
import { Alert, Button, Card, Descriptions, Space, Tag, Typography } from 'antd';
import type { Report } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Text, Paragraph } = Typography;

type MainConclusion = {
  text: string;
  timeText: string;
} | null;

type SummaryCard = {
  title: string;
  body: string;
};

type ReportSection = {
  title: string;
  body: string;
};

type Props = {
  mainAgentConclusion: MainConclusion;
  sessionStatus: string;
  sessionError: string;
  debateSummaryCards: SummaryCard[];
  reportResult: Report | null;
  reportSections: ReportSection[];
  reportLoading: boolean;
  incidentId: string;
  sessionId: string;
  onRegenerateReport: () => Promise<void>;
};

const DebateResultPanel: React.FC<Props> = ({
  mainAgentConclusion,
  sessionStatus,
  sessionError,
  debateSummaryCards,
  reportResult,
  reportSections,
  reportLoading,
  incidentId,
  sessionId,
  onRegenerateReport,
}) => {
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="主Agent结论">
        {mainAgentConclusion ? (
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Tag color="processing">ProblemAnalysisAgent</Tag>
            <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>{mainAgentConclusion.text}</Paragraph>
            <Text type="secondary">结论时间：{mainAgentConclusion.timeText}</Text>
          </Space>
        ) : sessionStatus === 'failed' ? (
          <Alert type="error" showIcon message={`辩论失败：${sessionError || '请查看辩论过程中的错误详情'}`} />
        ) : sessionStatus === 'completed' ? (
          <Alert
            type="warning"
            showIcon
            message="当前会话未生成有效大模型结论，系统已阻止报告兜底输出。请补充故障信息后重试分析。"
          />
        ) : (
          <Alert type="info" showIcon message="主Agent结论尚未生成，请先完成辩论过程" />
        )}
      </Card>

      <Card title="结构化辩论结果">
        {debateSummaryCards.length === 0 ? (
          <Alert type="info" showIcon message="辩论结构化结果暂不可用，请先完成分析流程。" />
        ) : (
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            {debateSummaryCards.map((section, index) => (
              <Card key={`debate_section_${index}`} size="small" title={section.title}>
                <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>{section.body}</Paragraph>
              </Card>
            ))}
          </Space>
        )}
      </Card>

      <Card
        title="报告结果"
        extra={
          <Button loading={reportLoading} onClick={() => void onRegenerateReport()} disabled={!incidentId}>
            重新生成报告
          </Button>
        }
      >
        {reportResult ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions size="small" column={2}>
              <Descriptions.Item label="报告ID">{reportResult.report_id}</Descriptions.Item>
              <Descriptions.Item label="生成时间">{formatBeijingDateTime(reportResult.generated_at)}</Descriptions.Item>
              <Descriptions.Item label="格式">{reportResult.format}</Descriptions.Item>
              <Descriptions.Item label="会话ID">{reportResult.debate_session_id || sessionId || '-'}</Descriptions.Item>
            </Descriptions>
            {reportSections.length === 0 ? (
              <Alert type="info" showIcon message="报告内容为空，请点击“重新生成报告”" />
            ) : (
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                {reportSections.map((section, index) => (
                  <Card key={`${section.title}_${index}`} size="small" title={section.title}>
                    <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>{section.body}</Paragraph>
                  </Card>
                ))}
              </Space>
            )}
          </Space>
        ) : (
          <Alert type="info" showIcon message="暂未生成报告，请先完成辩论或点击“重新生成报告”" />
        )}
      </Card>
    </Space>
  );
};

export default DebateResultPanel;
