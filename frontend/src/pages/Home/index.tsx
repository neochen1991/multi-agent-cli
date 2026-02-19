import React from 'react';
import { Card, Row, Col, Statistic, Typography, Space, Button } from 'antd';
import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Title, Paragraph } = Typography;

const HomePage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="home-page">
      {/* 欢迎区域 */}
      <Card style={{ marginBottom: 24 }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Title level={2}>
            <RobotOutlined style={{ marginRight: 12, color: '#1677ff' }} />
            欢迎使用 SRE Debate Platform
          </Title>
          <Paragraph>
            多模型辩论式 SRE 智能体平台，基于 AutoGen 多 Agent 编排构建，实现三态资产融合与 AI 技术委员会决策系统。
          </Paragraph>
          <Space>
            <Button type="primary" size="large" onClick={() => navigate('/incident')}>
              开始故障分析
            </Button>
            <Button size="large" onClick={() => navigate('/history')}>
              查看历史记录
            </Button>
          </Space>
        </Space>
      </Card>

      {/* 统计区域 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="今日分析"
              value={0}
              prefix={<AlertOutlined />}
              valueStyle={{ color: '#1677ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="已解决"
              value={0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均耗时"
              value={0}
              suffix="分钟"
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="准确率"
              value={0}
              suffix="%"
              precision={1}
            />
          </Card>
        </Col>
      </Row>

      {/* 功能介绍 */}
      <Row gutter={16}>
        <Col span={8}>
          <Card title="🔥 三态资产融合" hoverable>
            <Paragraph>
              统一建模运行态、开发态、设计态资产，实现日志、代码、设计文档的自动关联。
            </Paragraph>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="🧠 多模型专家委员会" hoverable>
            <Paragraph>
              统一使用 kimi-k2.5 模型，按不同专家角色进行协同分析与技术裁决。
            </Paragraph>
          </Card>
        </Col>
        <Col span={8}>
          <Card title="⚖️ AI 内部辩论机制" hoverable>
            <Paragraph>
              通过质疑、反驳、裁决四阶段辩论流程，自我纠错，提高分析准确率。
            </Paragraph>
          </Card>
        </Col>
      </Row>

      {/* 专家角色介绍 */}
      <Card title="多模型专家分工" style={{ marginTop: 24 }}>
        <Row gutter={[16, 16]}>
          <Col span={8}>
            <Card size="small" style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}>
              <Statistic
                title="LogAgent"
                value="kimi-k2.5"
                valueStyle={{ fontSize: 16 }}
              />
              <Paragraph style={{ margin: 0 }}>日志结构化分析专家</Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" style={{ background: '#e6f7ff', borderColor: '#91d5ff' }}>
              <Statistic
                title="DomainAgent"
                value="kimi-k2.5"
                valueStyle={{ fontSize: 16 }}
              />
              <Paragraph style={{ margin: 0 }}>领域映射专家</Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" style={{ background: '#f9f0ff', borderColor: '#d3adf7' }}>
              <Statistic
                title="CodeAgent"
                value="kimi-k2.5"
                valueStyle={{ fontSize: 16 }}
              />
              <Paragraph style={{ margin: 0 }}>代码分析专家</Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" style={{ background: '#fff2e8', borderColor: '#ffbb96' }}>
              <Statistic
                title="CriticAgent"
                value="kimi-k2.5"
                valueStyle={{ fontSize: 16 }}
              />
              <Paragraph style={{ margin: 0 }}>架构质疑专家</Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" style={{ background: '#f0f5ff', borderColor: '#adc6ff' }}>
              <Statistic
                title="RebuttalAgent"
                value="kimi-k2.5"
                valueStyle={{ fontSize: 16 }}
              />
              <Paragraph style={{ margin: 0 }}>技术反驳专家</Paragraph>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" style={{ background: '#fff0f6', borderColor: '#ffadd2' }}>
              <Statistic
                title="JudgeAgent"
                value="kimi-k2.5"
                valueStyle={{ fontSize: 16 }}
              />
              <Paragraph style={{ margin: 0 }}>技术委员会主席</Paragraph>
            </Card>
          </Col>
        </Row>
      </Card>
    </div>
  );
};

export default HomePage;
