import React from 'react';
import { Button, Card, Col, List, Row, Space, Tag, Typography } from 'antd';
import {
  ExperimentOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
  DeploymentUnitOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Paragraph, Text, Title } = Typography;

const advancedModules = [
  {
    key: '/workbench',
    title: '会话审计',
    subtitle: '当你想知道某个 session 为什么得出当前根因、哪一步最值得怀疑时，先来这里。',
    icon: <DeploymentUnitOutlined />,
    tag: '审计与回放',
    firstView: '优先查看结论、置信度、处置建议，再核查关键决策和原始审计。',
  },
  {
    key: '/governance',
    title: '运行治理',
    subtitle: '当你怀疑策略过激、超时变多、修复动作积压，或想确认平台是否值得继续信任时，先来这里。',
    icon: <SafetyCertificateOutlined />,
    tag: '治理与控制',
    firstView: '优先查看系统可信度、处置建议，再决定是否调整策略或执行治理动作。',
  },
  {
    key: '/benchmark',
    title: '质量评估',
    subtitle: '当你准备变更模型、prompt、规则或策略，或者怀疑最近命中率下降时，先来这里。',
    icon: <ExperimentOutlined />,
    tag: '评测与基线',
    firstView: '优先查看质量判断卡和处置建议，再执行 benchmark 或核查历史趋势。',
  },
  {
    key: '/tools',
    title: '工具管理',
    subtitle: '当你怀疑工具结果不可信、连接器异常、或要做受控试跑时，先来这里。',
    icon: <ToolOutlined />,
    tag: '接入与审计',
    firstView: '优先查看工具健康摘要，再执行连接、试跑或会话审计。',
  },
];

const scenarioRoutes = [
  '最近 timeout rate 抬高，怀疑策略或平台运行方式出了问题 -> 治理中心',
  '怀疑最近分析质量变差，想确认是回归还是样本偶然 -> 评测中心',
  '想复盘某个 session 为什么这样下结论 -> 调查复盘台',
  '怀疑工具或连接器不稳定，想判断工具结果能不能信 -> 工具中心',
];

const platformSummary = [
  {
    title: '治理与运行',
    tone: 'watch',
    hint: '先判断系统是否可信，再切策略或处理治理动作。',
  },
  {
    title: '质量评测',
    tone: 'info',
    hint: '先看质量方向，再决定是否跑 benchmark。',
  },
  {
    title: '调查复盘',
    tone: 'healthy',
    hint: '先看结论和推荐下一步，再下钻原始审计。',
  },
  {
    title: '工具健康',
    tone: 'watch',
    hint: '先看工具和连接器健康，再做连接和试跑。',
  },
];

const AdvancedPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="advanced-page">
      <Card className="module-card advanced-hero-card">
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Tag color="default" style={{ width: 'fit-content' }}>
            面向需要深度判断、复盘和控制的 SRE / 平台角色
          </Tag>
          <Title level={3} style={{ margin: 0 }}>
            高级控制台
          </Title>
          <Paragraph style={{ marginBottom: 0 }}>
            平时优先从“故障分析”和“历史记录”处理主流程。只有当你需要更深层的判断、复盘、治理或工具控制时，才进入这里。
          </Paragraph>
          <Text type="secondary">
            这里是治理、评测、审计与工具能力的统一入口。目标是先完成模块判定，再进入深层处置。
          </Text>
        </Space>
      </Card>

      <Card className="module-card ops-section-card" style={{ marginTop: 16 }}>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Title level={5} style={{ margin: 0 }}>
            控制台导航
          </Title>
          <Text type="secondary">按当前运维目标进入对应模块，不需要先理解整个平台内部结构。</Text>
        </Space>
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {advancedModules.map((module) => (
          <Col xs={24} md={12} key={module.key}>
            <Card className="module-card advanced-module-card dashboard-task-card">
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Space align="start" style={{ justifyContent: 'space-between', width: '100%' }}>
                  <Space align="start">
                    <div className="advanced-module-icon">{module.icon}</div>
                    <div>
                      <Title level={5} style={{ margin: 0 }}>
                        {module.title}
                      </Title>
                      <Text type="secondary">{module.tag}</Text>
                    </div>
                  </Space>
                  <Button type="link" onClick={() => navigate(module.key)}>
                    进入
                  </Button>
                </Space>
                <Paragraph style={{ marginBottom: 0 }}>{module.subtitle}</Paragraph>
                <Card size="small" className="ops-subtle-block">
                  <Text strong>优先查看</Text>
                  <Paragraph style={{ margin: '6px 0 0' }}>{module.firstView}</Paragraph>
                </Card>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={14}>
          <Card className="module-card ops-section-card">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                场景指引
              </Title>
              <List
                size="small"
                className="ops-list-tight"
                dataSource={scenarioRoutes}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="module-card ops-section-card">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                运行摘要
              </Title>
              <div className="mini-bar-list">
                {platformSummary.map((item) => (
                  <div key={item.title} className="mini-bar-row">
                    <div className="mini-bar-label-wrap">
                      <Text strong>{item.title}</Text>
                      <Text type="secondary">{item.hint}</Text>
                    </div>
                    <div className={`mini-state-pill tone-${item.tone}`}>{item.tone === 'healthy' ? '稳定' : item.tone === 'watch' ? '关注' : item.tone === 'risk' ? '风险' : '待判断'}</div>
                  </div>
                ))}
              </div>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default AdvancedPage;
