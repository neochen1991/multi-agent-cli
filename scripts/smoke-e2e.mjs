const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

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

async function runRealtimeDebate(sessionId, token = '', timeoutMs = 180000) {
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

  const incident = await jsonRequest(
    `${BACKEND_URL}/api/v1/incidents/`,
    {
      method: 'POST',
      body: JSON.stringify({
        title: `e2e-${Date.now()}`,
        description: '前后端联调：下单失败',
        severity: 'high',
        service_name: 'order-service',
        environment: 'production',
        log_content:
          '2026-02-18 ERROR POST /api/v1/orders failed with java.lang.NullPointerException at OrderAppService#createOrder',
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

  const locate = await jsonRequest(
    `${BACKEND_URL}/api/v1/assets/locate`,
    {
      method: 'POST',
      body: JSON.stringify({
        log_content:
          'ERROR POST /api/v1/orders failed with NullPointerException at OrderAppService#createOrder',
        symptom: '下单失败',
      }),
    },
    token,
  );

  console.log(
    JSON.stringify(
      {
        frontend_ok: true,
        backend_ok: true,
        incident_id: incident.id,
        session_id: session.id,
        ws_result_confidence: realtime.result?.confidence,
        ws_events: realtime.events,
        session_status: detail.status,
        result_root_cause: debateResult.root_cause,
        report_generated: Boolean(report.report_id),
        locate_matched: locate.matched,
        locate_domain: locate.domain,
        locate_aggregate: locate.aggregate,
      },
      null,
      2,
    ),
  );
}

main().catch((err) => {
  console.error('[smoke-e2e] failed:', err.message);
  process.exit(1);
});
