"""
回合记录服务模块

本模块提供 LangGraph 辩论运行时的回合记录和追踪功能。

核心功能：
1. 回合创建和记录
2. 回合历史管理
3. 回合统计查询
4. 转换为历史卡片

回合数据结构：
- round_number: 回合编号
- phase: 执行阶段
- agent_name: Agent 名称
- agent_role: Agent 角色
- model: 模型配置
- input_message: 输入提示词
- output_content: 输出内容
- confidence: 置信度
- started_at: 开始时间
- completed_at: 完成时间

使用场景：
- 记录 Agent 执行过程
- 生成历史卡片用于前端展示
- 统计分析 Agent 活跃度

Turn recorder service for LangGraph debate runtime.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.runtime.langgraph.state import DebateTurn
from app.runtime.messages import AgentEvidence

logger = structlog.get_logger()


class TurnRecorder:
    """
    回合记录器

    记录和追踪辩论回合。

    属性：
    - _turns: 回合列表
    - _turn_index: 回合索引（round_number -> DebateTurn）

    功能：
    - 记录 Agent 执行回合
    - 按 Agent/阶段查询回合
    - 转换为历史卡片
    """

    def __init__(self) -> None:
        """
        初始化回合记录器

        创建空的回合列表和索引。
        """
        self._turns: List[DebateTurn] = []
        self._turn_index: Dict[int, DebateTurn] = {}  # round_number -> turn

    @property
    def turns(self) -> List[DebateTurn]:
        """
        获取所有回合

        Returns:
            List[DebateTurn]: 回合列表（只读副本）
        """
        return list(self._turns)

    def record(
        self,
        turn: DebateTurn,
    ) -> None:
        """
        记录辩论回合

        将回合添加到历史记录。

        Args:
            turn: 要记录的回合
        """
        self._turns.append(turn)
        self._turn_index[turn.round_number] = turn

        logger.debug(
            "turn_recorded",
            round_number=turn.round_number,
            agent_name=turn.agent_name,
            phase=turn.phase,
        )

    def create_turn(
        self,
        *,
        agent_name: str,
        agent_role: str,
        phase: str,
        model: Dict[str, str],
        input_message: str,
        output_content: Dict[str, Any],
        confidence: float,
    ) -> DebateTurn:
        """
        创建新回合

        Args:
            agent_name: Agent 名称
            agent_role: Agent 角色
            phase: 执行阶段
            model: 模型配置
            input_message: 输入提示词
            output_content: Agent 输出内容
            confidence: 置信度

        Returns:
            DebateTurn: 新创建的回合
        """
        round_number = len(self._turns) + 1
        turn = DebateTurn(
            round_number=round_number,
            phase=phase,
            agent_name=agent_name,
            agent_role=agent_role,
            model=model,
            input_message=input_message,
            output_content=output_content,
            confidence=confidence,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        return turn

    def get_turn(self, round_number: int) -> Optional[DebateTurn]:
        """
        按编号获取回合

        Args:
            round_number: 回合编号

        Returns:
            Optional[DebateTurn]: 回合对象，不存在则返回 None
        """
        return self._turn_index.get(round_number)

    def get_turns_by_agent(self, agent_name: str) -> List[DebateTurn]:
        """
        按 Agent 获取回合

        Args:
            agent_name: Agent 名称

        Returns:
            List[DebateTurn]: 该 Agent 的所有回合
        """
        return [
            turn for turn in self._turns
            if turn.agent_name == agent_name
        ]

    def get_turns_by_phase(self, phase: str) -> List[DebateTurn]:
        """
        按阶段获取回合

        Args:
            phase: 阶段名称

        Returns:
            List[DebateTurn]: 该阶段的所有回合
        """
        return [
            turn for turn in self._turns
            if turn.phase == phase
        ]

    def get_last_turn(self) -> Optional[DebateTurn]:
        """
        获取最后一个回合

        Returns:
            Optional[DebateTurn]: 最后的回合，无记录则返回 None
        """
        if self._turns:
            return self._turns[-1]
        return None

    def get_turn_count(self) -> int:
        """
        获取回合总数

        Returns:
            int: 回合数量
        """
        return len(self._turns)

    def get_agent_turn_counts(self) -> Dict[str, int]:
        """
        获取各 Agent 的回合数

        Returns:
            Dict[str, int]: Agent 名称到回合数的映射
        """
        counts: Dict[str, int] = {}
        for turn in self._turns:
            counts[turn.agent_name] = counts.get(turn.agent_name, 0) + 1
        return counts

    def create_fallback_turn(
        self,
        *,
        agent_name: str,
        agent_role: str,
        phase: str,
        model: Dict[str, str],
        input_message: str,
        error_text: str,
    ) -> DebateTurn:
        """
        创建错误回退回合

        当 Agent 执行失败时创建错误回合。

        Args:
            agent_name: Agent 名称
            agent_role: Agent 角色
            phase: 执行阶段
            model: 模型配置
            input_message: 输入提示词
            error_text: 错误消息

        Returns:
            DebateTurn: 错误回合
        """
        round_number = len(self._turns) + 1
        turn = DebateTurn(
            round_number=round_number,
            phase=phase,
            agent_name=agent_name,
            agent_role=agent_role,
            model=model,
            input_message=input_message,
            output_content={
                "conclusion": f"Agent execution failed: {error_text}",
                "error": error_text,
            },
            confidence=0.0,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        return turn

    def clear(self) -> None:
        """
        清空所有回合记录
        """
        self._turns.clear()
        self._turn_index.clear()

    def to_history_cards(self) -> List[AgentEvidence]:
        """
        转换为历史卡片

        将回合记录转换为前端展示用的历史卡片。

        Returns:
            List[AgentEvidence]: 历史卡片列表
        """
        cards = []
        for turn in self._turns:
            card = AgentEvidence(
                agent_name=turn.agent_name,
                agent_role=turn.agent_role,
                phase=turn.phase,
                conclusion=str((turn.output_content or {}).get("conclusion") or ""),
                evidence_chain=list((turn.output_content or {}).get("evidence_chain") or []),
                confidence=turn.confidence,
                raw_output=turn.output_content,
                created_at=turn.completed_at or turn.started_at,
            )
            cards.append(card)
        return cards


__all__ = ["TurnRecorder"]