import React from 'react';
import { Button, Card, Collapse, Descriptions, Empty, Space, Statistic, Tabs, Tag } from 'antd';
import type { CollapseProps, TimelineProps } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';

type Props = {
  incidentId: string;
  sessionId: string;
  running: boolean;
  loading: boolean;
  sessionStatus?: string;
  debateMaxRounds: number;
  onStartRealtimeDebate: () => Promise<void>;
  onCancel: () => Promise<void>;
  onResume: () => Promise<void>;
  onApproveReview?: () => Promise<void>;
  onRejectReview?: () => Promise<void>;
  onRetryFailed: () => Promise<void>;
  activeTabKey: string;
  onTabChange: (key: string) => void;
  eventFiltersNode: React.ReactNode;
  networkFocusNode?: React.ReactNode;
  dialogueNode: React.ReactNode;
  agentNetworkNode?: React.ReactNode;
  roundCollapseItems: CollapseProps['items'];
  timelineItems: TimelineProps['items'];
  eventStats?: {
    total: number;
    filtered: number;
    agentCount: number;
    phaseCount: number;
  };
  humanReview?: {
    status: string;
    reason: string;
    resumeFromStep?: string;
    approver?: string;
    comment?: string;
  } | null;
};

const DebateProcessPanel: React.FC<Props> = ({
  incidentId,
  sessionId,
  running,
  loading,
  sessionStatus,
  debateMaxRounds,
  onStartRealtimeDebate,
  onCancel,
  onResume,
  onApproveReview,
  onRejectReview,
  onRetryFailed,
  activeTabKey,
  onTabChange,
  eventFiltersNode,
  networkFocusNode,
  dialogueNode,
  agentNetworkNode,
  roundCollapseItems,
  timelineItems,
  eventStats,
  humanReview,
}) => {
  const stats = eventStats || { total: 0, filtered: 0, agentCount: 0, phaseCount: 0 };
  const reviewStatus = String(humanReview?.status || '').toLowerCase();
  const effectiveStatus = reviewStatus === 'pending'
    ? '待人工审核'
    : reviewStatus === 'approved'
      ? '审核通过，待恢复'
      : reviewStatus === 'rejected'
        ? '人工驳回'
        : running
          ? '分析中'
          : (sessionStatus || '待启动 / 已完成');
  const statusTagColor = reviewStatus === 'pending'
    ? 'warning'
    : reviewStatus === 'approved'
      ? 'processing'
      : reviewStatus === 'rejected'
        ? 'error'
        : running
          ? 'processing'
          : 'default';

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="module-card" title="会话控制台" extra={<Tag color={statusTagColor}>{effectiveStatus}</Tag>}>
        <Descriptions column={2} size="small" styles={{ label: { width: 100 } }}>
          <Descriptions.Item label="Incident ID">{incidentId || '-'}</Descriptions.Item>
          <Descriptions.Item label="Session ID">{sessionId || '-'}</Descriptions.Item>
          <Descriptions.Item label="辩论轮数">{debateMaxRounds}</Descriptions.Item>
          <Descriptions.Item label="状态">{effectiveStatus}</Descriptions.Item>
          {humanReview ? (
            <>
              <Descriptions.Item label="审核原因" span={2}>
                {humanReview.reason || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="恢复节点">
                {humanReview.resumeFromStep || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="审核备注">
                {humanReview.comment || humanReview.approver || '-'}
              </Descriptions.Item>
            </>
          ) : null}
        </Descriptions>

        <Space wrap style={{ marginTop: 12 }}>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={running}
            disabled={loading || reviewStatus === 'pending'}
            onClick={() => void onStartRealtimeDebate()}
          >
            启动实时辩论
          </Button>
          <Button danger onClick={() => void onCancel()}>
            取消分析
          </Button>
          <Button
            onClick={() => void onResume()}
            disabled={!sessionId || running || loading || reviewStatus === 'pending'}
          >
            恢复分析
          </Button>
          {reviewStatus === 'pending' ? (
            <>
              <Button type="primary" onClick={() => void onApproveReview?.()} disabled={loading}>
                批准继续
              </Button>
              <Button danger onClick={() => void onRejectReview?.()} disabled={loading}>
                驳回结束
              </Button>
            </>
          ) : null}
          <Button onClick={() => void onRetryFailed()} disabled={!sessionId || running || loading}>
            仅重试失败 Agent
          </Button>
        </Space>
      </Card>

      <Card className="module-card" title="过程统计">
        <Space size="large" wrap>
          <Statistic title="总事件" value={stats.total} />
          <Statistic title="筛选后事件" value={stats.filtered} valueStyle={{ color: '#1677ff' }} />
          <Statistic title="参与 Agent" value={stats.agentCount} />
          <Statistic title="阶段数" value={stats.phaseCount} />
        </Space>
      </Card>

      <Card className="module-card" title="分析过程">
        <Tabs
          activeKey={activeTabKey}
          onChange={onTabChange}
          items={[
            {
              key: 'dialogue',
              label: '辩论对话',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {networkFocusNode}
                  {eventFiltersNode}
                  {dialogueNode}
                </Space>
              ),
            },
            {
              key: 'network',
              label: 'Agent链路图',
              children: agentNetworkNode ? (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {networkFocusNode}
                  {agentNetworkNode}
                </Space>
              ) : <Empty description="暂无Agent链路数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />,
            },
            {
              key: 'rounds',
              label: '轮次详情',
              children:
                roundCollapseItems && roundCollapseItems.length > 0 ? (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {networkFocusNode}
                    <Collapse items={roundCollapseItems} />
                  </Space>
                ) : (
                  <Empty description="暂无轮次数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ),
            },
            {
              key: 'events',
              label: '事件明细',
              children: (
                timelineItems && timelineItems.length > 0 ? (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {networkFocusNode}
                    <div className="process-timeline-wrap">
                      <div className="process-timeline-list">
                        {timelineItems.map((item, index) => (
                          <div key={`${index}_${String(item.children)}`} className="process-timeline-item">
                            {item.children}
                          </div>
                        ))}
                      </div>
                    </div>
                  </Space>
                ) : (
                  <Empty description="暂无事件明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
};

export default DebateProcessPanel;
