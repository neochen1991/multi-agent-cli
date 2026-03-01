import React from 'react';
import { Button, Card, Collapse, Descriptions, Space, Tag, Timeline, Typography } from 'antd';
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
}) => {
  const { Text } = Typography;
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="会话信息">
        <Descriptions column={2}>
          <Descriptions.Item label="Incident ID">{incidentId || '-'}</Descriptions.Item>
          <Descriptions.Item label="Session ID">{sessionId || '-'}</Descriptions.Item>
          <Descriptions.Item label="实时状态">
            {running ? <Tag color="processing">运行中</Tag> : <Tag>待启动/已完成</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="辩论轮数">{debateMaxRounds}</Descriptions.Item>
        </Descriptions>
        <Button type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={() => void onStartRealtimeDebate()}>
          启动实时辩论
        </Button>
        <Space style={{ marginLeft: 12 }}>
          <Button danger onClick={() => void onCancel()}>
            取消分析
          </Button>
          <Button onClick={() => void onResume()}>恢复分析</Button>
          <Button onClick={() => void onRetryFailed()} disabled={!sessionId || running || loading}>
            仅重试失败Agent
          </Button>
        </Space>
      </Card>

      <Card title="辩论事件明细（流式对话）">
        {eventFiltersNode}
        {dialogueNode}
      </Card>

      <Card title="辩论轮次过程（可展开查看每轮输入输出）">
        {roundCollapseItems && roundCollapseItems.length > 0 ? <Collapse items={roundCollapseItems} /> : <Text type="secondary">暂无轮次数据</Text>}
      </Card>

      <Card title="辩论过程记录">
        {timelineItems && timelineItems.length > 0 ? <Timeline items={timelineItems} /> : <Text type="secondary">尚无过程记录</Text>}
      </Card>
    </Space>
  );
};

export default DebateProcessPanel;
