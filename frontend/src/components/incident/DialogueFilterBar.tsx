import React from 'react';
import { Button, Input, Select, Space, Tag } from 'antd';

type Props = {
  agents: string[];
  phases: string[];
  types: string[];
  selectedAgent: string;
  selectedPhase: string;
  selectedType: string;
  searchText: string;
  onAgentChange: (value: string) => void;
  onPhaseChange: (value: string) => void;
  onTypeChange: (value: string) => void;
  onSearchChange: (value: string) => void;
  onReset: () => void;
  filteredCount: number;
  totalCount: number;
};

const DialogueFilterBar: React.FC<Props> = ({
  agents,
  phases,
  types,
  selectedAgent,
  selectedPhase,
  selectedType,
  searchText,
  onAgentChange,
  onPhaseChange,
  onTypeChange,
  onSearchChange,
  onReset,
  filteredCount,
  totalCount,
}) => {
  return (
    <Space wrap style={{ marginBottom: 12 }}>
      <Select
        style={{ width: 180 }}
        value={selectedAgent}
        onChange={onAgentChange}
        options={agents.map((value) => ({
          label: value === 'all' ? '全部Agent' : value,
          value,
        }))}
      />
      <Select
        style={{ width: 180 }}
        value={selectedPhase}
        onChange={onPhaseChange}
        options={phases.map((value) => ({
          label: value === 'all' ? '全部阶段' : value,
          value,
        }))}
      />
      <Select
        style={{ width: 220 }}
        value={selectedType}
        onChange={onTypeChange}
        options={types.map((value) => ({
          label: value === 'all' ? '全部事件类型' : value,
          value,
        }))}
      />
      <Input
        allowClear
        style={{ width: 260 }}
        value={searchText}
        placeholder="搜索摘要/细节/trace_id"
        onChange={(e) => onSearchChange(e.target.value)}
      />
      <Button onClick={onReset}>重置筛选</Button>
      <Tag color="blue">{`显示 ${filteredCount} / ${totalCount} 条`}</Tag>
    </Space>
  );
};

export default DialogueFilterBar;
