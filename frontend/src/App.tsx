import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { Layout, Space, Spin } from 'antd';
import AppHeader from '@/components/common/Header';
import AppSider from '@/components/common/Sider';
import V2Routes from '@/v2/routes';

const HomePage = lazy(() => import('@/pages/Home'));
const IncidentPage = lazy(() => import('@/pages/Incident'));
const HistoryPage = lazy(() => import('@/pages/History'));
const AssetsPage = lazy(() => import('@/pages/Assets'));
const KnowledgePage = lazy(() => import('@/pages/Knowledge'));
const MonitoringPage = lazy(() => import('@/pages/Monitoring'));
const SettingsPage = lazy(() => import('@/pages/Settings'));
const InvestigationWorkbenchPage = lazy(() => import('@/pages/InvestigationWorkbench'));
const BenchmarkCenterPage = lazy(() => import('@/pages/BenchmarkCenter'));
const GovernanceCenterPage = lazy(() => import('@/pages/GovernanceCenter'));
const ToolsCenterPage = lazy(() => import('@/pages/ToolsCenter'));
const AdvancedPage = lazy(() => import('@/pages/Advanced'));

const { Content, Footer } = Layout;

const RouteLoading: React.FC = () => (
  <div
    style={{
      minHeight: 'calc(100vh - 180px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}
  >
    <Space direction="vertical" align="center" size="middle">
      <Spin size="large" />
      <span style={{ color: '#64748b' }}>页面加载中...</span>
    </Space>
  </div>
);

const LegacyShell: React.FC = () => (
  <Layout className="app-shell">
    <AppHeader />
    <Layout hasSider className="app-main-layout">
      <AppSider />
      <Layout className="app-content-shell">
        <Content className="app-content">
          <div className="page-container">
            <Outlet />
          </div>
        </Content>
        <Footer className="app-footer">
          SRE Debate Platform ©{new Date().getFullYear()} · 多 Agent 生产问题根因分析平台
        </Footer>
      </Layout>
    </Layout>
  </Layout>
);

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          {V2Routes}
          <Route element={<LegacyShell />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/incident" element={<IncidentPage />} />
            <Route path="/incident/:incidentId" element={<IncidentPage />} />
            <Route path="/events" element={<Navigate to="/history" replace />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/assets" element={<AssetsPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/monitoring" element={<MonitoringPage />} />
            <Route path="/advanced" element={<AdvancedPage />} />
            <Route path="/workbench" element={<InvestigationWorkbenchPage />} />
            <Route path="/benchmark" element={<BenchmarkCenterPage />} />
            <Route path="/governance" element={<GovernanceCenterPage />} />
            <Route path="/tools" element={<ToolsCenterPage />} />
            <Route path="/war-room" element={<Navigate to="/workbench" replace />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};

export default App;
