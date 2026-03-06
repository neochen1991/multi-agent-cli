import React, { useMemo, useState } from 'react';
import { Layout, Menu } from 'antd';
import {
  ApartmentOutlined,
  DeploymentUnitOutlined,
  AlertOutlined,
  HistoryOutlined,
  HomeOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';

const { Sider: AntSider } = Layout;

const AppSider: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const menuItems = useMemo(
    () => [
      {
        key: '/',
        icon: <HomeOutlined />,
        label: '首页',
      },
      {
        key: '/incident',
        icon: <AlertOutlined />,
        label: '故障分析',
      },
      {
        key: '/history',
        icon: <HistoryOutlined />,
        label: '历史记录',
      },
      {
        key: '/assets',
        icon: <ApartmentOutlined />,
        label: '责任田',
      },
      {
        key: '/settings',
        icon: <SettingOutlined />,
        label: '设置',
      },
      {
        key: '/advanced',
        icon: <DeploymentUnitOutlined />,
        label: '高级',
      },
    ],
    [],
  );

  const selectedKey = useMemo(() => {
    if (location.pathname === '/') return '/';
    if (
      location.pathname.startsWith('/incident')
    ) {
      return '/incident';
    }
    if (
      location.pathname.startsWith('/history')
      || location.pathname.startsWith('/events')
    ) {
      return '/history';
    }
    if (
      location.pathname.startsWith('/advanced')
      || location.pathname.startsWith('/workbench')
      || location.pathname.startsWith('/war-room')
      || location.pathname.startsWith('/benchmark')
      || location.pathname.startsWith('/governance')
      || location.pathname.startsWith('/tools')
    ) {
      return '/advanced';
    }
    const matched = menuItems
      .filter((item) => item.key !== '/')
      .find((item) => location.pathname.startsWith(item.key));
    return matched?.key || '/';
  }, [location.pathname, menuItems]);

  return (
    <AntSider
      className="app-sider"
      collapsible
      breakpoint="lg"
      collapsedWidth={70}
      width={224}
      collapsed={collapsed}
      onCollapse={(value) => setCollapsed(value)}
      onBreakpoint={(broken) => setCollapsed(broken)}
    >
      <div className="app-sider-title">导航</div>
      <Menu
        mode="inline"
        selectedKeys={[selectedKey]}
        items={menuItems}
        onClick={({ key }) => navigate(key)}
        className="app-sider-menu"
      />
    </AntSider>
  );
};

export default AppSider;
