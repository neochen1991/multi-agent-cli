"""
人工审核边界辅助。

把“等待人工审核时需要落什么状态”和“最终载荷里如何挂审核信息”
抽成稳定 helper，避免 runtime / service 层各自拼一套 review 结构。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, Optional


class ReviewBoundary:
    """统一封装人工审核相关的状态与载荷结构。"""

    @staticmethod
    def _utc_now_iso() -> str:
        """统一输出带时区的 UTC 时间，避免不同调用方各自处理时间格式。"""
        return datetime.now(UTC).isoformat()

    def build_review_state(
        self,
        *,
        reason: str,
        payload: Optional[Dict[str, Any]] = None,
        resume_from_step: str = "report_generation",
        requested_at: str = "",
    ) -> Dict[str, Any]:
        """构造等待人工审核时写入 session/context 的标准状态。"""
        return {
            "status": "pending",
            "reason": str(reason or ""),
            "payload": dict(payload or {}),
            "resume_from_step": str(resume_from_step or "report_generation"),
            "requested_at": str(requested_at or self._utc_now_iso()),
        }

    def attach_review_to_payload(self, final_payload: Dict[str, Any], review_state: Dict[str, Any]) -> Dict[str, Any]:
        """把 review_state 投影到最终载荷，供 UI / report / resume 统一消费。"""
        merged = dict(final_payload or {})
        normalized_state = self.build_review_state(
            reason=str((review_state or {}).get("reason") or ""),
            payload=dict((review_state or {}).get("payload") or {}),
            resume_from_step=str((review_state or {}).get("resume_from_step") or "report_generation"),
            requested_at=str((review_state or {}).get("requested_at") or ""),
        )
        merged["awaiting_human_review"] = True
        merged["human_review"] = normalized_state
        return merged
