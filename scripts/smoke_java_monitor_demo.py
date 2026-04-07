"""Java 页面感知演练：创建目标、执行感知、验证自动故障分析触发。"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


API_BASE = "http://127.0.0.1:8000/api/v1"
DEMO_URL = "http://127.0.0.1:18082/"


def _now_tag() -> str:
    return datetime.now().strftime("%H%M%S")


def _req(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{API_BASE}{path}"
    resp = requests.request(method=method, url=url, timeout=20, **kwargs)
    return resp


def _json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text}


def _ensure_started() -> None:
    _req("POST", "/monitoring/control/start")


def _create_target(name: str) -> Dict[str, Any]:
    payload = {
        "name": name,
        "url": DEMO_URL,
        "enabled": True,
        "check_interval_sec": 30,
        "timeout_sec": 20,
        "cooldown_sec": 30,
        "service_name": "java-monitor-demo",
        "environment": "staging",
        "severity": "high",
        "tags": ["java", "demo", "monitoring-e2e"],
    }
    resp = _req("POST", "/monitoring/targets", json=payload)
    if resp.status_code != 201:
        raise RuntimeError(f"create target failed: status={resp.status_code} body={resp.text}")
    return _json(resp)


def _scan_once(target_id: str) -> Dict[str, Any]:
    resp = _req("POST", f"/monitoring/targets/{target_id}/scan")
    if resp.status_code != 200:
        raise RuntimeError(f"scan failed: status={resp.status_code} body={resp.text}")
    return _json(resp)


def _list_events(target_id: str) -> List[Dict[str, Any]]:
    resp = _req("GET", f"/monitoring/targets/{target_id}/events", params={"limit": 20})
    if resp.status_code != 200:
        raise RuntimeError(f"list events failed: status={resp.status_code} body={resp.text}")
    return list((_json(resp).get("items") or []))


def _find_incident_by_name(target_name: str) -> Optional[Dict[str, Any]]:
    resp = _req("GET", "/incidents", params={"page": 1, "page_size": 50, "service_name": "java-monitor-demo"})
    if resp.status_code != 200:
        return None
    items = list((_json(resp).get("items") or []))
    for item in items:
        title = str(item.get("title") or "")
        if target_name in title:
            return item
    return None


def main() -> int:
    target_name = f"java-fault-demo-{_now_tag()}"
    print(f"[1/5] 启动感知服务: {API_BASE}")
    _ensure_started()

    print(f"[2/5] 创建感知目标: {target_name} -> {DEMO_URL}")
    target = _create_target(target_name)
    target_id = str(target["id"])
    print(f"      target_id={target_id}")

    print("[3/5] 手动执行一次感知扫描")
    scan_data = _scan_once(target_id)
    finding = scan_data.get("finding") or {}
    print(f"      has_error={finding.get('has_error')} summary={finding.get('summary')}")

    print("[4/5] 拉取感知事件并检查接口/前端报错、查询接口识别结果")
    events = _list_events(target_id)
    if not events:
        raise RuntimeError("未查到感知事件")
    latest = events[0]
    raw = latest.get("raw") or {}
    observed_apis = list(raw.get("observed_query_apis") or [])
    triggered_actions = list(raw.get("triggered_actions") or [])
    replay_api_errors = list(raw.get("replay_api_errors") or [])
    frontend_errors = list(latest.get("frontend_errors") or [])
    api_errors = list(latest.get("api_errors") or [])

    checks = {
        "has_error": bool(latest.get("has_error")),
        "frontend_errors": len(frontend_errors) > 0,
        "api_errors": len(api_errors) > 0,
        "observed_query_apis": len(observed_apis) > 0,
        "triggered_actions": len(triggered_actions) > 0,
    }
    print("      checks=", json.dumps(checks, ensure_ascii=False))
    print(f"      observed_query_apis={len(observed_apis)} triggered_actions={len(triggered_actions)} replay_api_errors={len(replay_api_errors)}")

    print("[5/5] 检查是否自动创建故障分析任务（Incident）")
    incident = None
    for _ in range(10):
        incident = _find_incident_by_name(target_name)
        if incident:
            break
        time.sleep(1.0)
    if incident:
        print(
            "      incident_found:",
            json.dumps(
                {
                    "id": incident.get("id"),
                    "title": incident.get("title"),
                    "status": incident.get("status"),
                    "debate_session_id": incident.get("debate_session_id"),
                },
                ensure_ascii=False,
            ),
        )
    else:
        print("      incident_found: false")

    all_pass = all(checks.values()) and (incident is not None)
    print("\n=== RESULT ===")
    print("PASS" if all_pass else "FAIL")
    if not all_pass:
        print("details:")
        print(json.dumps({
            "checks": checks,
            "incident_found": bool(incident),
            "latest_event_summary": latest.get("summary"),
        }, ensure_ascii=False, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
