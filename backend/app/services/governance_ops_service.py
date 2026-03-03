"""Governance operational services: A/B eval, tenant governance, external sync stubs."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings


class GovernanceOpsService:
    def __init__(self) -> None:
        root = Path(settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._tenant_file = root / "tenant_policies.json"
        self._sync_file = root / "external_sync_events.json"
        self._lock = asyncio.Lock()

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload
        except Exception:
            return default

    def _write_json(self, path: Path, payload: Any) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _metrics_dir(self) -> Path:
        return Path(__file__).resolve().parents[3] / "docs" / "metrics"

    def _load_baselines(self, limit: int = 20) -> List[Dict[str, Any]]:
        files = sorted(self._metrics_dir().glob("baseline-*.json"), reverse=True)[: max(1, int(limit or 20))]
        rows: List[Dict[str, Any]] = []
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            rows.append({"file": str(path), "generated_at": payload.get("generated_at"), "summary": payload.get("summary") or {}})
        return rows

    async def ab_evaluate(self, strategy_a: str, strategy_b: str) -> Dict[str, Any]:
        baselines = self._load_baselines(limit=2)
        if len(baselines) < 2:
            return {
                "strategy_a": strategy_a,
                "strategy_b": strategy_b,
                "canary_ready": False,
                "summary": "基线文件不足 2 份，无法进行 A/B 评测。",
                "comparison": {},
            }
        base = baselines[1]["summary"]
        target = baselines[0]["summary"]
        diff = {
            "top1_rate_delta": round(float(target.get("top1_rate") or 0.0) - float(base.get("top1_rate") or 0.0), 3),
            "timeout_rate_delta": round(float(target.get("timeout_rate") or 0.0) - float(base.get("timeout_rate") or 0.0), 3),
            "failure_rate_delta": round(float(target.get("failure_rate") or 0.0) - float(base.get("failure_rate") or 0.0), 3),
            "empty_conclusion_rate_delta": round(
                float(target.get("empty_conclusion_rate") or 0.0) - float(base.get("empty_conclusion_rate") or 0.0), 3
            ),
        }
        canary_ready = diff["top1_rate_delta"] >= 0 and diff["timeout_rate_delta"] <= 0.03 and diff["failure_rate_delta"] <= 0.03
        return {
            "strategy_a": strategy_a,
            "strategy_b": strategy_b,
            "base_file": baselines[1]["file"],
            "target_file": baselines[0]["file"],
            "comparison": diff,
            "canary_ready": canary_ready,
            "summary": "可灰度上线" if canary_ready else "建议继续离线调优",
        }

    async def list_tenants(self) -> List[Dict[str, Any]]:
        async with self._lock:
            rows = self._read_json(self._tenant_file, [])
            if not rows:
                rows = [
                    {
                        "tenant_id": "default",
                        "name": "Default Team",
                        "rbac": {"admin": ["admin"], "analyst": ["sre", "developer"], "viewer": ["viewer"]},
                        "quota": {"max_concurrent_sessions": 5, "daily_sessions": 200},
                        "budget": {"monthly_token_budget": 2000000},
                        "isolation": {"data_scope": "tenant_local_store"},
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ]
                self._write_json(self._tenant_file, rows)
            return rows

    async def upsert_tenant(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = str(payload.get("tenant_id") or "").strip()
        if not tenant_id:
            raise ValueError("tenant_id is required")
        async with self._lock:
            rows = self._read_json(self._tenant_file, [])
            target = None
            for row in rows:
                if str(row.get("tenant_id") or "") == tenant_id:
                    target = row
                    break
            if not target:
                target = {"tenant_id": tenant_id}
                rows.append(target)
            target.update(dict(payload or {}))
            target["updated_at"] = datetime.utcnow().isoformat()
            self._write_json(self._tenant_file, rows)
            return target

    async def sync_external(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        record = {
            "id": f"sync_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            "at": datetime.utcnow().isoformat(),
            "provider": str(payload.get("provider") or "unknown"),
            "direction": str(payload.get("direction") or "outbound"),
            "action": str(payload.get("action") or "notify"),
            "status": "success",
            "payload": dict(payload.get("payload") or {}),
        }
        async with self._lock:
            rows = self._read_json(self._sync_file, [])
            rows.append(record)
            self._write_json(self._sync_file, rows[-1000:])
        return record

    async def list_external_sync(self, limit: int = 100) -> List[Dict[str, Any]]:
        async with self._lock:
            rows = self._read_json(self._sync_file, [])
        return list(reversed(rows))[: max(1, int(limit or 100))]


governance_ops_service = GovernanceOpsService()

