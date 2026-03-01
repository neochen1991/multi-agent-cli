import React from 'react';
import { Alert, Button, Card, Collapse, Descriptions, Empty, Space, Statistic, Tag, Typography } from 'antd';
import type { Report } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const { Paragraph, Text } = Typography;

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
  debateConfidence?: number;
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
  debateConfidence,
  onRegenerateReport,
}) => {
  const confidence = typeof debateConfidence === 'number' ? Number((debateConfidence * 100).toFixed(1)) : null;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="module-card" title="主 Agent 最终结论">
        {mainAgentConclusion ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space wrap>
              <Tag color="processing">ProblemAnalysisAgent</Tag>
              <Tag color="blue">状态: {sessionStatus || '-'}</Tag>
              {confidence !== null ? <Tag color="geekblue">置信度: {confidence}%</Tag> : null}
            </Space>
            <Paragraph className="result-conclusion-paragraph">{mainAgentConclusion.text}</Paragraph>
            <Text type="secondary">结论时间：{mainAgentConclusion.timeText}</Text>
          </Space>
        ) : sessionStatus === 'failed' ? (
          <Alert type="error" showIcon message={`辩论失败：${sessionError || '请查看辩论过程中的错误详情'}`} />
        ) : sessionStatus === 'completed' ? (
          <Alert
            type="warning"
            showIcon
            message="当前会话未生成有效主结论，请补充日志细节后重新发起分析。"
          />
        ) : (
          <Alert type="info" showIcon message="主 Agent 结论尚未生成，请先完成辩论过程。" />
        )}
      </Card>

      <Card className="module-card" title="结构化辩论结果">
        {debateSummaryCards.length === 0 ? (
          <Empty description="结构化结果暂不可用，请先完成辩论流程" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Collapse
            items={debateSummaryCards.map((section, index) => ({
              key: `${section.title}_${index}`,
              label: section.title,
              children: <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>{section.body}</Paragraph>,
            }))}
          />
        )}
      </Card>

      <Card
        className="module-card"
        title="报告结果"
        extra={
          <Button loading={reportLoading} onClick={() => void onRegenerateReport()} disabled={!incidentId}>
            重新生成报告
          </Button>
        }
      >
        {reportResult ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Space size="large" wrap>
              <Statistic title="报告分段" value={reportSections.length} />
              <Statistic title="生成状态" value={reportSections.length > 0 ? '完成' : '空报告'} />
            </Space>
            <Descriptions size="small" column={2} styles={{ label: { width: 90 } }}>
              <Descriptions.Item label="报告 ID">{reportResult.report_id}</Descriptions.Item>
              <Descriptions.Item label="生成时间">{formatBeijingDateTime(reportResult.generated_at)}</Descriptions.Item>
              <Descriptions.Item label="输出格式">{reportResult.format}</Descriptions.Item>
              <Descriptions.Item label="会话 ID">{reportResult.debate_session_id || sessionId || '-'}</Descriptions.Item>
            </Descriptions>

            {reportSections.length === 0 ? (
              <Alert type="info" showIcon message="报告内容为空，请点击“重新生成报告”后重试。" />
            ) : (
              <Collapse
                items={reportSections.map((section, index) => ({
                  key: `${section.title}_${index}`,
                  label: section.title,
                  children: <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>{section.body}</Paragraph>,
                }))}
              />
            )}
          </Space>
        ) : (
          <Empty description="暂未生成报告，请先完成辩论或点击“重新生成报告”" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
    </Space>
  );
};

export default DebateResultPanel;
