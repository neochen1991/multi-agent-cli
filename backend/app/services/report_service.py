"""
报告服务
Report Service
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from app.models.debate import DebateResult
from app.repositories.report_repository import (
    InMemoryReportRepository,
    FileReportRepository,
    ReportRepository,
)
from app.services.debate_service import debate_service
from app.services.incident_service import incident_service
from app.services.report_generation_service import report_generation_service
from app.config import settings


class ReportService:
    """报告查询与导出服务"""

    def __init__(self, repository: Optional[ReportRepository] = None):
        self._repository = repository or (
            FileReportRepository()
            if settings.LOCAL_STORE_BACKEND == "file"
            else InMemoryReportRepository()
        )

    async def get_report(self, incident_id: str) -> Optional[Dict[str, Any]]:
        return await self._repository.get_latest(incident_id)

    async def save_generated_report(
        self,
        report: Dict[str, Any],
        debate_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = dict(report or {})
        if debate_session_id:
            payload["debate_session_id"] = debate_session_id
        generated_at = payload.get("generated_at")
        if isinstance(generated_at, str):
            try:
                payload["generated_at"] = datetime.fromisoformat(generated_at)
            except ValueError:
                payload["generated_at"] = datetime.utcnow()
        elif not isinstance(generated_at, datetime):
            payload["generated_at"] = datetime.utcnow()
        return await self._repository.save(payload)

    async def get_or_generate_report(
        self,
        incident_id: str,
        format: str = "markdown",
        force_regenerate: bool = False,
    ) -> Dict[str, Any]:
        if not force_regenerate:
            existed = await self._repository.get_latest_by_format(incident_id, format)
            if existed:
                return existed

        incident = await incident_service.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        if not incident.debate_session_id:
            raise ValueError(f"Incident {incident_id} has no debate session")

        debate_result = await debate_service.get_result(incident.debate_session_id)
        if not debate_result:
            raise ValueError(
                f"Debate result for incident {incident_id} not found. "
                "Execute debate first."
            )
        if not self._has_effective_debate_result(debate_result):
            raise ValueError("缺少有效大模型结论，已拒绝生成报告。请先完成有效辩论结论后重试。")

        session = await debate_service.get_session(incident.debate_session_id)
        assets = session.context.get("assets", {}) if session else {}

        generated = await report_generation_service.generate_report(
            incident=incident.model_dump(mode="json"),
            debate_result=self._build_debate_payload(debate_result),
            assets=assets,
            format=format,
        )

        generated["debate_session_id"] = incident.debate_session_id
        generated["generated_at"] = datetime.fromisoformat(generated["generated_at"])
        return await self._repository.save(generated)

    async def regenerate_report(
        self,
        incident_id: str,
        format: str = "markdown",
    ) -> Dict[str, Any]:
        return await self.get_or_generate_report(
            incident_id=incident_id,
            format=format,
            force_regenerate=True,
        )

    async def create_share_link(self, incident_id: str) -> Dict[str, Any]:
        report = await self.get_or_generate_report(incident_id=incident_id, format="markdown")
        token = f"shr_{uuid4().hex[:16]}"
        await self._repository.save_share_token(token, incident_id)
        return {
            "incident_id": incident_id,
            "report_id": report["report_id"],
            "share_token": token,
            "share_url": f"/api/v1/reports/shared/{token}",
            "created_at": datetime.utcnow(),
        }

    async def get_report_by_share_token(self, token: str) -> Optional[Dict[str, Any]]:
        incident_id = await self._repository.get_incident_id_by_share_token(token)
        if not incident_id:
            return None
        return await self._repository.get_latest(incident_id)

    def _build_debate_payload(self, result: DebateResult) -> Dict[str, Any]:
        evidence_chain = [item.model_dump(mode="json") for item in result.evidence_chain]

        final_judgment: Dict[str, Any] = {
            "root_cause": {
                "summary": result.root_cause,
                "category": result.root_cause_category,
            },
            "evidence_chain": evidence_chain,
        }
        if result.fix_recommendation:
            final_judgment["fix_recommendation"] = result.fix_recommendation.model_dump(
                mode="json"
            )
        if result.impact_analysis:
            final_judgment["impact_analysis"] = result.impact_analysis.model_dump(mode="json")
        if result.risk_assessment:
            final_judgment["risk_assessment"] = result.risk_assessment.model_dump(mode="json")
        if result.verification_plan:
            final_judgment["verification_plan"] = list(result.verification_plan)

        return {
            "final_judgment": final_judgment,
            "confidence": result.confidence,
            "action_items": result.action_items,
            "responsible_team": {
                "team": result.responsible_team,
                "owner": result.responsible_owner,
            },
            "dissenting_opinions": result.dissenting_opinions,
            "debate_history": [
                round_.model_dump(mode="json") for round_ in result.debate_history
            ],
        }

    @staticmethod
    def _has_effective_debate_result(result: DebateResult) -> bool:
        summary = str(result.root_cause or "").strip()
        if not summary:
            return False
        lowered = summary.lower()
        blocked_fragments = {
            "需要进一步分析",
            "insufficient",
            "unknown",
            "无法确定",
            "待补充信息",
        }
        if any(fragment in lowered for fragment in blocked_fragments):
            return False
        if float(result.confidence or 0.0) <= 0.0:
            return False
        if not result.evidence_chain:
            return False
        source_tokens = set()
        description_tokens = []
        for item in result.evidence_chain:
            type_text = str(getattr(item, "type", "") or "").lower()
            source_text = str(getattr(item, "source", "") or "").lower()
            source_tokens.add(type_text)
            source_tokens.add(source_text)
            description_tokens.append(str(getattr(item, "description", "") or "").lower())
        has_log = any("log" in token for token in source_tokens)
        has_other = any(
            marker in token
            for token in source_tokens
            for marker in ("code", "domain", "metrics", "change", "runbook")
        )
        if not has_log:
            has_log = any("日志" in text or "log" in text for text in description_tokens)
        if not has_other:
            has_other = any(
                any(marker in text for marker in ("代码", "领域", "指标", "变更", "runbook", "code", "domain", "metric", "change"))
                for text in description_tokens
            )
        if not (has_log and has_other):
            return False
        return True


report_service = ReportService()
