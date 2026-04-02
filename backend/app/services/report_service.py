"""
报告服务模块

本模块提供故障分析报告的管理和生成功能。

核心功能：
1. 报告查询和列表
2. 报告生成和重新生成
3. 报告版本对比
4. 分享链接管理

报告格式：
- markdown: Markdown 格式（默认）
- json: JSON 格式
- html: HTML 格式
- pdf: PDF 格式（未实现）

工作流程：
1. 故障分析完成 -> 生成报告
2. 报告存储到仓储
3. 支持分享和版本管理

使用场景：
- 前端展示分析结果
- 导出报告文档
- 分享分析结论

Report Service
"""

import difflib
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from app.models.debate import DebateResult
from app.repositories.report_repository import (
    InMemoryReportRepository,
    FileReportRepository,
    ReportRepository,
    SqliteReportRepository,
)
from app.services.debate_service import debate_service
from app.services.incident_service import incident_service
from app.services.report_generation_service import report_generation_service
from app.config import settings


class ReportService:
    """
    报告查询与导出服务

    提供报告的完整生命周期管理：
    - 查询：获取最新报告、历史版本
    - 生成：基于辩论结果生成报告
    - 对比：比较不同版本的差异
    - 分享：生成分享链接

    属性：
    - _repository: 报告存储仓储
    """

    def __init__(self, repository: Optional[ReportRepository] = None):
        """
        初始化报告服务

        根据配置选择存储后端：
        - file: 文件存储
        - memory: 内存存储

        Args:
            repository: 报告仓储，未提供则根据配置选择
        """
        self._repository = repository or (
            InMemoryReportRepository()
            if settings.LOCAL_STORE_BACKEND == "memory"
            else SqliteReportRepository()
        )

    async def get_report(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """
        获取故障的最新报告

        Args:
            incident_id: 故障 ID

        Returns:
            Optional[Dict[str, Any]]: 报告数据，不存在则返回 None
        """
        return await self._repository.get_latest(incident_id)

    async def list_reports(self, incident_id: str) -> list[Dict[str, Any]]:
        """
        列出故障的所有历史报告

        Args:
            incident_id: 故障 ID

        Returns:
            list[Dict[str, Any]]: 报告列表（按时间排序）
        """
        return await self._repository.list_by_incident(incident_id)

    async def compare_latest_reports(self, incident_id: str) -> Dict[str, Any]:
        """
        对比最近两版报告

        生成 unified diff 格式的差异对比。

        Args:
            incident_id: 故障 ID

        Returns:
            Dict[str, Any]: 对比结果，包含 diff_lines
        """
        items = await self._repository.list_by_incident(incident_id)
        if len(items) < 2:
            return {
                "incident_id": incident_id,
                "base_report_id": None,
                "target_report_id": None,
                "changed": False,
                "diff_lines": [],
                "summary": "历史版本不足 2 份，无法生成差异对比。",
            }

        base = items[-2]
        target = items[-1]
        base_text = str(base.get("content") or "")
        target_text = str(target.get("content") or "")

        # 生成 unified diff
        diff_lines = list(
            difflib.unified_diff(
                base_text.splitlines(),
                target_text.splitlines(),
                fromfile=str(base.get("report_id") or "base"),
                tofile=str(target.get("report_id") or "target"),
                lineterm="",
            )
        )

        changed = base_text != target_text
        summary = "检测到报告版本差异" if changed else "两个版本内容一致"

        return {
            "incident_id": incident_id,
            "base_report_id": base.get("report_id"),
            "target_report_id": target.get("report_id"),
            "changed": changed,
            "diff_lines": diff_lines[:500],
            "summary": summary,
        }

    async def save_generated_report(
        self,
        report: Dict[str, Any],
        debate_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        保存生成的报告

        统一处理时间字段并存储。

        Args:
            report: 报告数据
            debate_session_id: 辩论会话 ID

        Returns:
            Dict[str, Any]: 保存后的报告数据
        """
        payload = dict(report or {})
        if debate_session_id:
            payload["debate_session_id"] = debate_session_id

        # 处理时间字段
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
        """
        获取或生成报告

        如果报告已存在且不强制重新生成，返回现有报告。
        否则基于故障和辩论结果生成新报告。

        Args:
            incident_id: 故障 ID
            format: 报告格式（markdown/json/html）
            force_regenerate: 是否强制重新生成

        Returns:
            Dict[str, Any]: 报告数据

        Raises:
            ValueError: 故障不存在或缺少辩论结果
        """
        # 尝试获取现有报告
        if not force_regenerate:
            existed = await self._repository.get_latest_by_format(incident_id, format)
            if existed:
                return existed

        # 获取故障信息
        incident = await incident_service.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        if not incident.debate_session_id:
            raise ValueError(f"Incident {incident_id} has no debate session")

        # 获取辩论结果
        debate_result = await debate_service.get_result(incident.debate_session_id)
        if not debate_result:
            raise ValueError(
                f"Debate result for incident {incident_id} not found. "
                "Execute debate first."
            )

        # 检查辩论结果有效性
        if not self._has_effective_debate_result(debate_result):
            raise ValueError("缺少有效大模型结论，已拒绝生成报告。请先完成有效辩论结论后重试。")

        # 获取资产信息
        session = await debate_service.get_session(incident.debate_session_id)
        assets = session.context.get("assets", {}) if session else {}

        # 生成报告
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
        """
        强制重新生成报告

        Args:
            incident_id: 故障 ID
            format: 报告格式

        Returns:
            Dict[str, Any]: 新生成的报告
        """
        return await self.get_or_generate_report(
            incident_id=incident_id,
            format=format,
            force_regenerate=True,
        )

    async def create_share_link(self, incident_id: str) -> Dict[str, Any]:
        """
        创建报告分享链接

        生成一个可通过 URL 访问的分享令牌。

        Args:
            incident_id: 故障 ID

        Returns:
            Dict[str, Any]: 分享信息，包含 share_token 和 share_url
        """
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
        """
        通过分享令牌获取报告

        Args:
            token: 分享令牌

        Returns:
            Optional[Dict[str, Any]]: 报告数据，令牌无效则返回 None
        """
        incident_id = await self._repository.get_incident_id_by_share_token(token)
        if not incident_id:
            return None
        return await self._repository.get_latest(incident_id)

    def _build_debate_payload(self, result: DebateResult) -> Dict[str, Any]:
        """
        构建报告生成器所需的载荷

        将辩论结果转换为报告生成器需要的格式。

        Args:
            result: 辩论结果

        Returns:
            Dict[str, Any]: 载荷数据
        """
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
            "root_cause_candidates": [
                item.model_dump(mode="json") for item in (result.root_cause_candidates or [])
            ],
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
        """
        判断辩论结果是否有效

        检查辩论结果是否满足生成报告的最低门槛：
        - 有根因结论
        - 结论不是"需要进一步分析"等无效内容
        - 置信度大于 0
        - 有证据链
        - 证据来源包含日志和其他类型

        Args:
            result: 辩论结果

        Returns:
            bool: 是否有效
        """
        summary = str(result.root_cause or "").strip()
        if not summary:
            return False

        # 检查无效结论
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

        # 检查置信度
        if float(result.confidence or 0.0) <= 0.0:
            return False

        # 检查证据链
        if not result.evidence_chain:
            return False

        # 检查证据来源多样性
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


# 全局实例
report_service = ReportService()
