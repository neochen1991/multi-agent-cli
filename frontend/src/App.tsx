import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from 'antd';
import AppHeader from '@/components/common/Header';
import AppSider from '@/components/common/Sider';
import HomePage from '@/pages/Home';
import IncidentPage from '@/pages/Incident';
import HistoryPage from '@/pages/History';
import AssetsPage from '@/pages/Assets';
import SettingsPage from '@/pages/Settings';

const { Content, Footer } = Layout;

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Layout className="app-shell">
        <AppHeader />
        <Layout hasSider className="app-main-layout">
          <AppSider />
          <Layout className="app-content-shell">
            <Content className="app-content">
              <div className="page-container">
                <Routes>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/incident" element={<IncidentPage />} />
                  <Route path="/incident/:incidentId" element={<IncidentPage />} />
                  <Route path="/history" element={<HistoryPage />} />
                  <Route path="/assets" element={<AssetsPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </div>
            </Content>
            <Footer className="app-footer">
              SRE Debate Platform ©{new Date().getFullYear()} · 多 Agent 生产问题根因分析平台
            </Footer>
          </Layout>
        </Layout>
      </Layout>
    </BrowserRouter>
  );
};

export default App;
