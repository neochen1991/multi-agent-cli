import React, { useEffect, useMemo, useState } from 'react';
import { message } from 'antd';
import { Badge, PageHeader, Panel } from '@/v2/components/V2Common';
import { settingsApi, type ToolAuditResponse, type ToolConnector, type ToolRegistryItem, type ToolTrialRunResponse } from '@/services/api';
import { formatBeijingDateTime } from '@/utils/dateTime';

const ToolsV2: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [registry, setRegistry] = useState<ToolRegistryItem[]>([]);
  const [connectors, setConnectors] = useState<ToolConnector[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [selectedTool, setSelectedTool] = useState('');
  const [trialTask, setTrialTask] = useState('');
  const [trialResult, setTrialResult] = useState<ToolTrialRunResponse | null>(null);
  const [audit, setAudit] = useState<ToolAuditResponse | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [tools, connectorRes] = await Promise.all([
        settingsApi.getToolRegistry(),
        settingsApi.getToolConnectors(),
      ]);
      setRegistry(tools || []);
      setConnectors(connectorRes || []);
      if (!selectedTool && tools.length > 0) setSelectedTool(tools[0].tool_name);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载工具中心失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const loadAudit = async () => {
    if (!sessionId.trim()) {
      message.warning('请输入 session_id');
      return;
    }
    try {
      const result = await settingsApi.getToolAudit(sessionId.trim());
      setAudit(result);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '加载工具审计失败');
    }
  };

  const runTrial = async () => {
    if (!selectedTool) {
      message.warning('请选择工具');
      return;
    }
    try {
      const result = await settingsApi.trialRunTool({
        tool_name: selectedTool,
        use_tool: true,
        task: trialTask || `trial ${selectedTool}`,
        focus: 'v2 tools center',
      });
      setTrialResult(result);
      message.success('工具试跑完成');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '工具试跑失败');
    }
  };

  const selectedToolDetail = useMemo(() => registry.find((item) => item.tool_name === selectedTool) || null, [registry, selectedTool]);
  const enabledCount = registry.filter((item) => item.enabled).length;
  const unhealthyCount = connectors.filter((item) => item.healthy === false || ['error', 'disconnected'].includes(String(item.status || '').toLowerCase())).length;

  return (
    <>
      <PageHeader
        title="工具中心"
        desc="真实读取工具注册表、连接器、试跑结果和会话审计。用户先看工具归属与连接健康，再做试跑。"
        actions={
          <>
            <button className="btn" onClick={() => void load()} disabled={loading}>刷新连接器</button>
            <button className="btn primary" onClick={() => void runTrial()} disabled={!selectedTool}>执行试跑</button>
          </>
        }
      />

      <section className="grid-4">
        <div className="metric-card"><span className="eyebrow">Tools</span><strong>{registry.length}</strong><p>注册工具</p></div>
        <div className="metric-card"><span className="eyebrow">Enabled</span><strong>{enabledCount}</strong><p>已启用</p></div>
        <div className="metric-card"><span className="eyebrow">Connectors</span><strong>{connectors.length}</strong><p>连接器总数</p></div>
        <div className="metric-card"><span className="eyebrow">Unhealthy</span><strong>{unhealthyCount}</strong><p>异常连接器</p></div>
      </section>

      <section className="data-grid">
        <Panel title="工具总览" subtitle="真实 registry 列表；内容多时内部滚动。" extra={<Badge tone="brand">{registry.length} tools</Badge>}>
          <div className="table-scroll compact-scroll">
            <table className="table">
              <thead><tr><th>工具</th><th>Agent</th><th>状态</th><th>分类</th></tr></thead>
              <tbody>
                {registry.map((item) => (
                  <tr key={item.tool_name} className={selectedTool === item.tool_name ? 'active clickable-row' : 'clickable-row'} onClick={() => setSelectedTool(item.tool_name)}><td><span className="row-title">{item.tool_name}</span></td><td>{item.owner_agent}</td><td><Badge tone={item.enabled ? 'teal' : 'amber'}>{item.enabled ? 'enabled' : 'disabled'}</Badge></td><td>{item.category}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <div className="stack">
          <Panel title="参数试跑" subtitle="基于真实 tool trial API。">
            <div className="kv-list">
              <div className="kv-item"><h5>当前选中</h5><p>{selectedToolDetail ? `${selectedToolDetail.tool_name} · ${selectedToolDetail.owner_agent}` : '未选择工具'}</p></div>
              <div className="kv-item"><h5>试跑任务</h5><p><input className="v2-input" value={trialTask} onChange={(e) => setTrialTask(e.target.value)} placeholder="例如：trace OrderAppService transaction scope" /></p></div>
              <div className="kv-item"><h5>试跑摘要</h5><p>{trialResult?.summary || '尚未试跑'}</p></div>
            </div>
          </Panel>
          <Panel title="连接器状态" subtitle="真实 connector 健康状态。">
            <div className="scroll-region compact-scroll status-grid">
              {connectors.map((item) => (
                <div key={item.name} className="status-row"><div><div className="status-name">{item.name}</div><div className="status-meta">{item.resource} · {item.tools.join(', ')}</div></div><Badge tone={item.healthy === false || String(item.status || '').toLowerCase() === 'disconnected' ? 'red' : 'teal'}>{item.status || 'unknown'}</Badge></div>
              ))}
            </div>
          </Panel>
        </div>
      </section>

      <Panel title="会话审计" subtitle="输入真实 session_id 查询工具调用审计。">
        <div className="toolbar">
          <input className="v2-input" placeholder="session_id" value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
          <button className="btn" onClick={() => void loadAudit()}>加载审计</button>
        </div>
        <div className="timeline scroll-region compact-scroll">
          {audit?.items?.length ? audit.items.map((item) => (
            <div key={`${item.seq}-${item.timestamp}`} className="timeline-card"><div className="timeline-meta"><span>{formatBeijingDateTime(item.timestamp)}</span><span>{item.agent_name || '-'}</span></div><h4>{item.event_type}</h4><p>{JSON.stringify(item.output_summary || item.payload || {}, null, 2)}</p></div>
          )) : <div className="empty-note">暂无工具审计记录。</div>}
        </div>
      </Panel>
    </>
  );
};

export default ToolsV2;
