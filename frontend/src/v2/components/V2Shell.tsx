import React from 'react';
void React;
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { formatBeijingDateTime } from '@/utils/dateTime';

type NavItem = {
  key: string;
  label: string;
  children?: Array<{ key: string; label: string }>;
};

const NAV_ITEMS: NavItem[] = [
  { key: '/v2', label: '首页总控台' },
  { key: '/v2/incident', label: '故障分析' },
  { key: '/v2/history', label: '历史会话' },
  { key: '/v2/assets', label: '责任田资产' },
  { key: '/v2/settings', label: '设置' },
  {
    key: '/v2/advanced',
    label: '高级能力',
    children: [
      { key: '/v2/tools', label: '工具中心' },
      { key: '/v2/replay', label: '调查回放' },
      { key: '/v2/benchmark', label: 'Benchmark' },
      { key: '/v2/governance', label: '治理中心' },
    ],
  },
];

const pageConfig = (pathname: string) => {
  if (pathname.startsWith('/v2/incident')) {
    return {
      title: 'Incident Investigation Workbench',
      subtitle: 'Evidence-first multi-agent investigation console',
      status: '按当前会话实时渲染',
      summaryTitle: '当前工作区',
      summaryText: '分析页优先展示结论、过程、责任田和证据链。未启动会话时显示真实空态，不填充示例数据。',
      statusTitle: '运行状态',
      statusText: '主 Agent、专家 Agent、工具审计和报告状态都应来自当前会话，不在 Shell 中伪造。',
    };
  }
  return {
    title: 'SRE Root Cause Console',
    subtitle: 'Production Incident Investigation Workspace',
    status: '控制台状态来自页面真实数据',
    summaryTitle: '本班次摘要',
    summaryText: '首页、历史页、责任田页和设置页都直接读取真实 API。无数据时显示空态，不展示演示数字。',
    statusTitle: '接入状态',
    statusText: '接入状态以设置页与首页的真实 connector / tooling 数据为准，Shell 只保留导航信息。',
  };
};

const V2Shell: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const config = pageConfig(location.pathname);
  const isRouteActive = (key: string): boolean =>
    location.pathname === key || location.pathname.startsWith(`${key}/`);

  return (
    <div className="v2-shell-page">
      <div className="shell">
        <header className="topbar">
          <div className="topbar-brand">
            <div className="logo">RC</div>
            <div className="brand-copy">
              <h1>{config.title}</h1>
              <p>{config.subtitle}</p>
            </div>
          </div>
          <div className="topbar-status">
            <div className="status-chip">{config.status}</div>
            <div>{formatBeijingDateTime(new Date())}</div>
          </div>
        </header>

        <div className="workspace">
          <aside className="sidebar">
            <div className="sidebar-section">
              <div className="sidebar-label">Navigation</div>
              <div className="nav-list">
                {NAV_ITEMS.map((item) => {
                  const childActive = Boolean(item.children?.some((child) => isRouteActive(child.key)));
                  const active = isRouteActive(item.key) || childActive;
                  return (
                    <div key={item.key} className="nav-group">
                      <button className={`nav-item${active ? ' active' : ''}`} onClick={() => navigate(item.key)}>
                        {item.label}
                      </button>
                      {item.children && active ? (
                        <div className="nav-sub-list">
                          {item.children.map((child) => {
                            const subActive = isRouteActive(child.key);
                            return (
                              <button
                                key={child.key}
                                className={`nav-sub-item${subActive ? ' active' : ''}`}
                                onClick={() => navigate(child.key)}
                              >
                                {child.label}
                              </button>
                            );
                          })}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="sidebar-section sidebar-card">
              <h3>{config.summaryTitle}</h3>
              <p>{config.summaryText}</p>
            </div>
            <div className="sidebar-section sidebar-card">
              <h4>{config.statusTitle}</h4>
              <p>{config.statusText}</p>
            </div>
          </aside>

          <main className="main v2-route-outlet">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
};

export default V2Shell;
