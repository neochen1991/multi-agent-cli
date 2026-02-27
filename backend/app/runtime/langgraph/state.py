"""
Typed state and lightweight runtime models for LangGraph orchestration.
LangGraph 标准状态定义，使用 Annotated + Reducer 实现规范的状态管理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Any, Dict, List, Mapping, Optional, Tuple, TypedDict

from langgraph.graph import MessagesState
from langchain_core.messages import BaseMessage

from app.runtime.messages import AgentEvidence


# ============================================================================
# State Reducers (Annotated type reducers)
# ============================================================================


def merge_agent_outputs(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """
    合并 Agent 输出的 Reducer。

    新的输出会覆盖同名 Agent 的旧输出，其他保持不变。

    Args:
        left: 现有的 agent_outputs
        right: 新增的 agent_outputs

    Returns:
        合并后的 agent_outputs
    """
    if left is None:
        return right or {}
    if right is None:
        return left or {}
    return {**left, **right}


def extend_evidence_chain(left: List[Dict[str, Any]], right: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    扩展证据链的 Reducer。

    将新的证据追加到现有证据链末尾。

    Args:
        left: 现有的 evidence_chain
        right: 新增的 evidence_chain

    Returns:
        扩展后的 evidence_chain
    """
    if left is None:
        return right or []
    if right is None:
        return left or []
    return list(left) + list(right)


def extend_history_cards(left: List[AgentEvidence], right: List[AgentEvidence]) -> List[AgentEvidence]:
    """
    扩展历史卡片的 Reducer。

    将新的历史卡片追加到现有列表末尾。

    Args:
        left: 现有的 history_cards
        right: 新增的 history_cards

    Returns:
        扩展后的 history_cards
    """
    if left is None:
        return right or []
    if right is None:
        return left or []
    return list(left) + list(right)


def merge_claims(left: List[Dict[str, Any]], right: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    合并声明的 Reducer。

    追加新的声明到现有列表末尾。

    Args:
        left: 现有的 claims
        right: 新增的 claims

    Returns:
        合并后的 claims
    """
    if left is None:
        return right or []
    if right is None:
        return left or []
    return list(left) + list(right)


def merge_context(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """
    合并上下文的 Reducer。

    深度合并上下文字典，新值覆盖旧值。

    Args:
        left: 现有的 context
        right: 新增的 context

    Returns:
        合并后的 context
    """
    if left is None:
        return right or {}
    if right is None:
        return left or {}
    result = dict(left)
    for key, value in right.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


def take_latest(left: Any, right: Any) -> Any:
    """
    取最新值的 Reducer。

    简单地返回右侧（新）值。

    Args:
        left: 旧值
        right: 新值

    Returns:
        新值（如果存在），否则返回旧值
    """
    return right if right is not None else left


def increment_counter(left: int, right: int) -> int:
    """
    增量计数器的 Reducer。

    将新值加到现有值上。

    Args:
        left: 现有计数
        right: 增量

    Returns:
        增加后的计数
    """
    if left is None:
        left = 0
    if right is None:
        right = 0
    return left + right


# ============================================================================
# TypedDict State Definitions
# ============================================================================


class DebateMessagesState(MessagesState, total=False):
    """
    LangGraph-style 消息状态基类。

    继承自 MessagesState，自动提供 messages 字段。
    total=False 使所有字段可选，但推荐使用明确的默认值。
    """

    # messages 由 MessagesState 提供，自动使用 add_messages reducer
    pass


class PhaseState(TypedDict, total=False):
    """Structured execution phase state."""

    current_round: int
    executed_rounds: int
    consensus_reached: bool
    continue_next_round: bool


class RoutingState(TypedDict, total=False):
    """Structured routing/control state."""

    next_step: str
    agent_commands: Dict[str, Dict[str, Any]]
    discussion_step_count: int
    max_discussion_steps: int
    round_start_turn_index: int
    agent_mailbox: Dict[str, List[Dict[str, Any]]]
    supervisor_stop_requested: bool
    supervisor_stop_reason: str
    supervisor_notes: List[Dict[str, Any]]


class OutputState(TypedDict, total=False):
    """Structured output/evidence state."""

    history_cards: List[AgentEvidence]
    agent_outputs: Dict[str, Dict[str, Any]]
    evidence_chain: List[Dict[str, Any]]
    claims: List[Dict[str, Any]]
    open_questions: List[str]
    final_payload: Dict[str, Any]


class DebateExecState(DebateMessagesState):
    """
    LangGraph 辩论执行状态定义。

    使用 Annotated 类型配合 Reducer 函数，实现规范的状态管理。

    状态字段职责说明：

    ┌────────────────────────────────────────────────────────────────────┐
    │                        核心上下文                                    │
    ├─────────────┬──────────────────────────────────────────────────────┤
    │ context     │ 完整的问题上下文（日志、代码、配置等原始输入）           │
    │             │ 用途：Agent执行时的输入数据源                          │
    │             │ Reducer：深度合并（新值覆盖旧值，嵌套字典递归合并）       │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ context_    │ 上下文摘要（精简后的关键信息）                         │
    │ summary     │ 用途：快速访问上下文摘要，减少token消耗                │
    │             │ Reducer：取最新值                                     │
    └─────────────┴──────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────────────────────────────────┐
    │                      Agent 输出与历史                                │
    ├─────────────┬──────────────────────────────────────────────────────┤
    │ history_    │ Agent 输出卡片列表（前端展示用）                       │
    │ cards       │ 用途：存储每个Agent的分析结果，用于前端渲染            │
    │             │ Reducer：扩展追加（新卡片添加到末尾）                   │
    │             │ 注意：与messages相似但结构更适合前端展示               │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ agent_      │ 按Agent名称组织的输出字典                              │
    │ outputs     │ 用途：快速查询特定Agent的最新输出                      │
    │             │ Reducer：合并覆盖（同名Agent新输出覆盖旧输出）          │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ evidence_   │ 全局证据链（所有Agent发现的证据）                      │
    │ chain       │ 用途：最终报告生成时汇总所有证据                       │
    │             │ Reducer：扩展追加                                      │
    │             │ 注意：与history_cards.evidence_chain类似，但为全局汇总 │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ claims      │ 声明列表（各Agent的结论性陈述）                        │
    │             │ 用途：快速查询各Agent的结论                            │
    │             │ Reducer：扩展追加                                      │
    │             │ 注意：与history_cards.conclusion类似，但为扁平列表     │
    └─────────────┴──────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────────────────────────────────┐
    │                        控制流状态                                    │
    ├─────────────┬──────────────────────────────────────────────────────┤
    │ current_    │ 当前回合数（从1开始）                                  │
    │ round       │ 用途：追踪分析进度                                    │
    │             │ Reducer：取最新值                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ executed_   │ 已执行回合数                                          │
    │ rounds      │ 用途：记录已完成的回合总数                             │
    │             │ Reducer：取最新值                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ consensus_  │ 是否达成共识                                          │
    │ reached     │ 用途：判断分析是否完成                                │
    │             │ Reducer：取最新值                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ continue_   │ 是否继续下一回合                                      │
    │ next_round  │ 用途：控制多回合循环                                  │
    │             │ Reducer：取最新值                                     │
    └─────────────┴──────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────────────────────────────────┐
    │                        路由控制                                      │
    ├─────────────┬──────────────────────────────────────────────────────┤
    │ next_step   │ 下一步骤（如 "speak:LogAgent", "analysis_parallel"）   │
    │             │ 用途：决定下一个执行的节点                            │
    │             │ Reducer：取最新值                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ agent_      │ Agent命令字典（由Commander下发）                       │
    │ commands    │ 用途：存储各Agent需要执行的任务                        │
    │             │ Reducer：合并覆盖                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ discussion_ │ 讨论步数计数                                          │
    │ step_count  │ 用途：防止无限循环，限制最大步数                       │
    │             │ Reducer：增量累加                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ max_        │ 最大讨论步数                                          │
    │ discussion_ │ 用途：配置驱动的步数限制                              │
    │ steps       │ Reducer：取最新值                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ round_      │ 回合开始时的turn索引                                  │
    │ start_turn_ │ 用途：计算当前回合的卡片范围                          │
    │ index       │ Reducer：取最新值                                     │
    └─────────────┴──────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────────────────────────────────┐
    │                     Supervisor 控制                                  │
    ├─────────────┬──────────────────────────────────────────────────────┤
    │ supervisor_ │ 是否请求停止                                          │
    │ stop_       │ 用途：允许外部或内部逻辑请求停止分析                   │
    │ requested   │ Reducer：取最新值                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ supervisor_ │ 停止原因                                              │
    │ stop_reason │ 用途：记录停止的具体原因                              │
    │             │ Reducer：取最新值                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ supervisor_ │ Supervisor笔记列表                                    │
    │ notes       │ 用途：记录每次路由决策的详细信息                       │
    │             │ Reducer：扩展追加                                     │
    └─────────────┴──────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────────────────────────────────┐
    │                         输出                                         │
    ├─────────────┬──────────────────────────────────────────────────────┤
    │ final_      │ 最终结果载荷                                          │
    │ payload     │ 用途：存储最终的分析结果，返回给API调用者              │
    │             │ Reducer：取最新值                                     │
    ├─────────────┼──────────────────────────────────────────────────────┤
    │ open_       │ 未决问题列表                                          │
    │ questions   │ 用途：记录尚未解决的问题，引导后续分析                 │
    │             │ Reducer：扩展追加                                     │
    └─────────────┴──────────────────────────────────────────────────────┘
    """

    # ==================== 核心上下文 ====================

    # 上下文信息（深度合并）
    # 完整的问题上下文：日志内容、解析数据、接口映射等原始输入
    context: Annotated[Dict[str, Any], merge_context]

    # 上下文摘要（取最新）
    # 精简后的关键信息，用于减少LLM token消耗
    context_summary: Annotated[Dict[str, Any], take_latest]

    # 分层状态快照（取最新）
    # 便于将扁平字段逐步迁移为分层状态，不破坏现有调用路径
    phase_state: Annotated[PhaseState, take_latest]
    routing_state: Annotated[RoutingState, take_latest]
    output_state: Annotated[OutputState, take_latest]

    # ==================== Agent 输出与历史 ====================

    # 历史卡片列表（取最新快照）
    # AgentEvidence卡片列表，每个卡片包含Agent的分析结果
    # 用于前端渲染和状态追踪
    history_cards: Annotated[List[AgentEvidence], take_latest]

    # Agent 输出字典（合并覆盖）
    # 按Agent名称组织的输出字典，便于快速查询
    agent_outputs: Annotated[Dict[str, Dict[str, Any]], merge_agent_outputs]

    # 证据链（扩展追加）
    # 全局证据链，汇总所有Agent发现的证据
    evidence_chain: Annotated[List[Dict[str, Any]], extend_evidence_chain]

    # 声明列表（取最新快照）
    # 各Agent的结论性陈述，扁平化存储便于查询
    claims: Annotated[List[Dict[str, Any]], take_latest]

    # ==================== 控制流状态 ====================

    # 当前回合数（取最新）
    # 从1开始计数，追踪分析进度
    current_round: Annotated[int, take_latest]

    # 已执行回合数（取最新）
    # 记录已完成的回合总数
    executed_rounds: Annotated[int, take_latest]

    # 是否达成共识（取最新）
    # 当JudgeAgent置信度超过阈值时为True
    consensus_reached: Annotated[bool, take_latest]

    # 是否继续下一回合（取最新）
    # 控制多回合循环
    continue_next_round: Annotated[bool, take_latest]

    # ==================== 路由控制 ====================

    # 下一步骤（取最新）
    # 格式：'speak:AgentName' 或 'analysis_parallel' 等
    next_step: Annotated[str, take_latest]

    # Agent 命令字典（合并）
    # 由Commander（ProblemAnalysisAgent）下发给各Agent的任务
    agent_commands: Annotated[Dict[str, Dict[str, Any]], merge_agent_outputs]

    # 讨论步数计数（取最新）
    # 节点返回绝对步数，避免 reducer 增量语义与节点更新语义冲突
    discussion_step_count: Annotated[int, take_latest]

    # 最大讨论步数（取最新）
    # 配置驱动的步数限制
    max_discussion_steps: Annotated[int, take_latest]

    # 回合开始轮次索引（取最新）
    # 用于计算当前回合的卡片范围
    round_start_turn_index: Annotated[int, take_latest]

    # Agent 消息邮箱（取最新）
    # 显式 agent 间通信总线：receiver -> [AgentMessage dict...]
    agent_mailbox: Annotated[Dict[str, List[Dict[str, Any]]], take_latest]

    # ==================== Supervisor 控制 ====================

    # 是否请求停止（取最新）
    # 允许外部或内部逻辑请求停止分析
    supervisor_stop_requested: Annotated[bool, take_latest]

    # 停止原因（取最新）
    # 记录停止的具体原因
    supervisor_stop_reason: Annotated[str, take_latest]

    # Supervisor 笔记（取最新快照）
    # 记录每次路由决策的详细信息
    supervisor_notes: Annotated[List[Dict[str, Any]], take_latest]

    # ==================== 输出 ====================

    # 最终结果载荷（取最新）
    # 存储最终的分析结果，返回给API调用者
    final_payload: Annotated[Dict[str, Any], take_latest]

    # 未决问题列表（取最新快照）
    # 记录尚未解决的问题，引导后续分析
    open_questions: Annotated[List[str], take_latest]


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class DebateTurn:
    """辩论回合记录"""

    round_number: int
    phase: str
    agent_name: str
    agent_role: str
    model: Dict[str, str]
    input_message: str
    output_content: Dict[str, Any]
    confidence: float
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


@dataclass(frozen=True)
class AgentSpec:
    """
    Agent 规格定义（不可变，运行时使用）

    用于运行时 Agent 执行的完整规格定义。
    包含 Agent 的基本信息（name, role, phase, system_prompt）
    以及运行时配置（tools, max_tokens, timeout, temperature）。

    职责说明：
    - name: Agent 唯一标识符
    - role: Agent 角色描述
    - phase: Agent 所属阶段（analysis, critique, rebuttal, judgment）
    - system_prompt: Agent 的系统提示
    - tools: Agent 可用的工具名称列表
    - max_tokens: 最大输出 token 数
    - timeout: 执行超时时间（秒）
    - temperature: LLM 温度参数
    """

    name: str
    role: str
    phase: str
    system_prompt: str
    # 运行时配置字段
    tools: Tuple[str, ...] = ()
    max_tokens: int = 320
    timeout: int = 35
    temperature: float = 0.15

    @classmethod
    def from_config(cls, config: Any) -> "AgentSpec":
        """
        从配置对象创建 AgentSpec（鸭子类型）。

        Args:
            config: 具备 Agent 配置字段的对象（name/role/phase/...）

        Returns:
            AgentSpec 实例
        """
        required_fields = ("name", "role", "phase")
        if any(not hasattr(config, field) for field in required_fields):
            raise TypeError(f"Expected config object with fields {required_fields}, got {type(config)}")
        return cls(
            name=str(getattr(config, "name")),
            role=str(getattr(config, "role")),
            phase=str(getattr(config, "phase")),
            system_prompt=str(getattr(config, "system_prompt", "") or ""),
            tools=tuple(getattr(config, "tools", ()) or ()),
            max_tokens=int(getattr(config, "max_tokens", 320) or 320),
            timeout=int(getattr(config, "timeout", 35) or 35),
            temperature=float(getattr(config, "temperature", 0.15) or 0.15),
        )


# ============================================================================
# State Utilities
# ============================================================================


def create_initial_state(
    context: Dict[str, Any],
    max_rounds: int = 1,
    max_discussion_steps: int = 20,
) -> DebateExecState:
    """
    创建初始辩论状态。

    Args:
        context: 初始上下文
        max_rounds: 最大回合数
        max_discussion_steps: 最大讨论步数

    Returns:
        初始化的 DebateExecState
    """
    return DebateExecState(
        messages=[],
        context=context,
        context_summary={},
        phase_state={
            "current_round": 1,
            "executed_rounds": 0,
            "consensus_reached": False,
            "continue_next_round": True,
        },
        routing_state={
            "next_step": "",
            "agent_commands": {},
            "discussion_step_count": 0,
            "max_discussion_steps": max_discussion_steps,
            "round_start_turn_index": 0,
            "agent_mailbox": {},
            "supervisor_stop_requested": False,
            "supervisor_stop_reason": "",
            "supervisor_notes": [],
        },
        output_state={
            "history_cards": [],
            "agent_outputs": {},
            "evidence_chain": [],
            "claims": [],
            "open_questions": [],
            "final_payload": {},
        },
        history_cards=[],
        agent_outputs={},
        evidence_chain=[],
        claims=[],
        open_questions=[],
        current_round=1,
        executed_rounds=0,
        consensus_reached=False,
        continue_next_round=True,
        agent_commands={},
        next_step="",
        round_start_turn_index=0,
        agent_mailbox={},
        discussion_step_count=0,
        max_discussion_steps=max_discussion_steps,
        supervisor_stop_requested=False,
        supervisor_stop_reason="",
        supervisor_notes=[],
        final_payload={},
    )


def get_state_summary(state: DebateExecState) -> Dict[str, Any]:
    """
    获取状态摘要，用于日志和调试。

    Args:
        state: 辩论状态

    Returns:
        状态摘要字典
    """
    return {
        "current_round": state.get("current_round", 0),
        "discussion_step_count": state.get("discussion_step_count", 0),
        "history_cards_count": len(state.get("history_cards", [])),
        "agent_outputs_count": len(state.get("agent_outputs", {})),
        "evidence_chain_count": len(state.get("evidence_chain", [])),
        "consensus_reached": state.get("consensus_reached", False),
        "supervisor_stop_requested": state.get("supervisor_stop_requested", False),
        "next_step": state.get("next_step", ""),
        "agent_mailbox_targets": len(state.get("agent_mailbox", {})),
        "phase_state_keys": list((state.get("phase_state") or {}).keys()),
        "routing_state_keys": list((state.get("routing_state") or {}).keys()),
        "output_state_keys": list((state.get("output_state") or {}).keys()),
    }


def structured_state_snapshot(state: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    从扁平状态生成分层状态快照。

    该函数用于在迁移期保持兼容：
    - 旧代码继续读写扁平字段
    - 新代码可消费 phase_state/routing_state/output_state
    """

    phase_state: PhaseState = {
        "current_round": int(state.get("current_round") or 0),
        "executed_rounds": int(state.get("executed_rounds") or 0),
        "consensus_reached": bool(state.get("consensus_reached") or False),
        "continue_next_round": bool(state.get("continue_next_round") or False),
    }
    routing_state: RoutingState = {
        "next_step": str(state.get("next_step") or ""),
        "agent_commands": dict(state.get("agent_commands") or {}),
        "discussion_step_count": int(state.get("discussion_step_count") or 0),
        "max_discussion_steps": int(state.get("max_discussion_steps") or 0),
        "round_start_turn_index": int(state.get("round_start_turn_index") or 0),
        "agent_mailbox": dict(state.get("agent_mailbox") or {}),
        "supervisor_stop_requested": bool(state.get("supervisor_stop_requested") or False),
        "supervisor_stop_reason": str(state.get("supervisor_stop_reason") or ""),
        "supervisor_notes": list(state.get("supervisor_notes") or []),
    }
    output_state: OutputState = {
        "history_cards": list(state.get("history_cards") or []),
        "agent_outputs": dict(state.get("agent_outputs") or {}),
        "evidence_chain": list(state.get("evidence_chain") or []),
        "claims": list(state.get("claims") or []),
        "open_questions": list(state.get("open_questions") or []),
        "final_payload": dict(state.get("final_payload") or {}),
    }
    return {
        "phase_state": phase_state,
        "routing_state": routing_state,
        "output_state": output_state,
    }


def sync_structured_state(state_update: Mapping[str, Any]) -> Dict[str, Any]:
    """
    为状态更新结果附加分层状态快照字段。
    """

    return {**dict(state_update), **structured_state_snapshot(state_update)}


__all__ = [
    # Reducers
    "merge_agent_outputs",
    "extend_evidence_chain",
    "extend_history_cards",
    "merge_claims",
    "merge_context",
    "take_latest",
    "increment_counter",
    # State classes
    "DebateMessagesState",
    "DebateExecState",
    "PhaseState",
    "RoutingState",
    "OutputState",
    # Data classes
    "DebateTurn",
    "AgentSpec",
    # Utilities
    "create_initial_state",
    "get_state_summary",
    "structured_state_snapshot",
    "sync_structured_state",
]
