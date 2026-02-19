import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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
      <Layout style={{ minHeight: '100vh' }}>
        <AppHeader />
        <Layout>
          <AppSider />
          <Content style={{ padding: '24px', background: '#f0f2f5' }}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/incident" element={<IncidentPage />} />
              <Route path="/incident/:incidentId" element={<IncidentPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/assets" element={<AssetsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Content>
        </Layout>
        <Footer style={{ textAlign: 'center' }}>
          SRE Debate Platform ©{new Date().getFullYear()} - 多模型辩论式 SRE 智能体平台
        </Footer>
      </Layout>
    </BrowserRouter>
  );
};

export default App;
