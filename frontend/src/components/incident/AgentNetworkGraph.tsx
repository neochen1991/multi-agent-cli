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

type Props = {
  nodes: AgentNetworkNode[];
  edges: AgentNetworkEdge[];
};

type Point = { x: number; y: number };

const WIDTH = 960;
const HEIGHT = 520;
const CENTER = { x: WIDTH / 2, y: HEIGHT / 2 };

const roleColor: Record<AgentNetworkNode['role'], string> = {
  commander: '#2563eb',
  specialist: '#0f766e',
  observer: '#6b7280',
};

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

const AgentNetworkGraph: React.FC<Props> = ({ nodes, edges }) => {
  const positions = useMemo(() => {
    const map = new Map<string, Point>();
    if (nodes.length === 0) return map;

    const commander =
      nodes.find((node) => node.role === 'commander') ||
      nodes.find((node) => node.id === 'ProblemAnalysisAgent') ||
      null;
    const rest = nodes
      .filter((node) => !commander || node.id !== commander.id)
      .slice()
      .sort((a, b) => a.label.localeCompare(b.label));

    if (commander) {
      map.set(commander.id, CENTER);
    }

    const total = rest.length;
    if (total === 0) return map;

    const radius = Math.min(WIDTH, HEIGHT) * (commander ? 0.34 : 0.36);
    rest.forEach((node, index) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / total;
      const x = CENTER.x + radius * Math.cos(angle);
      const y = CENTER.y + radius * Math.sin(angle);
      map.set(node.id, { x, y });
    });
    return map;
  }, [nodes]);

  const edgesWithOrder = useMemo(() => {
    const orderMap = new Map<string, number>();
    return edges.map((edge) => {
      const key = `${edge.source}->${edge.target}`;
      const order = orderMap.get(key) || 0;
      orderMap.set(key, order + 1);
      return { ...edge, order };
    });
  }, [edges]);

  const curveInfo = (source: Point, target: Point, order: number) => {
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len;
    const ny = dx / len;
    const offset = Math.min(56, 18 + order * 10);
    const direction = order % 2 === 0 ? 1 : -1;
    const cx = (source.x + target.x) / 2 + nx * offset * direction;
    const cy = (source.y + target.y) / 2 + ny * offset * direction;
    const labelX = 0.25 * source.x + 0.5 * cx + 0.25 * target.x;
    const labelY = 0.25 * source.y + 0.5 * cy + 0.25 * target.y;
    return {
      path: `M ${source.x} ${source.y} Q ${cx} ${cy} ${target.x} ${target.y}`,
      labelX,
      labelY,
    };
  };

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
        <Tag color="blue">主 Agent</Tag>
        <Tag color="cyan">专家 Agent</Tag>
        <Tag color="default">观察节点</Tag>
        <Tag color="blue">下发指令</Tag>
        <Tag color="green">反馈结果</Tag>
        <Tag color="purple">对话回复</Tag>
      </div>
      <svg
        className="agent-network-svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Agent interaction network graph"
      >
        <defs>
          <marker id="agent-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
          </marker>
        </defs>

        <g className="agent-network-grid">
          <circle cx={CENTER.x} cy={CENTER.y} r={Math.min(WIDTH, HEIGHT) * 0.34} />
          <circle cx={CENTER.x} cy={CENTER.y} r={Math.min(WIDTH, HEIGHT) * 0.2} />
        </g>

        <g className="agent-network-edges">
          {edgesWithOrder.map((edge) => {
            const source = positions.get(edge.source);
            const target = positions.get(edge.target);
            if (!source || !target) return null;
            const { path, labelX, labelY } = curveInfo(source, target, edge.order);
            const stroke = relationColor[edge.relation];
            const strokeWidth = Math.min(8, 1.4 + Math.log2(edge.count + 1) * 1.8);
            return (
              <g key={edge.id}>
                <path
                  d={path}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={strokeWidth}
                  strokeOpacity={0.8}
                  markerEnd="url(#agent-arrow)"
                />
                <text x={labelX} y={labelY} textAnchor="middle" className="agent-network-edge-label">
                  {relationLabel[edge.relation]} x{edge.count}
                </text>
              </g>
            );
          })}
        </g>

        <g className="agent-network-nodes">
          {nodes.map((node) => {
            const point = positions.get(node.id);
            if (!point) return null;
            const radius = Math.min(38, 20 + Math.log2(node.activity + 1) * 4);
            const fill = roleColor[node.role];
            return (
              <g key={node.id} transform={`translate(${point.x},${point.y})`}>
                <circle r={radius} fill={fill} fillOpacity={0.88} />
                <circle r={radius + 4} fill="none" stroke={fill} strokeOpacity={0.3} />
                <text y={-2} textAnchor="middle" className="agent-network-node-name">
                  {compactName(node.label)}
                </text>
                <text y={14} textAnchor="middle" className="agent-network-node-meta">
                  出{node.outbound} / 入{node.inbound}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="agent-network-stats">
        <span>节点 {nodes.length}</span>
        <span>链路 {edges.length}</span>
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
