import React, { useMemo } from 'react';
import { Empty, Tag } from 'antd';

export type AgentNetworkNode = {
  id: string;
  label: string;
  role: 'commander' | 'specialist' | 'observer';
  inbound: number;
  outbound: number;
  activity: number;
};

export type AgentNetworkEdge = {
  id: string;
  source: string;
  target: string;
  relation: 'command' | 'feedback' | 'reply';
  count: number;
};

export type AgentNetworkStep = {
  id: string;
  source: string;
  target: string;
  relation: 'command' | 'feedback' | 'reply';
  count: number;
  clueCount?: number;
  toolCount?: number;
  keyClues?: string[];
};

type Props = {
  nodes: AgentNetworkNode[];
  edges: AgentNetworkEdge[];
  steps?: AgentNetworkStep[];
  selectedStepId?: string | null;
  onStepSelect?: (step: AgentNetworkStep) => void;
};

type Point = { x: number; y: number };

const LABEL_WIDTH = 180;
const STEP_WIDTH = 150;
const TOP_PADDING = 72;
const BOTTOM_PADDING = 48;
const LANE_GAP = 92;
const MIN_VIEW_WIDTH = 960;

const relationLabel: Record<AgentNetworkEdge['relation'], string> = {
  command: '下发指令',
  feedback: '反馈结果',
  reply: '对话回复',
};

const relationColor: Record<AgentNetworkEdge['relation'], string> = {
  command: '#2563eb',
  feedback: '#059669',
  reply: '#7c3aed',
};

const relationTagColor: Record<AgentNetworkEdge['relation'], string> = {
  command: 'blue',
  feedback: 'green',
  reply: 'purple',
};

const compactName = (name: string): string => {
  const plain = String(name || '').replace(/Agent$/i, '');
  if (plain.length <= 14) return plain || name;
  return `${plain.slice(0, 12)}...`;
};

const compactClue = (value: string): string => {
  const text = String(value || '').trim();
  if (text.length <= 12) return text;
  return `${text.slice(0, 10)}...`;
};

const AgentNetworkGraph: React.FC<Props> = ({
  nodes,
  edges,
  steps = [],
  selectedStepId = null,
  onStepSelect,
}) => {
  const orderedNodes = useMemo(() => {
    const roleOrder: Record<AgentNetworkNode['role'], number> = {
      commander: 0,
      specialist: 1,
      observer: 2,
    };
    return nodes.slice().sort((left, right) => {
      if (roleOrder[left.role] !== roleOrder[right.role]) {
        return roleOrder[left.role] - roleOrder[right.role];
      }
      if (left.id === 'ProblemAnalysisAgent') return -1;
      if (right.id === 'ProblemAnalysisAgent') return 1;
      return left.label.localeCompare(right.label);
    });
  }, [nodes]);

  const stepItems = useMemo<AgentNetworkStep[]>(() => {
    if (steps.length > 0) return steps;
    return edges.map((edge, index) => ({
      id: `${edge.id}_${index}`,
      source: edge.source,
      target: edge.target,
      relation: edge.relation,
      count: edge.count,
    }));
  }, [edges, steps]);

  const lanePositions = useMemo(() => {
    const map = new Map<string, Point>();
    orderedNodes.forEach((node, index) => {
      map.set(node.id, {
        x: LABEL_WIDTH,
        y: TOP_PADDING + index * LANE_GAP,
      });
    });
    return map;
  }, [orderedNodes]);

  const dimensions = useMemo(() => {
    const width = Math.max(MIN_VIEW_WIDTH, LABEL_WIDTH + 120 + stepItems.length * STEP_WIDTH);
    const height = Math.max(300, TOP_PADDING + Math.max(orderedNodes.length - 1, 0) * LANE_GAP + BOTTOM_PADDING);
    return { width, height };
  }, [orderedNodes.length, stepItems.length]);

  const stepX = (index: number) => LABEL_WIDTH + 110 + index * STEP_WIDTH;
  const midpoint = (sourceY: number, targetY: number) => (sourceY + targetY) / 2;

  if (nodes.length === 0) {
    return (
      <div className="agent-network-empty">
        <Empty description="暂无可绘制的 Agent 链路数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="agent-network-wrap">
      <div className="agent-network-legend">
        <Tag color="blue">主 Agent 泳道</Tag>
        <Tag color="cyan">专家 Agent 泳道</Tag>
        <Tag color="default">观察泳道</Tag>
        <Tag color="blue">下发指令</Tag>
        <Tag color="green">反馈结果</Tag>
        <Tag color="purple">对话回复</Tag>
      </div>
      <div className={`agent-network-scroll${orderedNodes.length > 6 ? ' is-scrollable' : ''}`}>
        <svg
          className="agent-network-svg"
          viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
          role="img"
          aria-label="Agent interaction sequence lanes"
        >
          <defs>
            <marker id="agent-seq-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
            </marker>
          </defs>

          <g className="agent-network-lanes">
            {orderedNodes.map((node) => {
              const point = lanePositions.get(node.id);
              if (!point) return null;
              return (
                <g key={node.id}>
                  <line
                    x1={LABEL_WIDTH}
                    y1={point.y}
                    x2={dimensions.width - 40}
                    y2={point.y}
                    className="agent-network-lane-line"
                  />
                  <g transform={`translate(20, ${point.y - 20})`}>
                    <rect
                      className={`agent-network-lane-pill is-${node.role}`}
                      width="138"
                      height="40"
                      rx="12"
                    />
                    <text x="12" y="17" className="agent-network-lane-title">
                      {compactName(node.label)}
                    </text>
                    <text x="12" y="31" className="agent-network-lane-meta">
                      出{node.outbound} / 入{node.inbound}
                    </text>
                  </g>
                </g>
              );
            })}
          </g>

          <g className="agent-network-step-guides">
            {stepItems.map((step, index) => {
              const x = stepX(index);
              return (
                <g key={`guide_${step.id}`}>
                  <line x1={x} y1={32} x2={x} y2={dimensions.height - 24} className="agent-network-step-line" />
                  <text x={x} y={20} textAnchor="middle" className="agent-network-step-index">
                    Step {index + 1}
                  </text>
                </g>
              );
            })}
          </g>

          <g className="agent-network-sequences">
            {stepItems.map((step, index) => {
              const source = lanePositions.get(step.source);
              const target = lanePositions.get(step.target);
              if (!source || !target) return null;
              const x = stepX(index);
              const midY = midpoint(source.y, target.y);
              const isDownward = target.y >= source.y;
              const stroke = relationColor[step.relation];
              const selected = selectedStepId === step.id;
              const dimmed = Boolean(selectedStepId) && !selected;
              return (
                <g
                  key={step.id}
                  className={`agent-network-step-group${selected ? ' is-selected' : ''}${dimmed ? ' is-dimmed' : ''}`}
                  onClick={() => onStepSelect?.(step)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onStepSelect?.(step);
                    }
                  }}
                >
                  <path
                    d={`M ${x - 26} ${source.y} L ${x} ${source.y} L ${x} ${target.y} L ${x + 26} ${target.y}`}
                    fill="none"
                    stroke={stroke}
                    strokeWidth={3}
                    strokeOpacity={0.88}
                    markerEnd="url(#agent-seq-arrow)"
                  />
                  <g transform={`translate(${x - 54}, ${midY - (isDownward ? 32 : 54)})`}>
                    <rect
                      width="108"
                      height="62"
                      rx="10"
                      className={`agent-network-step-card is-${step.relation}`}
                    />
                    <text x="54" y="15" textAnchor="middle" className="agent-network-step-card-title">
                      {relationLabel[step.relation]}
                    </text>
                    <text x="54" y="27" textAnchor="middle" className="agent-network-step-card-meta">
                      x{step.count}
                    </text>
                    <text x="54" y="39" textAnchor="middle" className="agent-network-step-card-submeta">
                      线索 {step.clueCount || 0} / 工具 {step.toolCount || 0}
                    </text>
                    <text x="54" y="53" textAnchor="middle" className="agent-network-step-card-clues">
                      {Array.isArray(step.keyClues) && step.keyClues.length > 0
                        ? step.keyClues.slice(0, 2).map(compactClue).join(' · ')
                        : '无关键线索'}
                    </text>
                  </g>
                  <text x={x} y={Math.min(source.y, target.y) - 10} textAnchor="middle" className="agent-network-link-meta">
                    {compactName(step.source)} {'->'} {compactName(step.target)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <div className="agent-network-stats">
        <span>节点 {nodes.length}</span>
        <span>链路 {edges.length}</span>
        <span>步骤 {stepItems.length}</span>
        <span>点击步骤可过滤右侧过程内容</span>
        {(['command', 'feedback', 'reply'] as AgentNetworkEdge['relation'][]).map((relation) => {
          const count = edges
            .filter((edge) => edge.relation === relation)
            .reduce((total, item) => total + item.count, 0);
          if (!count) return null;
          return (
            <Tag key={relation} color={relationTagColor[relation]}>
              {relationLabel[relation]}: {count}
            </Tag>
          );
        })}
      </div>
    </div>
  );
};

export default AgentNetworkGraph;
