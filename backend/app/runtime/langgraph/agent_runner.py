"""
Agent 执行运行器模块。

这个文件只负责“如何安全地调用一次 Agent”，不承载 Prompt 组装、
路由判断或状态机逻辑。它存在的目的就是把错误分级统一收口：
- 致命错误直接上抛
- 非致命错误转成 fallback turn
"""

from __future__ import annotations

from typing import Any, Optional

from app.runtime.langgraph.execution import FatalLLMError, call_agent
from app.runtime.langgraph.state import AgentSpec, DebateTurn


class AgentRunner:
    """
    Agent 执行统一入口。

    它把“单个 Agent 一轮执行”的调用细节统一收口到一处：
    - 正常路径走 `call_agent`
    - 致命错误直接上抛
    - 非致命错误转成 fallback turn，保证整轮轨迹不断裂
    """

    def __init__(self, orchestrator: Any):
        """
        初始化 Agent 运行器

        Args:
            orchestrator: 编排器实例，用于访问后备方法
        """
        self._orchestrator = orchestrator

    async def run_agent(
        self,
        *,
        spec: AgentSpec,
        prompt: str,
        round_number: int,
        loop_round: int,
        history_cards_context: Optional[list[Any]] = None,
        execution_context: Optional[dict[str, Any]] = None,
    ) -> DebateTurn:
        """
        执行单个 Agent 的一轮调用。

        这里故意不在 runner 内部做太多业务判断，只统一处理错误分级：
        - `FatalLLMError` 直接终止整场会话
        - 其他异常转成 fallback turn，留给后续流程决定如何降级
        """
        try:
            # 正常路径：交给 execution 层完成模型调用、重试和输出归一化。
            return await call_agent(
                self._orchestrator,
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
                history_cards_context=history_cards_context,
                execution_context=execution_context,
            )
        except FatalLLMError:
            # 致命错误直接抛出，交给更上层决定是否中止整场会话。
            raise
        except Exception as exc:  # pragma: no cover - fallback path
            # 其他异常统一转成 fallback turn，保证轨迹和前端展示不断裂。
            error_text = str(exc).strip() or exc.__class__.__name__
            return await self._orchestrator._create_fallback_turn(
                spec=spec,
                prompt=prompt,
                round_number=round_number,
                loop_round=loop_round,
                error_text=error_text,
            )


__all__ = ["AgentRunner"]
