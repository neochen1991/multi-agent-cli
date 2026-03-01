import React from 'react';
import { Button, Card, Collapse, Descriptions, Empty, Space, Statistic, Tabs, Tag } from 'antd';
import type { CollapseProps, TimelineProps } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';

type Props = {
  incidentId: string;
  sessionId: string;
  running: boolean;
  loading: boolean;
  debateMaxRounds: number;
  onStartRealtimeDebate: () => Promise<void>;
  onCancel: () => Promise<void>;
  onResume: () => Promise<void>;
  onRetryFailed: () => Promise<void>;
  eventFiltersNode: React.ReactNode;
  dialogueNode: React.ReactNode;
  roundCollapseItems: CollapseProps['items'];
  timelineItems: TimelineProps['items'];
  eventStats?: {
    total: number;
    filtered: number;
    agentCount: number;
    phaseCount: number;
  };
};

const DebateProcessPanel: React.FC<Props> = ({
  incidentId,
  sessionId,
  running,
  loading,
  debateMaxRounds,
  onStartRealtimeDebate,
  onCancel,
  onResume,
  onRetryFailed,
  eventFiltersNode,
  dialogueNode,
  roundCollapseItems,
  timelineItems,
  eventStats,
}) => {
  const stats = eventStats || { total: 0, filtered: 0, agentCount: 0, phaseCount: 0 };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="module-card" title="会话控制台" extra={<Tag color={running ? 'processing' : 'default'}>{running ? '运行中' : '未运行'}</Tag>}>
        <Descriptions column={2} size="small" styles={{ label: { width: 100 } }}>
          <Descriptions.Item label="Incident ID">{incidentId || '-'}</Descriptions.Item>
          <Descriptions.Item label="Session ID">{sessionId || '-'}</Descriptions.Item>
          <Descriptions.Item label="辩论轮数">{debateMaxRounds}</Descriptions.Item>
          <Descriptions.Item label="状态">{running ? '分析中' : '待启动 / 已完成'}</Descriptions.Item>
        </Descriptions>

        <Space wrap style={{ marginTop: 12 }}>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={running}
            onClick={() => void onStartRealtimeDebate()}
          >
            启动实时辩论
          </Button>
          <Button danger onClick={() => void onCancel()}>
            取消分析
          </Button>
          <Button onClick={() => void onResume()}>恢复分析</Button>
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
          defaultActiveKey="dialogue"
          items={[
            {
              key: 'dialogue',
              label: '对话流',
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {eventFiltersNode}
                  {dialogueNode}
                </Space>
              ),
            },
            {
              key: 'rounds',
              label: '轮次详情',
              children:
                roundCollapseItems && roundCollapseItems.length > 0 ? (
                  <Collapse items={roundCollapseItems} />
                ) : (
                  <Empty description="暂无轮次数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ),
            },
            {
              key: 'timeline',
              label: '事件时间线',
              children:
                timelineItems && timelineItems.length > 0 ? (
                  <div className="process-timeline-wrap">
                    <div className="process-timeline-list">
                      {timelineItems.map((item, index) => (
                        <div key={`${index}_${String(item.children)}`} className="process-timeline-item">
                          {item.children}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <Empty description="暂无时间线记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ),
            },
          ]}
        />
      </Card>
    </Space>
  );
};

export default DebateProcessPanel;
