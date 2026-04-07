"""Java 真实故障场景全流程：清场 -> 感知 -> 自动分析 -> 输出根因结果。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


API_BASE = "http://127.0.0.1:8000/api/v1"
JAVA_SRC = Path("/Users/neochen/multi-agent-cli_v2/scripts/java_monitor_fault_demo/JavaMonitorFaultDemo.java")
JAVA_CP = str(JAVA_SRC.parent)
JAVA_MAIN = "JavaMonitorFaultDemo"
DEMO_URL = "http://127.0.0.1:18082/"

RUNNING_STATUSES = {
    "pending",
    "running",
    "analyzing",
    "debating",
    "critiquing",
    "rebutting",
    "judging",
    "waiting",
    "retrying",
}

TERMINAL_STATUSES = {"resolved", "closed", "failed"}


def _req(method: str, path: str, *, timeout: int = 30, **kwargs) -> requests.Response:
    url = f"{API_BASE}{path}"
    return requests.request(method=method, url=url, timeout=timeout, **kwargs)


def _json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text}


def _cancel_running_debates() -> Tuple[int, List[str]]:
    resp = _req("GET", "/debates", params={"page": 1, "page_size": 100})
    if resp.status_code != 200:
        raise RuntimeError(f"list debates failed: {resp.status_code} {resp.text}")
    items = list((_json(resp).get("items") or []))
    cancelled: List[str] = []
    for item in items:
        sid = str(item.get("id") or "")
        status = str(item.get("status") or "").lower()
        if not sid or status not in RUNNING_STATUSES:
            continue
        cancel_resp = _req("POST", f"/debates/{sid}/cancel")
        if cancel_resp.status_code == 200 and bool((_json(cancel_resp).get("cancelled"))):
            cancelled.append(sid)
    return len(cancelled), cancelled


def _start_monitoring() -> None:
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
        "tags": ["java", "real-case", "full-flow"],
    }
    resp = _req("POST", "/monitoring/targets", json=payload)
    if resp.status_code != 201:
        raise RuntimeError(f"create target failed: {resp.status_code} {resp.text}")
    return _json(resp)


def _scan_target(target_id: str) -> Dict[str, Any]:
    resp = _req("POST", f"/monitoring/targets/{target_id}/scan", timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"scan target failed: {resp.status_code} {resp.text}")
    return _json(resp)


def _find_incident(target_name: str) -> Optional[Dict[str, Any]]:
    resp = _req("GET", "/incidents", params={"page": 1, "page_size": 100, "service_name": "java-monitor-demo"})
    if resp.status_code != 200:
        return None
    for item in list((_json(resp).get("items") or [])):
        title = str(item.get("title") or "")
        if target_name in title:
            return item
    return None


def _get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    resp = _req("GET", f"/incidents/{incident_id}")
    if resp.status_code != 200:
        return None
    return _json(resp)


def _try_force_execute(session_id: str) -> Optional[Dict[str, Any]]:
    resp = _req("POST", f"/debates/{session_id}/execute", timeout=300)
    if resp.status_code == 200:
        return _json(resp)
    return None


def _get_debate(session_id: str) -> Optional[Dict[str, Any]]:
    resp = _req("GET", f"/debates/{session_id}", timeout=20)
    if resp.status_code != 200:
        return None
    return _json(resp)


def _get_debate_result(session_id: str) -> Optional[Dict[str, Any]]:
    resp = _req("GET", f"/debates/{session_id}/result", timeout=20)
    if resp.status_code != 200:
        return None
    return _json(resp)


def _wait_final_result(incident_id: str, session_id: str, timeout_sec: int = 360) -> Dict[str, Any]:
    started = time.time()
    last_detail: Dict[str, Any] = {}
    while (time.time() - started) < timeout_sec:
        detail = _get_incident(incident_id)
        if detail:
            last_detail = detail
            status = str(detail.get("status") or "").lower()
            root_cause = str(detail.get("root_cause") or "").strip()
            if status in TERMINAL_STATUSES and root_cause:
                return {
                    "ok": True,
                    "status": status,
                    "root_cause": root_cause,
                    "fix_suggestion": detail.get("fix_suggestion"),
                    "impact_analysis": detail.get("impact_analysis"),
                    "forced_execute": False,
                }
            if status in {"closed", "failed"} and not root_cause:
                break
        time.sleep(2.0)

    debate = _get_debate(session_id)
    if debate:
        debate_status = str(debate.get("status") or "").lower()
        if debate_status == "completed":
            result = _get_debate_result(session_id)
            if result and str(result.get("root_cause") or "").strip():
                return {
                    "ok": True,
                    "status": "resolved",
                    "root_cause": result.get("root_cause"),
                    "fix_suggestion": (result.get("fix_recommendation") or {}).get("summary"),
                    "impact_analysis": result.get("impact_analysis"),
                    "forced_execute": False,
                }
        if debate_status in {"failed", "cancelled"}:
            return {
                "ok": False,
                "status": debate_status,
                "root_cause": str(last_detail.get("root_cause") or ""),
                "fix_suggestion": last_detail.get("fix_suggestion"),
                "impact_analysis": last_detail.get("impact_analysis"),
                "forced_execute": False,
            }
    return {
        "ok": False,
        "status": str(last_detail.get("status") or "unknown"),
        "root_cause": str(last_detail.get("root_cause") or ""),
        "fix_suggestion": last_detail.get("fix_suggestion"),
        "impact_analysis": last_detail.get("impact_analysis"),
        "forced_execute": False,
    }


def _compile_java() -> None:
    proc = subprocess.run(
        ["javac", str(JAVA_SRC)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"javac failed: {proc.stderr or proc.stdout}")


def _start_java_service() -> subprocess.Popen[str]:
    proc = subprocess.Popen(
        ["java", "-cp", JAVA_CP, JAVA_MAIN],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    ready = False
    for _ in range(20):
        line = ""
        if proc.stdout:
            line = proc.stdout.readline().strip()
        if "listening on http://127.0.0.1:18082" in line:
            ready = True
            break
        time.sleep(0.2)
    if not ready:
        proc.terminate()
        raise RuntimeError("java demo service not ready")
    return proc


def main() -> int:
    tag = datetime.now().strftime("%H%M%S")
    target_name = f"java-full-flow-{tag}"

    print("[0/6] 清理运行中的故障分析任务")
    count, sessions = _cancel_running_debates()
    print(f"      cancelled={count} sessions={sessions[:5]}")

    print("[1/6] 编译并启动 Java 故障演练服务")
    _compile_java()
    java_proc = _start_java_service()

    try:
        print("[2/6] 启动页面感知服务并创建目标")
        _start_monitoring()
        target = _create_target(target_name)
        target_id = str(target.get("id") or "")
        print(f"      target_id={target_id} url={DEMO_URL}")

        print("[3/6] 执行页面感知扫描")
        scan = _scan_target(target_id)
        finding = scan.get("finding") or {}
        print(f"      has_error={finding.get('has_error')} summary={finding.get('summary')}")

        print("[4/6] 确认自动触发了故障分析会话")
        incident = None
        for _ in range(20):
            incident = _find_incident(target_name)
            if incident:
                break
            time.sleep(1.0)
        if not incident:
            raise RuntimeError("未找到自动创建的 incident")
        incident_id = str(incident.get("id") or "")
        session_id = str(incident.get("debate_session_id") or "")
        print(f"      incident_id={incident_id} session_id={session_id} status={incident.get('status')}")
        if not session_id:
            raise RuntimeError("incident 未绑定 debate_session_id")

        print("[5/6] 等待分析完成并获取根因结果")
        result = _wait_final_result(incident_id=incident_id, session_id=session_id, timeout_sec=240)
        print("      result=", json.dumps(result, ensure_ascii=False))

        print("\n=== FULL FLOW RESULT ===")
        if result.get("ok") and str(result.get("root_cause") or "").strip():
            print("PASS")
            print(json.dumps(
                {
                    "incident_id": incident_id,
                    "session_id": session_id,
                    "status": result.get("status"),
                    "forced_execute": result.get("forced_execute"),
                    "root_cause": result.get("root_cause"),
                    "fix_suggestion": result.get("fix_suggestion"),
                },
                ensure_ascii=False,
                indent=2,
            ))
            return 0
        print("FAIL")
        return 1
    finally:
        java_proc.terminate()
        try:
            java_proc.wait(timeout=3)
        except Exception:
            java_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
