"""
路由规则引擎模块

本模块提供 LangGraph 辩论运行时的路由规则评估功能。

核心功能：
1. 规则优先级管理
2. 按优先级顺序评估规则
3. 返回第一个匹配的决策

默认规则集（按优先级）：
1. ConsensusRule (10): 检查是否达成共识
2. JudgeReadyRule (15): 检查 Judge 是否准备好
3. BudgetRule (20): 预算约束检查
4. RepetitionRule (30): 重复检测
5. CritiqueCycleRule (40): 批评循环管理
6. PostRebuttalSettleRule (45): 反驳后结算
7. CommanderSettleRule (50): Commander 置信度决策
8. NoCritiqueRevisitRule (55): 无批评重访

工作流程：
1. 状态变化 -> 构建路由上下文
2. 规则引擎评估 -> 返回路由决策
3. 执行路由决策 -> 决定下一步

Routing rule engine for LangGraph debate runtime.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from app.runtime.langgraph.routing.rules import RoutingContext, RoutingDecision, RoutingRule

logger = structlog.get_logger()


class RoutingRuleEngine:
    """
    路由规则引擎

    按优先级顺序评估路由规则，返回第一个匹配的决策。
    优先级数字越小，优先级越高。

    属性：
    - _rules: 规则列表（按优先级排序）

    使用示例：
    ```python
    engine = RoutingRuleEngine()
    decision = engine.evaluate(context)
    if decision.should_stop:
        # 结束辩论
        pass
    else:
        # 继续下一步
        pass
    ```
    """

    def __init__(self, rules: Optional[List[RoutingRule]] = None):
        """
        初始化规则引擎

        Args:
            rules: 可选的规则列表，未提供则使用默认规则
        """
        self._rules: List[RoutingRule] = []
        if rules is not None:
            for rule in rules:
                self.add_rule(rule)
        else:
            for rule in self._default_rules():
                self.add_rule(rule)

    def _default_rules(self) -> List[RoutingRule]:
        """
        创建默认规则集

        延迟导入以避免循环依赖。

        Returns:
            List[RoutingRule]: 默认规则列表
        """
        from app.runtime.langgraph.routing.rules_impl import (
            BudgetRule,
            CommanderSettleRule,
            ConsensusRule,
            CritiqueCycleRule,
            JudgeReadyRule,
            NoCritiqueRevisitRule,
            PostRebuttalSettleRule,
            RepetitionRule,
        )

        return [
            # 最高优先级：首先检查共识
            ConsensusRule(priority=10),
            # 检查 Judge 是否准备好做决策
            JudgeReadyRule(priority=15),
            # 预算约束
            BudgetRule(priority=20),
            # 重复检测
            RepetitionRule(priority=30),
            # 批评循环管理
            CritiqueCycleRule(priority=40),
            PostRebuttalSettleRule(priority=45),
            # Commander 置信度决策
            CommanderSettleRule(priority=50),
            NoCritiqueRevisitRule(priority=55),
        ]

    def add_rule(self, rule: RoutingRule) -> None:
        """
        添加规则

        规则按优先级排序插入。

        Args:
            rule: 要添加的规则
        """
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)
        logger.debug(
            "routing_rule_added",
            rule_name=rule.name,
            rule_priority=rule.priority,
            total_rules=len(self._rules),
        )

    def remove_rule(self, name: str) -> bool:
        """
        移除规则

        按名称移除规则。

        Args:
            name: 规则名称

        Returns:
            bool: 是否找到并移除
        """
        for i, rule in enumerate(self._rules):
            if rule.name == name:
                self._rules.pop(i)
                logger.debug(
                    "routing_rule_removed",
                    rule_name=name,
                    remaining_rules=len(self._rules),
                )
                return True
        return False

    def get_rule(self, name: str) -> Optional[RoutingRule]:
        """
        获取规则

        按名称查找规则。

        Args:
            name: 规则名称

        Returns:
            Optional[RoutingRule]: 规则对象，不存在则返回 None
        """
        for rule in self._rules:
            if rule.name == name:
                return rule
        return None

    def enable_rule(self, name: str) -> bool:
        """
        启用规则

        Args:
            name: 规则名称

        Returns:
            bool: 是否成功启用
        """
        rule = self.get_rule(name)
        if rule and hasattr(rule, "_enabled"):
            rule._enabled = True  # type: ignore
            return True
        return False

    def disable_rule(self, name: str) -> bool:
        """
        禁用规则

        Args:
            name: 规则名称

        Returns:
            bool: 是否成功禁用
        """
        rule = self.get_rule(name)
        if rule and hasattr(rule, "_enabled"):
            rule._enabled = False  # type: ignore
            return True
        return False

    def evaluate(self, ctx: RoutingContext) -> RoutingDecision:
        """
        评估所有规则

        按优先级顺序评估规则，返回第一个匹配的决策。
        如果没有规则匹配，返回默认决策（继续执行）。

        Args:
            ctx: 路由上下文

        Returns:
            RoutingDecision: 路由决策
        """
        for rule in self._rules:
            # 跳过禁用的规则
            if not rule.enabled:
                continue

            try:
                decision = rule.evaluate(ctx)
                if decision is not None:
                    logger.info(
                        "routing_rule_matched",
                        rule=rule.name,
                        priority=rule.priority,
                        next_step=decision.next_step,
                        should_stop=decision.should_stop,
                        reason=decision.reason,
                    )
                    return decision
            except Exception as e:
                logger.error(
                    "routing_rule_error",
                    rule=rule.name,
                    error=str(e),
                    exc_info=True,
                )
                # 出错时继续评估下一条规则

        # 默认决策：继续执行提议的下一步
        return RoutingDecision(
            next_step=ctx.next_step,
            should_stop=False,
            stop_reason="",
            reason="No matching rule, continue with proposed step",
        )

    def evaluate_from_state(
        self,
        state: Dict[str, Any],
        route_decision: Dict[str, Any],
        consensus_threshold: float,
        max_discussion_steps_default: int,
        parallel_analysis_agents: List[str],
        debate_enable_critique: bool,
        round_cards: List[Any],
    ) -> Dict[str, Any]:
        """
        从状态构建上下文并评估规则

        这是与现有代码集成的便捷方法。
        从状态中提取必要信息，构建路由上下文，评估规则。

        Args:
            state: 当前辩论状态
            route_decision: 提议的路由决策
            consensus_threshold: 共识阈值
            max_discussion_steps_default: 默认最大讨论步数
            parallel_analysis_agents: 并行分析 Agent 列表
            debate_enable_critique: 是否启用批评
            round_cards: 当前回合的卡片

        Returns:
            Dict[str, Any]: 路由决策字典
        """
        from app.runtime.langgraph.routing import (
            agent_from_step,
            judge_is_ready,
            recent_agent_card,
            recent_judge_card,
            round_agent_counts,
        )

        # 从状态中提取上下文
        discussion_step = int(state.get("discussion_step_count") or 0)
        max_steps = int(state.get("max_discussion_steps") or max_discussion_steps_default)
        next_step = str(route_decision.get("next_step") or "").strip()
        target_agent = agent_from_step(next_step)

        # 获取 Judge 信息
        judge_card = recent_judge_card(round_cards)
        judge_output = state.get("agent_outputs", {}).get("JudgeAgent", {})
        judge_confidence = float(
            (judge_output.get("confidence") or 0.0)
            or (getattr(judge_card, "confidence", 0.0) if judge_card else 0.0)
        )

        # 获取 Commander 信息
        commander_card = recent_agent_card(round_cards, "ProblemAnalysisAgent")
        commander_output = state.get("agent_outputs", {}).get("ProblemAnalysisAgent", {})
        if not commander_output and commander_card:
            commander_output = getattr(commander_card, "raw_output", {}) or {}
        commander_confidence = float(
            (commander_output.get("confidence") or 0.0)
            or (getattr(commander_card, "confidence", 0.0) if commander_card else 0.0)
        )

        # 统计未解决项
        unresolved_items: List[str] = []
        for key in ("open_questions", "missing_info", "needs_validation"):
            value = commander_output.get(key)
            if isinstance(value, list):
                unresolved_items.extend([str(v or "").strip() for v in value if str(v or "").strip()])
            elif isinstance(value, str) and value.strip():
                unresolved_items.append(value.strip())
        unresolved_count = len(list(dict.fromkeys(unresolved_items)))

        # 构建路由上下文
        ctx = RoutingContext(
            state=state,
            discussion_step=discussion_step,
            max_steps=max_steps,
            round_cards=round_cards,
            agent_counts=round_agent_counts(round_cards),
            judge_confidence=judge_confidence,
            judge_card=judge_card,
            commander_confidence=commander_confidence,
            commander_output=commander_output,
            unresolved_count=unresolved_count,
            target_agent=target_agent,
            next_step=next_step,
            debate_enable_critique=debate_enable_critique,
            parallel_analysis_agents=parallel_analysis_agents,
        )

        # 评估规则
        decision = self.evaluate(ctx)

        # 合并原始决策
        result = dict(route_decision)
        result.update(decision.to_dict())
        return result

    @property
    def rules(self) -> List[RoutingRule]:
        """
        获取规则列表（只读）

        Returns:
            List[RoutingRule]: 规则列表
        """
        return list(self._rules)


__all__ = ["RoutingRuleEngine"]