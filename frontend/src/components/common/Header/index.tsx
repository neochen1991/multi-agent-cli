import React from 'react';
import { Layout, Space, Tag } from 'antd';
import { GithubOutlined, RobotOutlined } from '@ant-design/icons';

const { Header: AntHeader } = Layout;

const AppHeader: React.FC = () => {
  return (
    <AntHeader className="app-header">
      <Space size={12} className="app-header-brand">
        <span className="app-header-logo" aria-hidden="true">
          <RobotOutlined />
        </span>
        <div className="app-header-title-wrap">
          <div className="app-header-title">生产问题根因分析智能体</div>
          <div className="app-header-subtitle">LangGraph Multi-Agent Runtime</div>
        </div>
      </Space>

      <Space size={12} className="app-header-actions">
        <Tag color="processing" style={{ margin: 0 }}>
          kimi-k2.5
        </Tag>
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          className="app-header-github"
          aria-label="GitHub"
        >
          <GithubOutlined />
        </a>
      </Space>
    </AntHeader>
  );
};

export default AppHeader;
