const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const WS_TIMEOUT_MS = Number(process.env.WS_TIMEOUT_MS || 720000);
const SMOKE_SCENARIO = String(process.env.SMOKE_SCENARIO || '').trim();
const REQUIRE_FRONTEND_HTTP = String(process.env.REQUIRE_FRONTEND_HTTP || '').trim() === 'true';

const scenarios = [
  {
    id: 'order-502-db-lock',
    title: '订单接口 502 + CPU 飙高',
    description: '生产下单失败，疑似数据库与连接池问题',
    service_name: 'order-service',
    log_content:
      '2026-02-20T14:01:38+08:00 ERROR gateway upstream timeout 502 /api/v1/orders; HikariPool request timed out 30000ms; DB active connections 100/100; lock wait timeout exceeded',
  },
  {
    id: 'order-404-route-miss',
    title: '订单接口 404',
    description: '网关返回404，怀疑路由缺失',
    service_name: 'gateway',
    log_content:
      '2026-02-20T10:11:01+08:00 WARN gateway route not found path=/api/v1/orders method=POST return=404',
  },
  {
    id: 'payment-timeout-upstream',
    title: '支付接口超时',
    description: '支付接口调用上游风控服务超时',
    service_name: 'payment-service',
    log_content:
      '2026-02-20T16:42:10+08:00 ERROR /api/v1/payments timeout after 30000ms cause=RiskService timeout retries=3',
  },
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForHttp(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok) return true;
    } catch (_) {
      // ignore
    }
    await sleep(1000);
  }
  throw new Error(`timeout waiting for ${url}`);
}

async function jsonRequest(url, init = {}, token = '') {
  const headers = {
    'Content-Type': 'application/json',
    ...(init.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(url, { ...init, headers });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_) {
    data = { raw: text };
  }
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} ${JSON.stringify(data)}`);
  }
  return data;
}

async function waitForDebateArtifacts(sessionId, incidentId, token = '', timeoutMs = WS_TIMEOUT_MS) {
  const start = Date.now();
  let lastDetail = null;
  let lastResult = null;
  let lastReport = null;

  while (Date.now() - start < timeoutMs) {
    try {
      lastDetail = await jsonRequest(
        `${BACKEND_URL}/api/v1/debates/${sessionId}`,
        { method: 'GET' },
        token,
      );
    } catch (_) {
      lastDetail = null;
    }

    try {
      lastResult = await jsonRequest(
        `${BACKEND_URL}/api/v1/debates/${sessionId}/result`,
        { method: 'GET' },
        token,
      );
    } catch (_) {
      lastResult = null;
    }

    try {
      lastReport = await jsonRequest(
        `${BACKEND_URL}/api/v1/reports/${incidentId}`,
        { method: 'GET' },
        token,
      );
    } catch (_) {
      lastReport = null;
    }

    const status = String(lastDetail?.status || '');
    const hasResult = Boolean(lastResult && Object.keys(lastResult).length > 0);
    const hasReport = Boolean(lastReport?.report_id);
    if (status === 'completed' && hasResult && hasReport) {
      return { detail: lastDetail, debateResult: lastResult, report: lastReport };
    }
    if (status === 'failed' || status === 'cancelled') {
      throw new Error(`session_${status}: ${JSON.stringify(lastDetail || {})}`);
    }
    await sleep(2000);
  }

  throw new Error(
    `artifact_poll_timeout: session=${sessionId} detail=${JSON.stringify(lastDetail || {})}`,
  );
}

async function runRealtimeDebate(sessionId, token = '', timeoutMs = WS_TIMEOUT_MS) {
  const params = new URLSearchParams();
  params.set('auto_start', 'true');
  if (token) params.set('token', token);

  const backendWsBase = BACKEND_URL.replace(/^http/i, 'ws');
  const wsUrl = `${backendWsBase}/ws/debates/${sessionId}?${params.toString()}`;

  return new Promise((resolve, reject) => {
    const events = [];
    const ws = new WebSocket(wsUrl);
    let settled = false;
    const done = (handler, payload) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        ws.close();
      } catch (_) {
        // ignore
      }
      handler(payload);
    };
    const timer = setTimeout(() => {
      done(reject, new Error('websocket timeout waiting result'));
    }, timeoutMs);

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'event') {
          const eventType = payload.data?.type || 'event';
          events.push(eventType);
          if (eventType === 'session_failed') {
            const error =
              payload.data?.error ||
              payload.data?.error_message ||
              payload.data?.message ||
              'session_failed';
            done(reject, new Error(`session_failed: ${error}`));
            return;
          }
        }
        if (payload.type === 'error') {
          done(reject, new Error(payload.message || 'websocket error'));
          return;
        }
        if (payload.type === 'result') {
          done(resolve, { result: payload.data, events });
        }
      } catch (_) {
        // ignore non-json
      }
    };

    ws.onerror = () => {
      done(reject, new Error('websocket connection error'));
    };

    ws.onclose = () => {
      if (!settled) {
        done(reject, new Error('websocket closed before result'));
      }
    };
  });
}

function isEffectiveRootCause(rootCause) {
  const text = String(rootCause || '').trim().toLowerCase();
  if (!text) return false;
  const blocked = ['需要进一步分析', 'unknown', '待评估', '待确认'];
  return !blocked.some((token) => text.includes(token));
}

async function runScenario(scenario, token) {
  const incident = await jsonRequest(
    `${BACKEND_URL}/api/v1/incidents/`,
    {
      method: 'POST',
      body: JSON.stringify({
        title: `${scenario.id}-${Date.now()}`,
        description: scenario.description,
        severity: 'high',
        service_name: scenario.service_name,
        environment: 'production',
        log_content: scenario.log_content,
      }),
    },
    token,
  );

  const session = await jsonRequest(
    `${BACKEND_URL}/api/v1/debates/?incident_id=${incident.id}&mode=quick`,
    { method: 'POST' },
    token,
  );

  let realtime = { result: null, events: [], fallback: false };
  try {
    realtime = await runRealtimeDebate(session.id, token);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (!message.includes('websocket timeout waiting result') && !message.includes('websocket closed before result')) {
      throw err;
    }
    realtime = { result: null, events: [], fallback: true, ws_error: message };
  }

  const artifacts = await waitForDebateArtifacts(session.id, incident.id, token);
  const detail = artifacts.detail;
  const debateResult = artifacts.debateResult;
  const report = artifacts.report;

  const effective = isEffectiveRootCause(debateResult.root_cause);
  return {
    scenario: scenario.id,
    incident_id: incident.id,
    session_id: session.id,
    status: detail.status,
    confidence: debateResult.confidence,
    root_cause: debateResult.root_cause,
    effective_root_cause: effective,
    report_generated: Boolean(report.report_id),
    ws_events: realtime.events,
    ws_fallback: Boolean(realtime.fallback),
    ws_error: realtime.ws_error || '',
    passed: detail.status === 'completed' && effective && Boolean(report.report_id),
  };
}

async function main() {
  await waitForHttp(`${BACKEND_URL}/health`);
  let frontendCheck = {
    checked: false,
    ok: false,
    warning: '',
  };
  try {
    await waitForHttp(`${FRONTEND_URL}/`, 15000);
    const home = await fetch(`${FRONTEND_URL}/`);
    const html = await home.text();
    if (!html.includes('<div id="root">')) {
      throw new Error('frontend root html invalid');
    }
    frontendCheck = { checked: true, ok: true, warning: '' };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    frontendCheck = {
      checked: true,
      ok: false,
      warning: `frontend_http_check_skipped: ${message}`,
    };
    if (REQUIRE_FRONTEND_HTTP) {
      throw err;
    }
  }

  let token = '';
  try {
    const login = await jsonRequest(`${BACKEND_URL}/api/v1/auth/login`, {
      method: 'POST',
      body: JSON.stringify({ username: 'analyst', password: 'analyst123' }),
    });
    token = login.access_token || '';
  } catch (_) {
    // auth disabled or unavailable, continue
  }

  const selectedScenarios = SMOKE_SCENARIO
    ? scenarios.filter((item) => item.id === SMOKE_SCENARIO)
    : scenarios;

  if (selectedScenarios.length === 0) {
    throw new Error(`unknown scenario: ${SMOKE_SCENARIO}`);
  }

  const details = [];
  for (const scenario of selectedScenarios) {
    try {
      const result = await runScenario(scenario, token);
      details.push(result);
    } catch (err) {
      details.push({
        scenario: scenario.id,
        passed: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  const total = details.length;
  const passed = details.filter((item) => item.passed).length;
  const failed = total - passed;
  const pass_rate = total > 0 ? Number(((passed / total) * 100).toFixed(1)) : 0;

  const summary = { total, passed, failed, pass_rate, details };
  if (frontendCheck.checked) {
    summary.frontend_check = frontendCheck;
  }
  console.log(JSON.stringify(summary, null, 2));

  if (failed > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('[smoke-e2e] failed:', err.message);
  process.exit(1);
});
