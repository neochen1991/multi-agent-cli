"""
Judge 边界辅助。

这里收敛两类能力：
1. Judge 输出的标准化入口；
2. final_payload 的最小合同兜底。

这样测试和上层服务可以走稳定 helper，而不是直接依赖 orchestrator 内部细节。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from app.runtime.messages import AgentEvidence


@dataclass
class JudgmentBoundary:
    """封装 Judge 相关的边界能力。"""

    normalize_agent_output_impl: Callable[[str, str], Dict[str, Any]]
    normalize_judge_output_impl: Callable[[Dict[str, Any], str], Dict[str, Any]]
    build_final_payload_impl: Callable[..., Dict[str, Any]]

    def normalize_agent_output(self, agent_name: str, raw_content: str) -> Dict[str, Any]:
        """通过统一入口解析 Agent 输出，便于测试和后续子图复用。"""
        return self.normalize_agent_output_impl(agent_name, raw_content)

    def normalize_judge_output(self, parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
        """通过统一入口恢复 Judge 的结构化裁决。"""
        return self.normalize_judge_output_impl(parsed, raw_content)

    def build_final_payload(
        self,
        *,
        history_cards: List[AgentEvidence],
        consensus_reached: bool,
        executed_rounds: int,
    ) -> Dict[str, Any]:
        """生成最终载荷后再做一层最小合同归一化。"""
        payload = self.build_final_payload_impl(
            history_cards=history_cards,
            consensus_reached=consensus_reached,
            executed_rounds=executed_rounds,
        )
        return self.normalize_final_payload(payload)

    @staticmethod
    def normalize_final_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        对 final_payload 做最小合同兜底。

        中文注释：这里不重写业务结论，只保证结果层能稳定读取
        `final_judgment / evidence_chain / claim_graph` 这些结构化字段。
        """
        merged = dict(payload or {})
        final_judgment = merged.get("final_judgment")
        final_judgment = final_judgment if isinstance(final_judgment, dict) else {}
        evidence_chain = final_judgment.get("evidence_chain")
        if not isinstance(evidence_chain, list):
            final_judgment["evidence_chain"] = []
        claim_graph = final_judgment.get("claim_graph")
        if not isinstance(claim_graph, dict):
            final_judgment["claim_graph"] = {}
        merged["final_judgment"] = final_judgment
        return merged
