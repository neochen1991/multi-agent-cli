"""Remediation workflow service (local file/in-memory, no external DB)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings


class RemediationService:
    _FLOW = ["PROPOSED", "SIMULATED", "APPROVED", "EXECUTED", "VERIFIED"]

    def __init__(self) -> None:
        root = Path(settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._file = root / "remediation_actions.json"
        self._lock = asyncio.Lock()

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    def _load(self) -> List[Dict[str, Any]]:
        if not self._file.exists():
            return []
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except Exception:
            return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)

    def _find(self, items: List[Dict[str, Any]], action_id: str) -> Optional[Dict[str, Any]]:
        for row in items:
            if str(row.get("id") or "") == action_id:
                return row
        return None

    def _append_audit(self, row: Dict[str, Any], event: str, payload: Dict[str, Any]) -> None:
        logs = row.get("audit_logs")
        if not isinstance(logs, list):
            logs = []
        logs.append({"at": self._now(), "event": event, **dict(payload or {})})
        row["audit_logs"] = logs

    @staticmethod
    def _no_regression(pre_slo: Dict[str, Any], post_slo: Dict[str, Any]) -> Dict[str, Any]:
        pre_error = float(pre_slo.get("error_rate") or 0.0)
        post_error = float(post_slo.get("error_rate") or 0.0)
        pre_latency = float(pre_slo.get("p95_latency_ms") or 0.0)
        post_latency = float(post_slo.get("p95_latency_ms") or 0.0)
        error_delta = post_error - pre_error
        latency_delta = post_latency - pre_latency
        passed = error_delta <= 0.01 and latency_delta <= 80
        return {
            "passed": passed,
            "pre": {"error_rate": pre_error, "p95_latency_ms": pre_latency},
            "post": {"error_rate": post_error, "p95_latency_ms": post_latency},
            "delta": {"error_rate": round(error_delta, 4), "p95_latency_ms": round(latency_delta, 2)},
        }

    async def list_actions(self, limit: int = 200) -> List[Dict[str, Any]]:
        async with self._lock:
            items = self._load()
        return list(reversed(items))[: max(1, int(limit or 200))]

    async def get_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            items = self._load()
            row = self._find(items, action_id)
            return dict(row) if isinstance(row, dict) else None

    async def propose(
        self,
        *,
        incident_id: str,
        session_id: str,
        summary: str,
        steps: List[str],
        risk_level: str,
        pre_slo: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = {
            "id": f"fix_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            "incident_id": incident_id,
            "session_id": session_id,
            "summary": summary,
            "steps": [str(step) for step in (steps or []) if str(step).strip()],
            "risk_level": str(risk_level or "medium").lower(),
            "state": "PROPOSED",
            "pre_slo": dict(pre_slo or {}),
            "post_slo": {},
            "regression_gate": {},
            "approvals": [],
            "rollback_plan": {},
            "change_link": {},
            "audit_logs": [],
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._append_audit(record, "proposed", {"summary": summary})
        async with self._lock:
            items = self._load()
            items.append(record)
            self._save(items)
        return record

    async def simulate(self, action_id: str, simulated_slo: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            items = self._load()
            row = self._find(items, action_id)
            if not row:
                raise ValueError(f"action not found: {action_id}")
            row["state"] = "SIMULATED"
            row["simulated_slo"] = dict(simulated_slo or {})
            row["updated_at"] = self._now()
            self._append_audit(row, "simulated", {"simulated_slo": row["simulated_slo"]})
            self._save(items)
            return dict(row)

    async def approve(self, action_id: str, approver: str, comment: str = "") -> Dict[str, Any]:
        async with self._lock:
            items = self._load()
            row = self._find(items, action_id)
            if not row:
                raise ValueError(f"action not found: {action_id}")
            approvals = row.get("approvals")
            if not isinstance(approvals, list):
                approvals = []
            approvals.append({"approver": approver, "comment": comment, "at": self._now()})
            row["approvals"] = approvals
            row["state"] = "APPROVED"
            row["updated_at"] = self._now()
            self._append_audit(row, "approved", {"approver": approver, "comment": comment})
            self._save(items)
            return dict(row)

    async def execute(
        self,
        action_id: str,
        *,
        operator: str,
        post_slo: Dict[str, Any],
    ) -> Dict[str, Any]:
        async with self._lock:
            items = self._load()
            row = self._find(items, action_id)
            if not row:
                raise ValueError(f"action not found: {action_id}")
            risk_level = str(row.get("risk_level") or "medium").lower()
            approvals = row.get("approvals") if isinstance(row.get("approvals"), list) else []
            if risk_level in {"high", "critical"} and not approvals:
                raise ValueError("high-risk action requires manual approval before execution")
            if str(row.get("state") or "") != "APPROVED":
                raise ValueError("action must be APPROVED before execution")
            gate = self._no_regression(dict(row.get("pre_slo") or {}), dict(post_slo or {}))
            row["regression_gate"] = gate
            row["post_slo"] = dict(post_slo or {})
            if not bool(gate.get("passed")):
                row["state"] = "APPROVED"
                row["updated_at"] = self._now()
                self._append_audit(row, "execution_blocked_by_no_regression_gate", {"operator": operator, "gate": gate})
                self._save(items)
                raise ValueError("no-regression gate failed; execution blocked")
            row["state"] = "EXECUTED"
            row["updated_at"] = self._now()
            self._append_audit(row, "executed", {"operator": operator, "post_slo": row["post_slo"]})
            self._save(items)
            return dict(row)

    async def verify(self, action_id: str, verifier: str, verification: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            items = self._load()
            row = self._find(items, action_id)
            if not row:
                raise ValueError(f"action not found: {action_id}")
            if str(row.get("state") or "") != "EXECUTED":
                raise ValueError("action must be EXECUTED before verification")
            row["state"] = "VERIFIED"
            row["verification"] = dict(verification or {})
            row["updated_at"] = self._now()
            self._append_audit(row, "verified", {"verifier": verifier, "verification": row["verification"]})
            self._save(items)
            return dict(row)

    async def rollback(self, action_id: str, reason: str, execute: bool = False) -> Dict[str, Any]:
        async with self._lock:
            items = self._load()
            row = self._find(items, action_id)
            if not row:
                raise ValueError(f"action not found: {action_id}")
            plan = {
                "summary": f"回滚 {row.get('id')} 到执行前版本",
                "steps": [
                    "恢复上一个稳定版本",
                    "恢复配置快照",
                    "回放关键业务探针并验证 SLO",
                ],
                "reason": reason,
                "generated_at": self._now(),
            }
            row["rollback_plan"] = plan
            if execute:
                row["state"] = "ROLLED_BACK"
                self._append_audit(row, "rollback_executed", {"reason": reason})
            else:
                self._append_audit(row, "rollback_plan_generated", {"reason": reason})
            row["updated_at"] = self._now()
            self._save(items)
            return {"action": dict(row), "rollback_plan": plan}

    async def link_change_window(
        self,
        action_id: str,
        *,
        change_id: str,
        window: str,
        release_type: str,
    ) -> Dict[str, Any]:
        async with self._lock:
            items = self._load()
            row = self._find(items, action_id)
            if not row:
                raise ValueError(f"action not found: {action_id}")
            risk_signals = []
            if str(release_type).lower() in {"schema", "infra", "major"}:
                risk_signals.append("high-risk-release-type")
            if "freeze" in str(window).lower() or "night" in str(window).lower():
                risk_signals.append("non-business-change-window")
            row["change_link"] = {
                "change_id": change_id,
                "window": window,
                "release_type": release_type,
                "risk_signals": risk_signals,
                "high_risk": bool(risk_signals),
            }
            row["updated_at"] = self._now()
            self._append_audit(row, "change_linked", {"change_link": row["change_link"]})
            self._save(items)
            return dict(row)


remediation_service = RemediationService()

