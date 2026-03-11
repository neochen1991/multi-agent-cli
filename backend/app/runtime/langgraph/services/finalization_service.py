"""
终态收口服务。

把 runtime finalize 阶段里与“最终载荷 / 人工审核 / 终态事件”相关的
纯状态决策逻辑抽出来，避免编排器主类继续膨胀。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from app.runtime.messages import AgentEvidence
from app.runtime.langgraph.services.review_boundary import ReviewBoundary


@dataclass(frozen=True)
class FinalizationDecision:
    """描述 finalize 阶段应如何落终态。"""

    final_payload: Dict[str, Any]
    awaiting_human_review: bool
    runtime_event: Dict[str, Any]


@dataclass
class FinalizationService:
    """
    终态收口服务。

    它只负责“如何得到最终载荷”和“当前该走 completed 还是 waiting_review”，
    不负责真正写 session store 或发事件。
    """

    build_final_payload: Callable[..., Dict[str, Any]]
    review_boundary: ReviewBoundary
    normalize_final_payload: Callable[[Dict[str, Any]], Dict[str, Any]]

    def resolve(
        self,
        *,
        state: Dict[str, Any],
        history_cards: List[AgentEvidence],
        consensus_reached: bool,
        executed_rounds: int,
    ) -> FinalizationDecision:
        """
        根据当前状态解析 finalize 决策。

        返回值可直接驱动：
        - runtime_session_store.complete
        - runtime_session_store.mark_waiting_review
        - 终态事件发射
        """
        final_payload = dict(state.get("final_payload") or {})
        if not final_payload:
            # 中文注释：finalize 是最后一道兜底门，这里统一补出最终载荷，
            # 让上层编排器无需关心“中间节点是否显式写过 final_payload”。
            final_payload = self.build_final_payload(
                history_cards=history_cards,
                consensus_reached=consensus_reached,
                executed_rounds=executed_rounds,
            )
        final_payload = self.normalize_final_payload(final_payload)

        awaiting_human_review = bool(state.get("awaiting_human_review") or False)
        if awaiting_human_review:
            final_payload = self._attach_human_review(final_payload, state)
            runtime_event = {
                "type": "runtime_human_review_requested",
                "confidence": final_payload.get("confidence", 0.0),
                "consensus_reached": consensus_reached,
                "mode": "langgraph_runtime",
                "review_reason": str(state.get("human_review_reason") or "").strip(),
                "resume_from_step": str(state.get("resume_from_step") or "report_generation").strip(),
            }
        else:
            runtime_event = {
                "type": "runtime_debate_completed",
                "confidence": final_payload.get("confidence", 0.0),
                "consensus_reached": consensus_reached,
                "mode": "langgraph_runtime",
            }
        return FinalizationDecision(
            final_payload=final_payload,
            awaiting_human_review=awaiting_human_review,
            runtime_event=runtime_event,
        )

    def _attach_human_review(self, final_payload: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """把人工审核信息封装进最终载荷，供后续 UI / report / resume 统一读取。"""
        review_state = self.review_boundary.build_review_state(
            reason=str(state.get("human_review_reason") or "").strip(),
            payload=dict(state.get("human_review_payload") or {}),
            resume_from_step=str(state.get("resume_from_step") or "report_generation").strip(),
        )
        return self.review_boundary.attach_review_to_payload(final_payload, review_state)
