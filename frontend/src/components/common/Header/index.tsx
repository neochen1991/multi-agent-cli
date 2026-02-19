import React from 'react';
import { Layout, Typography, Space } from 'antd';
import { RobotOutlined, GithubOutlined } from '@ant-design/icons';

const { Header: AntHeader } = Layout;
const { Title, Text } = Typography;

const AppHeader: React.FC = () => {
  return (
    <AntHeader
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: '#001529',
        padding: '0 24px',
      }}
    >
      <Space>
        <RobotOutlined style={{ fontSize: '28px', color: '#1677ff' }} />
        <Title level={4} style={{ margin: 0, color: '#fff' }}>
          SRE Debate Platform
        </Title>
        <Text type="secondary" style={{ color: 'rgba(255,255,255,0.65)' }}>
          多模型辩论式 SRE 智能体平台
        </Text>
      </Space>
      
      <Space>
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: 'rgba(255,255,255,0.65)' }}
        >
          <GithubOutlined style={{ fontSize: '20px' }} />
        </a>
      </Space>
    </AntHeader>
  );
};

export default AppHeader;
