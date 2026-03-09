import React from 'react';
void React;
void React;
import { Navigate, Route } from 'react-router-dom';
import V2Shell from '@/v2/components/V2Shell';
import HomeV2 from '@/v2/pages/HomeV2';
import IncidentV2 from '@/v2/pages/IncidentV2';
import HistoryV2 from '@/v2/pages/HistoryV2';
import AssetsV2 from '@/v2/pages/AssetsV2';
import SettingsV2 from '@/v2/pages/SettingsV2';
import AdvancedV2 from '@/v2/pages/AdvancedV2';
import ReplayV2 from '@/v2/pages/ReplayV2';
import BenchmarkV2 from '@/v2/pages/BenchmarkV2';
import GovernanceV2 from '@/v2/pages/GovernanceV2';
import ToolsV2 from '@/v2/pages/ToolsV2';

const V2Routes = (
  <Route path="/v2" element={<V2Shell />}>
    <Route index element={<HomeV2 />} />
    <Route path="incident" element={<IncidentV2 />} />
    <Route path="incident/:incidentId" element={<IncidentV2 />} />
    <Route path="history" element={<HistoryV2 />} />
    <Route path="assets" element={<AssetsV2 />} />
    <Route path="settings" element={<SettingsV2 />} />
    <Route path="advanced" element={<AdvancedV2 />} />
    <Route path="replay" element={<ReplayV2 />} />
    <Route path="benchmark" element={<BenchmarkV2 />} />
    <Route path="governance" element={<GovernanceV2 />} />
    <Route path="tools" element={<ToolsV2 />} />
    <Route path="*" element={<Navigate to="/v2" replace />} />
  </Route>
);

export default V2Routes;
