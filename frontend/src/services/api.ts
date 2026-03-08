import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 120000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sre_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  role: string;
  username: string;
}

export interface Incident {
  id: string;
  title: string;
  description?: string;
  severity?: string;
  status: string;
  source: string;
  service_name?: string;
  root_cause?: string;
  fix_suggestion?: string;
  debate_session_id?: string;
  created_at: string;
  updated_at: string;
  resolved_at?: string;
}

export interface AutoInvestigateTask {
  incident_id: string;
  session_id: string;
  task_id: string;
  status: string;
}

export interface AlertIngestPayload {
  alarm_id: string;
  service_name: string;
  title: string;
  description?: string;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  environment?: string;
  log_content?: string;
  exception_stack?: string;
  trace_id?: string;
  max_rounds?: number;
}

export interface DebateRound {
  round_number: number;
  phase: string;
  agent_name: string;
  agent_role: string;
  model?: Record<string, unknown>;
  input_message?: string;
  output_content?: Record<string, unknown>;
  confidence: number;
  started_at: string;
  completed_at?: string;
}

export interface DebateDetail {
  id: string;
  incident_id: string;
  status: string;
  current_phase?: string;
  current_round: number;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  rounds: DebateRound[];
  context: Record<string, unknown>;
}

export interface DebateResult {
  session_id: string;
  incident_id: string;
  root_cause: string;
  root_cause_category?: string;
  confidence: number;
  cross_source_passed?: boolean;
  root_cause_candidates?: Array<{
    rank: number;
    summary: string;
    source_agent?: string;
    confidence: number;
    confidence_interval?: number[];
    evidence_refs?: string[];
    evidence_coverage_count?: number;
    conflict_points?: string[];
    uncertainty_sources?: string[];
  }>;
  evidence_chain?: Array<{
    evidence_id?: string;
    type: string;
    description: string;
    source: string;
    source_ref?: string;
    location?: string;
    strength?: string;
  }>;
  fix_recommendation?: {
    summary?: string;
    steps?: Array<Record<string, unknown>>;
    code_changes_required?: boolean;
    rollback_recommended?: boolean;
    testing_requirements?: string[];
  };
  verification_plan?: Array<Record<string, unknown>>;
  impact_analysis?: {
    affected_services: string[];
    business_impact?: string;
  };
  risk_assessment?: {
    risk_level: string;
    risk_factors?: string[];
    mitigation_suggestions?: string[];
  };
  created_at: string;
}

export interface Report {
  report_id: string;
  incident_id: string;
  debate_session_id?: string;
  format: string;
  content: string;
  file_path?: string;
  generated_at: string;
}

export interface ReportVersion {
  report_id: string;
  incident_id: string;
  debate_session_id?: string;
  format: string;
  generated_at: string;
  content_preview: string;
}

export interface ReportDiff {
  incident_id: string;
  base_report_id?: string;
  target_report_id?: string;
  changed: boolean;
  summary: string;
  diff_lines: string[];
}

export interface AssetFusion {
  incident_id: string;
  debate_session_id: string;
  runtime_assets: Record<string, unknown>[];
  dev_assets: Record<string, unknown>[];
  design_assets: Record<string, unknown>[];
  relationships: Array<{
    source_id: string;
    source_type: string;
    target_id: string;
    target_type: string;
    relation: string;
  }>;
}

export interface InterfaceLocateResult {
  matched: boolean;
  confidence: number;
  reason: string;
  guidance: string[];
  interface_hints: Array<{ method: string; path: string }>;
  domain?: string;
  aggregate?: string;
  owner_team?: string;
  owner?: string;
  matched_endpoint?: {
    method: string;
    path: string;
    service?: string;
    interface?: string;
  };
  code_artifacts: Array<{ path: string; symbol: string }>;
  db_tables: string[];
  design_ref?: { doc: string; section: string };
  design_details?: {
    description?: string;
    invariants?: string[];
    entities?: string[];
    value_objects?: string[];
    domain_services?: string[];
    events?: string[];
  };
  similar_cases: Array<{
    id: string;
    title: string;
    api_endpoint?: string;
    root_cause?: string;
    solution?: string;
    fix_steps?: string[];
    tags?: string[];
  }>;
}

export interface ResponsibilityAssetRecord {
  asset_id: string;
  feature: string;
  domain: string;
  aggregate: string;
  frontend_pages: string[];
  api_interfaces: string[];
  code_items: string[];
  database_tables: string[];
  dependency_services: string[];
  monitor_items: string[];
  owner_team: string;
  owner: string;
  source_file: string;
  row_index?: number;
  created_at: string;
  updated_at: string;
}

export interface ResponsibilityAssetUploadResult {
  file_name: string;
  replace_existing: boolean;
  imported: number;
  stored: number;
  preview: ResponsibilityAssetRecord[];
}

export interface CodeRepoToolConfig {
  enabled: boolean;
  repo_url: string;
  access_token: string;
  branch: string;
  local_repo_path: string;
  max_hits: number;
}

export interface LogFileToolConfig {
  enabled: boolean;
  file_path: string;
  max_lines: number;
}

export interface DomainExcelToolConfig {
  enabled: boolean;
  excel_path: string;
  sheet_name: string;
  max_rows: number;
  max_matches: number;
}

export interface DatabaseToolConfig {
  enabled: boolean;
  engine: string;
  db_path: string;
  postgres_dsn: string;
  pg_schema: string;
  connect_timeout_seconds: number;
  max_rows: number;
}

export interface TelemetrySourceConfig {
  enabled: boolean;
  endpoint: string;
  api_token: string;
  timeout_seconds: number;
  verify_ssl: boolean;
}

export interface CMDBSourceConfig {
  enabled: boolean;
  endpoint: string;
  api_token: string;
  timeout_seconds: number;
  verify_ssl: boolean;
}

export interface PrometheusSourceConfig {
  enabled: boolean;
  endpoint: string;
  api_token: string;
  timeout_seconds: number;
  verify_ssl: boolean;
}

export interface LokiSourceConfig {
  enabled: boolean;
  endpoint: string;
  api_token: string;
  timeout_seconds: number;
  verify_ssl: boolean;
}

export interface GrafanaSourceConfig {
  enabled: boolean;
  endpoint: string;
  api_token: string;
  timeout_seconds: number;
  verify_ssl: boolean;
}

export interface APMSourceConfig {
  enabled: boolean;
  endpoint: string;
  api_token: string;
  timeout_seconds: number;
  verify_ssl: boolean;
}

export interface LogCloudSourceConfig {
  enabled: boolean;
  endpoint: string;
  api_token: string;
  timeout_seconds: number;
  verify_ssl: boolean;
}

export interface AlertPlatformSourceConfig {
  enabled: boolean;
  endpoint: string;
  api_token: string;
  timeout_seconds: number;
  verify_ssl: boolean;
}

export interface AgentSkillConfig {
  enabled: boolean;
  skills_dir: string;
  max_skills: number;
  max_skill_chars: number;
  allowed_agents: string[];
}

export interface AgentToolingConfig {
  code_repo: CodeRepoToolConfig;
  log_file: LogFileToolConfig;
  domain_excel: DomainExcelToolConfig;
  database?: DatabaseToolConfig;
  telemetry_source?: TelemetrySourceConfig;
  cmdb_source?: CMDBSourceConfig;
  prometheus_source?: PrometheusSourceConfig;
  loki_source?: LokiSourceConfig;
  grafana_source?: GrafanaSourceConfig;
  apm_source?: APMSourceConfig;
  logcloud_source?: LogCloudSourceConfig;
  alert_platform_source?: AlertPlatformSourceConfig;
  skills?: AgentSkillConfig;
  updated_at: string;
}

export interface BenchmarkSummary {
  cases: number;
  top1_rate: number;
  top3_rate?: number;
  avg_overlap_score: number;
  avg_duration_ms: number;
  avg_first_evidence_latency_ms?: number;
  p95_first_evidence_latency_ms?: number;
  failure_rate: number;
  timeout_rate: number;
  empty_conclusion_rate: number;
  cross_source_evidence_rate?: number;
}

export interface BenchmarkRunResult {
  generated_at: string;
  fixtures: number;
  summary: BenchmarkSummary;
  cases: Array<Record<string, unknown>>;
  baseline_file?: string;
}

export interface BaselineFile {
  file: string;
  generated_at: string;
  summary: BenchmarkSummary;
}

export interface LineageRecord {
  session_id: string;
  seq: number;
  kind: string;
  timestamp: string;
  phase: string;
  agent_name: string;
  event_type: string;
  confidence: number;
  duration_ms: number;
  payload?: Record<string, unknown>;
  input_summary?: Record<string, unknown>;
  output_summary?: Record<string, unknown>;
}

export interface LineageResponse {
  session_id: string;
  records: number;
  events: number;
  tools: number;
  agents: string[];
  first_ts?: string;
  last_ts?: string;
  items: LineageRecord[];
}

export interface ReplayResponse {
  session_id: string;
  count: number;
  rendered_steps: string[];
  summary: Record<string, unknown>;
  timeline: Array<Record<string, unknown>>;
  filters?: Record<string, unknown>;
  key_decisions?: Array<Record<string, unknown>>;
  evidence_refs?: string[];
}

export interface ToolRegistryItem {
  tool_name: string;
  category: string;
  owner_agent: string;
  enabled: boolean;
  input_schema: Record<string, unknown>;
  policy: Record<string, unknown>;
}

export interface ToolAuditResponse {
  session_id: string;
  count: number;
  items: LineageRecord[];
}

export interface ToolConnector {
  name: string;
  resource: string;
  tools: string[];
  connected?: boolean;
  healthy?: boolean;
  status?: string;
  last_probe_at?: string;
  last_error?: string;
  reconnect_attempts?: number;
}

export interface ToolTrialRunRequest {
  tool_name: string;
  use_tool?: boolean;
  task?: string;
  focus?: string;
  expected_output?: string;
  compact_context?: Record<string, unknown>;
  incident_context?: Record<string, unknown>;
}

export interface ToolTrialRunResponse {
  tool_name: string;
  agent_name: string;
  name: string;
  enabled: boolean;
  used: boolean;
  status: string;
  summary: string;
  data: Record<string, unknown>;
  command_gate: Record<string, unknown>;
  audit_log: Array<Record<string, unknown>>;
}

export const authApi = {
  async login(username: string, password: string): Promise<LoginResponse> {
    const { data } = await api.post<LoginResponse>('/auth/login', { username, password });
    return data;
  },
};

export const incidentApi = {
  async create(payload: {
    title: string;
    description?: string;
    severity?: string;
    log_content?: string;
    service_name?: string;
    environment?: string;
  }): Promise<Incident> {
    const { data } = await api.post<Incident>('/incidents/', payload);
    return data;
  },
  async list(
    page = 1,
    pageSize = 20,
    filters?: { status?: string; severity?: string; service_name?: string },
  ): Promise<{ items: Incident[]; total: number }> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (filters?.status) params.status = filters.status;
    if (filters?.severity) params.severity = filters.severity;
    if (filters?.service_name) params.service_name = filters.service_name;
    const { data } = await api.get('/incidents/', { params });
    return data;
  },
  async get(incidentId: string): Promise<Incident> {
    const { data } = await api.get<Incident>(`/incidents/${incidentId}`);
    return data;
  },
  async autoInvestigate(incidentId: string, maxRounds = 1): Promise<AutoInvestigateTask> {
    const { data } = await api.post<AutoInvestigateTask>(`/incidents/${incidentId}/auto-investigate`, null, {
      params: { max_rounds: maxRounds },
    });
    return data;
  },
  async ingestAlert(payload: AlertIngestPayload): Promise<AutoInvestigateTask> {
    const { data } = await api.post<AutoInvestigateTask>('/incidents/automation/alerts/ingest', payload);
    return data;
  },
};

export const debateApi = {
  async createSession(
    incidentId: string,
    options?: { maxRounds?: number; mode?: 'standard' | 'quick' | 'background' | 'async' },
  ): Promise<{ id: string; incident_id: string; status: string }> {
    const params: Record<string, string | number> = { incident_id: incidentId };
    if (typeof options?.maxRounds === 'number' && Number.isFinite(options.maxRounds)) {
      params.max_rounds = Math.max(1, Math.min(8, Math.trunc(options.maxRounds)));
    }
    if (options?.mode) {
      params.mode = options.mode;
    }
    const { data } = await api.post('/debates/', null, { params });
    return data;
  },
  async execute(sessionId: string, options?: { retryFailedOnly?: boolean }): Promise<DebateResult> {
    const params =
      typeof options?.retryFailedOnly === 'boolean'
        ? { retry_failed_only: options.retryFailedOnly }
        : undefined;
    const { data } = await api.post<DebateResult>(`/debates/${sessionId}/execute`, null, { params });
    return data;
  },
  async get(sessionId: string): Promise<DebateDetail> {
    const { data } = await api.get<DebateDetail>(`/debates/${sessionId}`);
    return data;
  },
  async getResult(sessionId: string): Promise<DebateResult> {
    const { data } = await api.get<DebateResult>(`/debates/${sessionId}/result`);
    return data;
  },
  async executeAsync(
    sessionId: string,
    options?: { retryFailedOnly?: boolean },
  ): Promise<{ task_id: string; status: string }> {
    const params =
      typeof options?.retryFailedOnly === 'boolean'
        ? { retry_failed_only: options.retryFailedOnly }
        : undefined;
    const { data } = await api.post(`/debates/${sessionId}/execute-async`, null, { params });
    return data;
  },
  async executeBackground(
    sessionId: string,
    options?: { retryFailedOnly?: boolean },
  ): Promise<{ task_id: string; status: string }> {
    const params =
      typeof options?.retryFailedOnly === 'boolean'
        ? { retry_failed_only: options.retryFailedOnly }
        : undefined;
    const { data } = await api.post(`/debates/${sessionId}/execute-background`, null, { params });
    return data;
  },
  async cancel(sessionId: string): Promise<{ session_id: string; cancelled: boolean }> {
    const { data } = await api.post(`/debates/${sessionId}/cancel`);
    return data;
  },
  async approveHumanReview(
    sessionId: string,
    approver = 'sre-oncall',
    comment = '',
  ): Promise<{ session_id: string; success: boolean; review_status: string; message: string }> {
    const { data } = await api.post(`/debates/${sessionId}/human-review/approve`, {
      approver,
      comment,
    });
    return data;
  },
  async rejectHumanReview(
    sessionId: string,
    approver = 'sre-oncall',
    reason = 'manual_reject',
  ): Promise<{ session_id: string; success: boolean; review_status: string; message: string }> {
    const { data } = await api.post(`/debates/${sessionId}/human-review/reject`, {
      approver,
      reason,
    });
    return data;
  },
  async getTask(taskId: string): Promise<{ task_id: string; status: string; result?: Record<string, unknown>; error?: string }> {
    const { data } = await api.get(`/debates/tasks/${taskId}`);
    return data;
  },
  async getOutputRef(refId: string): Promise<{
    ref_id: string;
    found: boolean;
    session_id: string;
    category: string;
    content: string;
    metadata: Record<string, unknown>;
    created_at: string;
  }> {
    const { data } = await api.get(`/debates/output-refs/${refId}`);
    return data;
  },
};

export const reportApi = {
  async get(incidentId: string): Promise<Report> {
    const { data } = await api.get<Report>(`/reports/${incidentId}`);
    return data;
  },
  async regenerate(incidentId: string): Promise<Report> {
    const { data } = await api.post<Report>(`/reports/${incidentId}/regenerate`);
    return data;
  },
  async share(incidentId: string): Promise<{ share_url: string; share_token: string }> {
    const { data } = await api.get(`/reports/${incidentId}/share`);
    return data;
  },
  async compare(incidentId: string): Promise<ReportVersion[]> {
    const { data } = await api.get<ReportVersion[]>(`/reports/${incidentId}/compare`);
    return data;
  },
  async compareDiff(incidentId: string): Promise<ReportDiff> {
    const { data } = await api.get<ReportDiff>(`/reports/${incidentId}/compare-diff`);
    return data;
  },
};

export const assetApi = {
  async fusion(incidentId: string): Promise<AssetFusion> {
    const { data } = await api.get<AssetFusion>(`/assets/fusion/${incidentId}`);
    return data;
  },
  async resources(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/assets/resources');
    return data;
  },
  async locate(logContent: string, symptom?: string): Promise<InterfaceLocateResult> {
    const { data } = await api.post<InterfaceLocateResult>('/assets/locate', {
      log_content: logContent,
      symptom,
    });
    return data;
  },
  async responsibilitySchema(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/assets/responsibility/schema');
    return data;
  },
  async listResponsibilityAssets(params?: {
    q?: string;
    domain?: string;
    aggregate?: string;
    api?: string;
  }): Promise<{ items: ResponsibilityAssetRecord[]; total: number }> {
    const { data } = await api.get<{ items: ResponsibilityAssetRecord[]; total: number }>(
      '/assets/responsibility',
      { params },
    );
    return data;
  },
  async upsertResponsibilityAsset(payload: {
    asset_id?: string;
    feature: string;
    domain: string;
    aggregate: string;
    frontend_pages?: string[];
    api_interfaces?: string[];
    code_items?: string[];
    database_tables?: string[];
    dependency_services?: string[];
    monitor_items?: string[];
    owner_team?: string;
    owner?: string;
  }): Promise<ResponsibilityAssetRecord> {
    const { data } = await api.post<ResponsibilityAssetRecord>('/assets/responsibility', payload);
    return data;
  },
  async deleteResponsibilityAsset(assetId: string): Promise<{ deleted: boolean; asset_id: string }> {
    const { data } = await api.delete<{ deleted: boolean; asset_id: string }>(
      `/assets/responsibility/${encodeURIComponent(assetId)}`,
    );
    return data;
  },
  async uploadResponsibilityAssets(
    file: File,
    replaceExisting = true,
  ): Promise<ResponsibilityAssetUploadResult> {
    const form = new FormData();
    form.append('file', file);
    form.append('replace_existing', String(replaceExisting));
    const { data } = await api.post<ResponsibilityAssetUploadResult>(
      '/assets/responsibility/upload',
      form,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    );
    return data;
  },
};

export const settingsApi = {
  async getTooling(): Promise<AgentToolingConfig> {
    const { data } = await api.get<AgentToolingConfig>('/settings/tooling');
    return data;
  },
  async updateTooling(payload: AgentToolingConfig): Promise<AgentToolingConfig> {
    const { data } = await api.put<AgentToolingConfig>('/settings/tooling', payload);
    return data;
  },
  async getToolRegistry(): Promise<ToolRegistryItem[]> {
    const { data } = await api.get<ToolRegistryItem[]>('/settings/tooling/registry');
    return data;
  },
  async getToolRegistryItem(toolName: string): Promise<ToolRegistryItem> {
    const { data } = await api.get<ToolRegistryItem>(`/settings/tooling/registry/${encodeURIComponent(toolName)}`);
    return data;
  },
  async getToolConnectors(): Promise<ToolConnector[]> {
    const { data } = await api.get<ToolConnector[]>('/settings/tooling/connectors');
    return data;
  },
  async connectToolConnector(connectorName: string): Promise<ToolConnector> {
    const { data } = await api.post<ToolConnector>(
      `/settings/tooling/connectors/${encodeURIComponent(connectorName)}/connect`,
    );
    return data;
  },
  async disconnectToolConnector(connectorName: string): Promise<ToolConnector> {
    const { data } = await api.post<ToolConnector>(
      `/settings/tooling/connectors/${encodeURIComponent(connectorName)}/disconnect`,
    );
    return data;
  },
  async listConnectorTools(connectorName: string): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>(
      `/settings/tooling/connectors/${encodeURIComponent(connectorName)}/tools`,
    );
    return data;
  },
  async callConnectorTool(
    connectorName: string,
    toolName: string,
    input: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>(
      `/settings/tooling/connectors/${encodeURIComponent(connectorName)}/call-tool/${encodeURIComponent(toolName)}`,
      { input },
    );
    return data;
  },
  async getToolAudit(sessionId: string): Promise<ToolAuditResponse> {
    const { data } = await api.get<ToolAuditResponse>(`/settings/tooling/audit/${sessionId}`);
    return data;
  },
  async trialRunTool(payload: ToolTrialRunRequest): Promise<ToolTrialRunResponse> {
    const { data } = await api.post<ToolTrialRunResponse>('/settings/tooling/trial-run', payload);
    return data;
  },
};

export const benchmarkApi = {
  async run(limit = 3, timeoutSeconds = 240): Promise<BenchmarkRunResult> {
    const { data } = await api.post<BenchmarkRunResult>('/benchmark/run', null, {
      params: { limit, timeout_seconds: timeoutSeconds },
    });
    return data;
  },
  async latest(): Promise<BaselineFile | null> {
    const { data } = await api.get<BaselineFile | null>('/benchmark/latest');
    return data;
  },
  async list(limit = 20): Promise<BaselineFile[]> {
    const { data } = await api.get<BaselineFile[]>('/benchmark/baselines', { params: { limit } });
    return data;
  },
};

export const lineageApi = {
  async get(sessionId: string, limit = 200): Promise<LineageResponse> {
    const { data } = await api.get<LineageResponse>(`/debates/${sessionId}/lineage`, { params: { limit } });
    return data;
  },
  async replay(
    sessionId: string,
    limit = 120,
    filters?: { phase?: string; agent?: string },
  ): Promise<ReplayResponse> {
    const { data } = await api.get<ReplayResponse>(`/debates/${sessionId}/replay`, {
      params: {
        limit,
        phase: filters?.phase || '',
        agent: filters?.agent || '',
      },
    });
    return data;
  },
};

export const governanceApi = {
  async systemCard(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/system-card');
    return data;
  },
  async qualityTrend(limit = 20): Promise<{ items: Array<Record<string, unknown>> }> {
    const { data } = await api.get<{ items: Array<Record<string, unknown>> }>('/governance/quality-trend', {
      params: { limit },
    });
    return data;
  },
  async costEstimate(caseCount = 100): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/cost-estimate', {
      params: { case_count: caseCount },
    });
    return data;
  },
  async submitFeedback(payload: {
    incident_id: string;
    session_id: string;
    verdict: 'adopt' | 'reject' | 'revise';
    comment: string;
    tags?: string[];
  }): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>('/governance/feedback', payload);
    return data;
  },
  async listFeedback(limit = 50): Promise<{ items: Array<Record<string, unknown>> }> {
    const { data } = await api.get<{ items: Array<Record<string, unknown>> }>('/governance/feedback', {
      params: { limit },
    });
    return data;
  },
  async feedbackLearningCandidates(limit = 200): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/feedback/learning-candidates', {
      params: { limit },
    });
    return data;
  },
  async abEvaluate(strategyA = 'baseline', strategyB = 'candidate'): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>('/governance/ab-evaluate', null, {
      params: { strategy_a: strategyA, strategy_b: strategyB },
    });
    return data;
  },
  async listTenants(): Promise<{ items: Array<Record<string, unknown>> }> {
    const { data } = await api.get<{ items: Array<Record<string, unknown>> }>('/governance/tenants');
    return data;
  },
  async upsertTenant(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    const { data } = await api.put<Record<string, unknown>>('/governance/tenants', payload);
    return data;
  },
  async proposeRemediation(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>('/governance/remediation/propose', payload);
    return data;
  },
  async listRemediation(limit = 100): Promise<{ items: Array<Record<string, unknown>> }> {
    const { data } = await api.get<{ items: Array<Record<string, unknown>> }>('/governance/remediation/actions', {
      params: { limit },
    });
    return data;
  },
  async approveRemediation(actionId: string, approver: string, comment = ''): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>(`/governance/remediation/actions/${actionId}/approve`, {
      approver,
      comment,
    });
    return data;
  },
  async executeRemediation(actionId: string, operator: string, postSlo: Record<string, unknown>): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>(`/governance/remediation/actions/${actionId}/execute`, {
      operator,
      post_slo: postSlo,
    });
    return data;
  },
  async rollbackRemediation(actionId: string, reason: string, execute = false): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>(`/governance/remediation/actions/${actionId}/rollback`, {
      reason,
      execute,
    });
    return data;
  },
  async listExternalSync(limit = 100): Promise<{ items: Array<Record<string, unknown>> }> {
    const { data } = await api.get<{ items: Array<Record<string, unknown>> }>('/governance/external-sync', {
      params: { limit },
    });
    return data;
  },
  async externalSyncTemplates(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/external-sync/templates');
    return data;
  },
  async externalSyncSettings(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/external-sync/settings');
    return data;
  },
  async updateExternalSyncSettings(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    const { data } = await api.put<Record<string, unknown>>('/governance/external-sync/settings', payload);
    return data;
  },
  async syncExternal(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>('/governance/external-sync', payload);
    return data;
  },
  async teamMetrics(days = 7, limit = 50): Promise<{ window_days: number; generated_at: string; items: Array<Record<string, unknown>> }> {
    const { data } = await api.get<{ window_days: number; generated_at: string; items: Array<Record<string, unknown>> }>(
      '/governance/team-metrics',
      { params: { days, limit } },
    );
    return data;
  },
  async sessionReplay(sessionId: string, limit = 120): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>(`/governance/session-replay/${sessionId}`, {
      params: { limit },
    });
    return data;
  },
  async runtimeStrategies(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/runtime-strategies');
    return data;
  },
  async runtimeStrategyActive(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/runtime-strategies/active');
    return data;
  },
  async updateRuntimeStrategyActive(profile: string): Promise<Record<string, unknown>> {
    const { data } = await api.put<Record<string, unknown>>('/governance/runtime-strategies/active', {
      profile,
    });
    return data;
  },
  async deploymentProfiles(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/deployment-profiles');
    return data;
  },
  async deploymentProfileActive(): Promise<Record<string, unknown>> {
    const { data } = await api.get<Record<string, unknown>>('/governance/deployment-profiles/active');
    return data;
  },
  async updateDeploymentProfileActive(profile: string): Promise<Record<string, unknown>> {
    const { data } = await api.put<Record<string, unknown>>('/governance/deployment-profiles/active', {
      profile,
    });
    return data;
  },
  async listHumanReview(limit = 50): Promise<{ items: Array<Record<string, unknown>>; summary: Record<string, unknown> }> {
    const { data } = await api.get<{ items: Array<Record<string, unknown>>; summary: Record<string, unknown> }>(
      '/governance/human-review',
      { params: { limit } },
    );
    return data;
  },
  async approveHumanReview(sessionId: string, approver = 'sre-oncall', comment = ''): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>(`/governance/human-review/${sessionId}/approve`, {
      approver,
      comment,
    });
    return data;
  },
  async rejectHumanReview(sessionId: string, approver = 'sre-oncall', reason = 'manual_reject'): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>(`/governance/human-review/${sessionId}/reject`, {
      approver,
      reason,
    });
    return data;
  },
  async resumeHumanReview(sessionId: string, operator = 'sre-oncall'): Promise<Record<string, unknown>> {
    const { data } = await api.post<Record<string, unknown>>(`/governance/human-review/${sessionId}/resume`, {
      operator,
    });
    return data;
  },
};

export const buildDebateWsUrl = (
  sessionId: string,
  options?: { autoStart?: boolean },
): string => {
  const token = localStorage.getItem('sre_token');
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.host;
  const autoStart = options?.autoStart === true ? 'true' : 'false';
  const tokenQuery = token
    ? `?token=${encodeURIComponent(token)}&auto_start=${autoStart}`
    : `?auto_start=${autoStart}`;
  return `${protocol}://${host}/ws/debates/${sessionId}${tokenQuery}`;
};

export default api;
