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

export interface AgentToolingConfig {
  code_repo: CodeRepoToolConfig;
  log_file: LogFileToolConfig;
  domain_excel: DomainExcelToolConfig;
  updated_at: string;
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
};

export const debateApi = {
  async createSession(
    incidentId: string,
    options?: { maxRounds?: number },
  ): Promise<{ id: string; incident_id: string; status: string }> {
    const params: Record<string, string | number> = { incident_id: incidentId };
    if (typeof options?.maxRounds === 'number' && Number.isFinite(options.maxRounds)) {
      params.max_rounds = Math.max(1, Math.min(8, Math.trunc(options.maxRounds)));
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
  async cancel(sessionId: string): Promise<{ session_id: string; cancelled: boolean }> {
    const { data } = await api.post(`/debates/${sessionId}/cancel`);
    return data;
  },
  async getTask(taskId: string): Promise<{ task_id: string; status: string; result?: Record<string, unknown> }> {
    const { data } = await api.get(`/debates/tasks/${taskId}`);
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
};

export const assetApi = {
  async fusion(incidentId: string): Promise<AssetFusion> {
    const { data } = await api.get<AssetFusion>(`/assets/fusion/${incidentId}`);
    return data;
  },
  async locate(logContent: string, symptom?: string): Promise<InterfaceLocateResult> {
    const { data } = await api.post<InterfaceLocateResult>('/assets/locate', {
      log_content: logContent,
      symptom,
    });
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
};

export const buildDebateWsUrl = (sessionId: string): string => {
  const token = localStorage.getItem('sre_token');
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.host;
  const tokenQuery = token ? `?token=${encodeURIComponent(token)}&auto_start=true` : '?auto_start=true';
  return `${protocol}://${host}/ws/debates/${sessionId}${tokenQuery}`;
};

export default api;
