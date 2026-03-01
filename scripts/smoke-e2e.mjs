const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const WS_TIMEOUT_MS = Number(process.env.WS_TIMEOUT_MS || 900000);
const SMOKE_SCENARIO = String(process.env.SMOKE_SCENARIO || '').trim();

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

async function runRealtimeDebate(sessionId, token = '', timeoutMs = WS_TIMEOUT_MS) {
  const params = new URLSearchParams();
  params.set('auto_start', 'true');
  if (token) params.set('token', token);

  const wsUrl = `ws://localhost:8000/ws/debates/${sessionId}?${params.toString()}`;

  return new Promise((resolve, reject) => {
    const events = [];
    const ws = new WebSocket(wsUrl);
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error('websocket timeout waiting result'));
    }, timeoutMs);

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'event') {
          events.push(payload.data?.type || 'event');
        }
        if (payload.type === 'error') {
          clearTimeout(timer);
          ws.close();
          reject(new Error(payload.message || 'websocket error'));
          return;
        }
        if (payload.type === 'result') {
          clearTimeout(timer);
          ws.close();
          resolve({ result: payload.data, events });
        }
      } catch (_) {
        // ignore non-json
      }
    };

    ws.onerror = () => {
      clearTimeout(timer);
      ws.close();
      reject(new Error('websocket connection error'));
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
    `${BACKEND_URL}/api/v1/debates/?incident_id=${incident.id}`,
    { method: 'POST' },
    token,
  );

  const realtime = await runRealtimeDebate(session.id, token);

  const detail = await jsonRequest(
    `${BACKEND_URL}/api/v1/debates/${session.id}`,
    { method: 'GET' },
    token,
  );
  const debateResult = await jsonRequest(
    `${BACKEND_URL}/api/v1/debates/${session.id}/result`,
    { method: 'GET' },
    token,
  );
  const report = await jsonRequest(
    `${BACKEND_URL}/api/v1/reports/${incident.id}`,
    { method: 'GET' },
    token,
  );

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
    passed: detail.status === 'completed' && effective && Boolean(report.report_id),
  };
}

async function main() {
  await waitForHttp(`${FRONTEND_URL}/`);
  await waitForHttp(`${BACKEND_URL}/health`);

  const home = await fetch(`${FRONTEND_URL}/`);
  const html = await home.text();
  if (!html.includes('<div id="root">')) {
    throw new Error('frontend root html invalid');
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
  console.log(JSON.stringify(summary, null, 2));

  if (failed > 0) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('[smoke-e2e] failed:', err.message);
  process.exit(1);
});
