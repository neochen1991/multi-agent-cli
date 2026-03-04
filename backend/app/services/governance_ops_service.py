"""Governance operational services: A/B eval, tenant governance, replay and metrics."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings
from app.runtime.trace_lineage import replay_session_lineage


class GovernanceOpsService:
    def __init__(self) -> None:
        root = Path(settings.LOCAL_STORE_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self._tenant_file = root / "tenant_policies.json"
        self._sync_file = root / "external_sync_events.json"
        self._sync_settings_file = root / "external_sync_settings.json"
        self._debates_file = root / "debates.json"
        self._runtime_events_dir = root / "runtime" / "events"
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

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _load_debate_snapshot(self) -> Dict[str, Any]:
        payload = self._read_json(self._debates_file, {})
        if not isinstance(payload, dict):
            return {"sessions": [], "results": []}
        sessions = payload.get("sessions")
        results = payload.get("results")
        return {
            "sessions": sessions if isinstance(sessions, list) else [],
            "results": results if isinstance(results, list) else [],
        }

    def _runtime_events_path(self, session_id: str) -> Path:
        return self._runtime_events_dir / f"{session_id}.jsonl"

    def _load_runtime_events(self, session_id: str) -> List[Dict[str, Any]]:
        path = self._runtime_events_path(session_id)
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                text = str(line or "").strip()
                if not text:
                    continue
                payload = json.loads(text)
                if isinstance(payload, dict):
                    rows.append(payload)
        except Exception:
            return []
        return rows

    def _resolve_team_name(self, session: Dict[str, Any], result: Dict[str, Any]) -> str:
        for raw in (
            result.get("responsible_team"),
            ((session.get("context") or {}).get("interface_mapping") or {}).get("responsible_team"),
            ((session.get("context") or {}).get("interface_mapping") or {}).get("team"),
            ((session.get("context") or {}).get("asset_mapping") or {}).get("team"),
            session.get("tenant_id"),
        ):
            team = str(raw or "").strip()
            if team:
                return team
        return "unknown"

    def _is_recent(self, value: Any, window_start: datetime | None) -> bool:
        if window_start is None:
            return True
        ts = str(value or "").strip()
        if not ts:
            return False
        try:
            created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created >= window_start

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

    async def external_sync_templates(self) -> Dict[str, Any]:
        return {
            "jira": {
                "outbound_fields": {
                    "summary": "incident.title",
                    "description": "report.root_cause + evidence",
                    "labels": "incident.tags",
                    "assignee": "asset.owner",
                },
                "inbound_fields": {
                    "status": "ticket.status",
                    "resolution": "ticket.resolution",
                },
            },
            "servicenow": {
                "outbound_fields": {
                    "short_description": "incident.title",
                    "description": "report.summary",
                    "assignment_group": "asset.owner_team",
                },
                "inbound_fields": {
                    "state": "ticket.state",
                    "work_notes": "ticket.work_notes",
                },
            },
            "slack": {
                "outbound_fields": {"channel": "sync.channel", "text": "report.summary"},
                "inbound_fields": {"thread_ts": "sync.thread_id"},
            },
            "feishu": {
                "outbound_fields": {"chat_id": "sync.chat_id", "content": "report.summary"},
                "inbound_fields": {"message_id": "sync.message_id"},
            },
            "pagerduty": {
                "outbound_fields": {"routing_key": "sync.routing_key", "payload": "incident+report"},
                "inbound_fields": {"incident_id": "ticket.incident_id"},
            },
        }

    async def get_external_sync_settings(self) -> Dict[str, Any]:
        async with self._lock:
            payload = self._read_json(
                self._sync_settings_file,
                {
                    "enabled": False,
                    "providers": ["jira", "servicenow", "slack", "feishu", "pagerduty"],
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            if not isinstance(payload, dict):
                payload = {"enabled": False, "providers": [], "updated_at": datetime.utcnow().isoformat()}
            return payload

    async def update_external_sync_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        enabled = bool(payload.get("enabled"))
        providers = payload.get("providers")
        if not isinstance(providers, list):
            providers = ["jira", "servicenow", "slack", "feishu", "pagerduty"]
        next_payload = {
            "enabled": enabled,
            "providers": [str(item).strip() for item in providers if str(item).strip()],
            "updated_at": datetime.utcnow().isoformat(),
        }
        async with self._lock:
            self._write_json(self._sync_settings_file, next_payload)
        return next_payload

    async def team_metrics(self, *, days: int = 7, limit: int = 50) -> Dict[str, Any]:
        """
        聚合团队维度治理指标：
        - success_rate
        - timeout_rate
        - tool_failure_rate
        - estimated_model_cost
        """
        window_days = max(1, int(days or 7))
        top_limit = max(1, int(limit or 50))
        window_start = datetime.now(timezone.utc) - timedelta(days=window_days)

        snapshot = self._load_debate_snapshot()
        sessions = list(snapshot.get("sessions") or [])
        results = list(snapshot.get("results") or [])
        result_by_session = {
            str(row.get("session_id") or ""): row for row in results if isinstance(row, dict)
        }

        grouped: Dict[str, Dict[str, Any]] = {}
        daily_cost_tokens: Dict[str, int] = {}
        timeout_hotspots: Dict[str, int] = {}
        tool_failure_topn: Dict[str, int] = {}
        sla_samples: Dict[str, List[int]] = {
            "first_evidence_latency_ms": [],
            "first_conclusion_latency_ms": [],
            "report_latency_ms": [],
        }

        def _parse_ts(raw: Any) -> datetime | None:
            text = str(raw or "").strip()
            if not text:
                return None
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return None
        for session in sessions:
            if not isinstance(session, dict):
                continue
            if not self._is_recent(session.get("created_at"), window_start):
                continue
            session_id = str(session.get("id") or "").strip()
            if not session_id:
                continue
            result = result_by_session.get(session_id, {})
            team = self._resolve_team_name(session, result)
            metrics = grouped.setdefault(
                team,
                {
                    "team": team,
                    "sessions": 0,
                    "completed": 0,
                    "failed": 0,
                    "cancelled": 0,
                    "llm_calls": 0,
                    "timeouts": 0,
                    "tool_calls": 0,
                    "tool_failures": 0,
                    "estimated_prompt_tokens": 0,
                    "estimated_completion_tokens": 0,
                    "estimated_total_tokens": 0,
                    "estimated_model_cost": 0.0,
                    "avg_confidence": 0.0,
                    "_confidence_sum": 0.0,
                    "_confidence_count": 0,
                    "session_ids": [],
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            metrics["sessions"] += 1
            metrics["session_ids"].append(session_id)
            status = str(session.get("status") or "").lower()
            if status == "completed":
                metrics["completed"] += 1
            elif status == "cancelled":
                metrics["cancelled"] += 1
            elif status in {"failed", "error"}:
                metrics["failed"] += 1

            confidence = self._safe_float(result.get("confidence"), -1.0)
            if confidence >= 0:
                metrics["_confidence_sum"] += confidence
                metrics["_confidence_count"] += 1

            # 从 runtime 事件文件聚合超时 / 工具失败 / token 成本估算
            events = self._load_runtime_events(session_id)
            first_event_at: datetime | None = None
            first_evidence_at: datetime | None = None
            first_conclusion_at: datetime | None = None
            report_ready_at: datetime | None = None
            for event in events:
                event_type = str(event.get("type") or "").strip().lower()
                event_ts = _parse_ts(event.get("timestamp"))
                if event_ts and first_event_at is None:
                    first_event_at = event_ts
                if event_type == "llm_http_request":
                    metrics["llm_calls"] += 1
                    prompt_len = self._safe_int(event.get("prompt_length"), 0)
                    max_tokens = self._safe_int(event.get("max_tokens"), 0)
                    # 粗估 token：中文按 1 char≈1 token 做安全上界估算
                    metrics["estimated_prompt_tokens"] += max(0, prompt_len)
                    metrics["estimated_completion_tokens"] += max(0, max_tokens)
                    day_key = str(event_ts.date().isoformat()) if event_ts else "unknown"
                    daily_cost_tokens[day_key] = daily_cost_tokens.get(day_key, 0) + max(0, prompt_len + max_tokens)
                if event_type in {"llm_call_timeout", "llm_request_failed"}:
                    metrics["timeouts"] += 1
                    key = f"{str(event.get('agent_name') or 'unknown')}::{event_type}"
                    timeout_hotspots[key] = timeout_hotspots.get(key, 0) + 1
                if event_type.startswith("agent_tool_") or event_type.startswith("tool_"):
                    metrics["tool_calls"] += 1
                    io_status = str(event.get("io_status") or event.get("status") or "").strip().lower()
                    if event_type == "agent_tool_context_failed" or io_status in {"error", "failed", "timeout"}:
                        metrics["tool_failures"] += 1
                        tool_name = str(event.get("tool_name") or event.get("name") or "unknown")
                        tool_failure_topn[tool_name] = tool_failure_topn.get(tool_name, 0) + 1
                if event_ts and first_evidence_at is None and event_type in {
                    "asset_interface_mapping_completed",
                    "agent_tool_context_prepared",
                    "agent_round",
                    "agent_chat_message",
                }:
                    first_evidence_at = event_ts
                if event_ts and first_conclusion_at is None and event_type in {"agent_round", "result_ready"}:
                    first_conclusion_at = event_ts
                if event_ts and event_type in {"runtime_debate_completed", "result_ready"}:
                    report_ready_at = event_ts
            if first_event_at and first_evidence_at:
                sla_samples["first_evidence_latency_ms"].append(
                    max(0, int((first_evidence_at - first_event_at).total_seconds() * 1000))
                )
            if first_event_at and first_conclusion_at:
                sla_samples["first_conclusion_latency_ms"].append(
                    max(0, int((first_conclusion_at - first_event_at).total_seconds() * 1000))
                )
            if first_event_at and report_ready_at:
                sla_samples["report_latency_ms"].append(
                    max(0, int((report_ready_at - first_event_at).total_seconds() * 1000))
                )

        # 估算模型成本（默认 0.002 CNY / 1K tokens，便于治理趋势对比）
        estimated_unit_cost = 0.002
        rows: List[Dict[str, Any]] = []
        for team, metrics in grouped.items():
            prompt_tokens = self._safe_int(metrics.get("estimated_prompt_tokens"), 0)
            completion_tokens = self._safe_int(metrics.get("estimated_completion_tokens"), 0)
            total_tokens = prompt_tokens + completion_tokens
            metrics["estimated_total_tokens"] = total_tokens
            metrics["estimated_model_cost"] = round((total_tokens / 1000.0) * estimated_unit_cost, 4)
            sessions_count = max(1, self._safe_int(metrics.get("sessions"), 0))
            llm_calls = max(1, self._safe_int(metrics.get("llm_calls"), 0))
            tool_calls = max(1, self._safe_int(metrics.get("tool_calls"), 0))
            metrics["success_rate"] = round(self._safe_int(metrics.get("completed"), 0) / sessions_count, 4)
            metrics["timeout_rate"] = round(self._safe_int(metrics.get("timeouts"), 0) / llm_calls, 4)
            metrics["tool_failure_rate"] = round(self._safe_int(metrics.get("tool_failures"), 0) / tool_calls, 4)
            if self._safe_int(metrics.get("_confidence_count"), 0) > 0:
                metrics["avg_confidence"] = round(
                    self._safe_float(metrics.get("_confidence_sum"), 0.0)
                    / self._safe_int(metrics.get("_confidence_count"), 1),
                    4,
                )
            metrics["window_days"] = window_days
            metrics.pop("_confidence_sum", None)
            metrics.pop("_confidence_count", None)
            rows.append(metrics)

        rows.sort(
            key=lambda item: (
                -self._safe_int(item.get("sessions"), 0),
                -self._safe_float(item.get("estimated_model_cost"), 0.0),
                str(item.get("team") or ""),
            )
        )
        trend_rows = [
            {
                "day": day,
                "estimated_tokens": tokens,
                "estimated_model_cost": round((tokens / 1000.0) * 0.002, 4),
            }
            for day, tokens in sorted(daily_cost_tokens.items())
            if day != "unknown"
        ]
        hotspot_rows = [
            {"key": key, "count": count}
            for key, count in sorted(timeout_hotspots.items(), key=lambda item: item[1], reverse=True)[:20]
        ]
        tool_failure_rows = [
            {"tool_name": key, "count": count}
            for key, count in sorted(tool_failure_topn.items(), key=lambda item: item[1], reverse=True)[:20]
        ]
        sla = {}
        for name, samples in sla_samples.items():
            if samples:
                sla[name] = int(sum(samples) / max(1, len(samples)))
            else:
                sla[name] = 0
        return {
            "window_days": window_days,
            "generated_at": datetime.utcnow().isoformat(),
            "items": rows[:top_limit],
            "token_cost_trend": trend_rows,
            "timeout_hotspots": hotspot_rows,
            "tool_failure_topn": tool_failure_rows,
            "sla": sla,
        }

    async def session_replay(self, session_id: str, *, limit: int = 120) -> Dict[str, Any]:
        payload = await replay_session_lineage(session_id, limit=max(1, int(limit or 120)))
        snapshot = self._load_debate_snapshot()
        sessions = {
            str(item.get("id") or ""): item
            for item in list(snapshot.get("sessions") or [])
            if isinstance(item, dict)
        }
        results = {
            str(item.get("session_id") or ""): item
            for item in list(snapshot.get("results") or [])
            if isinstance(item, dict)
        }
        session = sessions.get(session_id, {})
        result = results.get(session_id, {})
        return {
            **payload,
            "session_status": str(session.get("status") or ""),
            "incident_id": str(session.get("incident_id") or ""),
            "root_cause": str(result.get("root_cause") or ""),
            "confidence": self._safe_float(result.get("confidence"), 0.0),
        }


governance_ops_service = GovernanceOpsService()
