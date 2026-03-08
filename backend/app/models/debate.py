"""
辩论会话模型模块

本模块定义了辩论系统的核心数据模型：

状态枚举：
- DebateStatus: 辩论状态（PENDING/RUNNING/ANALYZING/.../COMPLETED）
- DebatePhase: 辩论阶段（COORDINATION/ANALYSIS/CRITIQUE/REBUTTAL/JUDGMENT）
- AgentRole: Agent 角色（LOG_ANALYST/DOMAIN_EXPERT/CODE_EXPERT/...）

核心模型：
- DebateRound: 单轮辩论记录
- DebateSession: 辩论会话
- DebateResult: 辩论结果
- EvidenceItem: 证据项
- FixRecommendation: 修复建议
- ImpactAnalysis: 影响分析
- RiskAssessment: 风险评估
- RootCauseCandidate: 根因候选

Debate Models
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DebateStatus(str, Enum):
    """
    辩论状态枚举

    状态流转：
    PENDING -> RUNNING -> ANALYZING -> DEBATING -> JUDGING -> COMPLETED
                     |          |           |
                     v          v           v
               CRITIQUING  WAITING    RETRYING
                     |          |           |
                     v          v           v
               REBUTTING   RETRYING    FAILED
                     |
                     v
                  JUDGING

    状态说明：
    - PENDING: 待开始，会话已创建但未执行
    - RUNNING: 运行中，总状态
    - ANALYZING: 分析阶段，各 Agent 独立分析
    - DEBATING: 辩论阶段，Agent 间讨论
    - CRITIQUING: 质疑阶段，CriticAgent 提出质疑
    - REBUTTING: 反驳阶段，RebuttalAgent 进行反驳
    - JUDGING: 裁决阶段，JudgeAgent 做出最终裁决
    - WAITING: 等待中，等待外部条件或重试窗口
    - RETRYING: 重试中
    - COMPLETED: 已完成
    - CANCELLED: 已取消
    - FAILED: 失败
    """
    PENDING = "pending"          # 待开始
    RUNNING = "running"          # 任务运行态（总状态）
    ANALYZING = "analyzing"      # 分析阶段
    DEBATING = "debating"        # 辩论执行中
    CRITIQUING = "critiquing"    # 质疑阶段
    REBUTTING = "rebutting"      # 反驳阶段
    JUDGING = "judging"          # 裁决阶段
    WAITING = "waiting"          # 等待外部条件/重试窗口
    RETRYING = "retrying"        # 重试中
    COMPLETED = "completed"      # 已完成
    CANCELLED = "cancelled"      # 已取消
    FAILED = "failed"            # 失败


class DebatePhase(str, Enum):
    """
    辩论阶段枚举

    阶段说明：
    - COORDINATION: 主Agent协调阶段，由 ProblemAnalysisAgent 调度
    - ANALYSIS: 独立分析阶段，各专家 Agent 独立分析
    - CRITIQUE: 交叉质疑阶段，CriticAgent 提出质疑
    - REBUTTAL: 反驳修正阶段，RebuttalAgent 进行反驳
    - JUDGMENT: 最终裁决阶段，JudgeAgent 做出裁决
    - VERIFICATION: 验证计划阶段，VerificationAgent 制定验证计划
    """
    COORDINATION = "coordination"  # 主Agent协调
    ANALYSIS = "analysis"        # 独立分析
    CRITIQUE = "critique"        # 交叉质疑
    REBUTTAL = "rebuttal"        # 反驳修正
    JUDGMENT = "judgment"        # 最终裁决
    VERIFICATION = "verification"  # 验证计划


class AgentRole(str, Enum):
    """
    Agent 角色枚举

    角色说明：
    - LOG_ANALYST: 日志分析专家，负责日志时间线重建
    - DOMAIN_EXPERT: 领域映射专家，负责接口到责任田映射
    - CODE_EXPERT: 代码分析专家，负责代码路径分析
    - CRITIC: 架构质疑专家，负责提出质疑
    - REBUTTAL: 技术反驳专家，负责反驳质疑
    - JUDGE: 技术委员会主席，负责最终裁决
    """
    LOG_ANALYST = "log_analyst"           # 日志分析专家
    DOMAIN_EXPERT = "domain_expert"       # 领域映射专家
    CODE_EXPERT = "code_expert"           # 代码分析专家
    CRITIC = "critic"                     # 架构质疑专家
    REBUTTAL = "rebuttal"                 # 技术反驳专家
    JUDGE = "judge"                       # 技术委员会主席


class DebateRound(BaseModel):
    """
    辩论轮次模型

    记录单个 Agent 在一轮辩论中的执行情况：
    - Agent 信息：名称、角色、使用的模型
    - 输入输出：输入消息和输出内容
    - 评估指标：置信度、推理 token 数、响应延迟
    - 时间戳：开始时间和完成时间
    """
    round_number: int = Field(..., description="轮次编号")
    phase: DebatePhase = Field(..., description="辩论阶段")
    agent_name: str = Field(..., description="Agent 名称")
    agent_role: str = Field(..., description="Agent 角色")
    model: Dict[str, str] = Field(..., description="使用的模型")

    # 输入输出
    input_message: str = Field(..., description="输入消息")
    output_content: Dict[str, Any] = Field(..., description="输出内容")

    # 评估指标
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    reasoning_tokens: Optional[int] = Field(None, description="推理 token 数")
    latency_ms: Optional[int] = Field(None, description="响应延迟(ms)")

    # 时间戳
    started_at: datetime = Field(default_factory=datetime.utcnow, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")

    class Config:
        """提供模型配置项，统一对象序列化与字段行为。"""
        json_schema_extra = {
            "example": {
                "round_number": 1,
                "phase": "analysis",
                "agent_name": "CodeAgent",
                "agent_role": "code_expert",
                "model": {"name": "glm-5"},
                "input_message": "分析以下日志...",
                "output_content": {"root_cause": "...", "evidence": [...]},
                "confidence": 0.85
            }
        }


class DebateSession(BaseModel):
    """
    辩论会话模型

    记录完整的辩论会话信息：
    - 基本信息：会话ID、关联故障ID
    - 状态信息：当前状态、当前阶段、当前轮次
    - 辩论历史：所有辩论轮次记录
    - 上下文数据：日志、解析数据、责任田线索、审计轨迹索引等
    - 时间戳：创建时间、更新时间、完成时间
    """
    id: str = Field(..., description="会话ID")
    incident_id: str = Field(..., description="关联故障ID")
    status: DebateStatus = Field(default=DebateStatus.PENDING, description="状态")
    current_phase: Optional[DebatePhase] = Field(None, description="当前阶段")
    current_round: int = Field(default=0, description="当前轮次")

    # 辩论历史
    rounds: List[DebateRound] = Field(default_factory=list, description="辩论轮次")

    # 上下文
    context: Dict[str, Any] = Field(default_factory=dict, description="上下文数据")

    # LLM 会话
    llm_session_id: Optional[str] = Field(None, description="LLM 会话ID")

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")

    class Config:
        """提供模型配置项，统一对象序列化与字段行为。"""
        json_schema_extra = {
            "example": {
                "id": "deb_001",
                "incident_id": "inc_001",
                "status": "analyzing",
                "current_phase": "analysis",
                "current_round": 1
            }
        }


class EvidenceItem(BaseModel):
    """
    证据项模型

    记录单个证据的信息：
    - 基本信息：证据ID、类型、描述
    - 来源信息：证据来源、引用位置
    - 强度评估：证据强度（strong/medium/weak）
    """
    evidence_id: Optional[str] = Field(None, description="证据ID")
    type: str = Field(..., description="证据类型")
    description: str = Field(..., description="证据描述")
    source: str = Field(..., description="证据来源")
    source_ref: Optional[str] = Field(None, description="证据引用（文件/日志定位）")
    location: Optional[str] = Field(None, description="代码位置")
    strength: str = Field(default="medium", description="证据强度: strong/medium/weak")


class FixRecommendation(BaseModel):
    """
    修复建议模型

    记录修复建议的详细信息：
    - 修复摘要
    - 修复步骤列表
    - 是否需要代码修改
    - 是否建议回滚
    - 测试要求
    """
    summary: str = Field(..., description="修复摘要")
    steps: List[Dict[str, Any]] = Field(default_factory=list, description="修复步骤")
    code_changes_required: bool = Field(default=False, description="是否需要代码修改")
    rollback_recommended: bool = Field(default=False, description="是否建议回滚")
    testing_requirements: List[str] = Field(default_factory=list, description="测试要求")


class ImpactAnalysis(BaseModel):
    """
    影响分析模型

    记录故障的影响范围：
    - 受影响服务列表
    - 受影响用户
    - 业务影响描述
    - 预计恢复时间
    """
    affected_services: List[str] = Field(default_factory=list, description="受影响服务")
    affected_users: Optional[str] = Field(None, description="受影响用户")
    business_impact: Optional[str] = Field(None, description="业务影响")
    estimated_recovery_time: Optional[str] = Field(None, description="预计恢复时间")


class RiskAssessment(BaseModel):
    """
    风险评估模型

    记录风险评估结果：
    - 风险等级（critical/high/medium/low）
    - 风险因素列表
    - 缓解建议
    """
    risk_level: str = Field(..., description="风险等级: critical/high/medium/low")
    risk_factors: List[str] = Field(default_factory=list, description="风险因素")
    mitigation_suggestions: List[str] = Field(default_factory=list, description="缓解建议")


class RootCauseCandidate(BaseModel):
    """
    根因候选模型

    记录一个候选根因的详细信息：
    - 排序和摘要
    - 来源 Agent 和置信度
    - 证据引用和覆盖
    - 冲突点和不确定性来源
    """
    rank: int = Field(..., ge=1, description="候选排序")
    summary: str = Field(..., description="候选根因摘要")
    source_agent: Optional[str] = Field(None, description="来源 Agent")
    confidence: float = Field(default=0.0, ge=0, le=1, description="候选置信度")
    confidence_interval: List[float] = Field(default_factory=list, description="置信区间 [low, high]")
    evidence_refs: List[str] = Field(default_factory=list, description="证据引用")
    evidence_coverage_count: int = Field(default=0, ge=0, description="覆盖证据数")
    conflict_points: List[str] = Field(default_factory=list, description="冲突点")
    uncertainty_sources: List[str] = Field(default_factory=list, description="不确定性来源")


class DebateResult(BaseModel):
    """
    辩论结果模型

    记录完整的辩论结果：
    - 会话信息：会话ID、故障ID
    - 最终结论：根因、置信度、是否通过跨源证据门禁
    - 根因候选列表
    - 证据链
    - 修复建议
    - 影响分析
    - 风险评估
    - 责任归属
    - 行动项和验证计划
    """
    session_id: str = Field(..., description="会话ID")
    incident_id: str = Field(..., description="故障ID")

    # 最终结论
    root_cause: str = Field(..., description="根因")
    root_cause_category: Optional[str] = Field(None, description="根因类别")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    cross_source_passed: bool = Field(default=False, description="是否通过跨源证据门禁")
    root_cause_candidates: List[RootCauseCandidate] = Field(default_factory=list, description="Top-K 根因候选")

    # 证据链
    evidence_chain: List[EvidenceItem] = Field(default_factory=list, description="证据链")

    # 修复建议
    fix_recommendation: Optional[FixRecommendation] = Field(None, description="修复建议")

    # 影响分析
    impact_analysis: Optional[ImpactAnalysis] = Field(None, description="影响分析")

    # 风险评估
    risk_assessment: Optional[RiskAssessment] = Field(None, description="风险评估")

    # 责任田
    responsible_team: Optional[str] = Field(None, description="责任团队")
    responsible_owner: Optional[str] = Field(None, description="责任人")

    # 行动项
    action_items: List[Dict[str, Any]] = Field(default_factory=list, description="行动项")

    # 验证计划
    verification_plan: List[Dict[str, Any]] = Field(default_factory=list, description="验证计划")
    
    # 异议记录
    dissenting_opinions: List[Dict[str, Any]] = Field(default_factory=list, description="异议意见")
    
    # 完整辩论历史
    debate_history: List[DebateRound] = Field(default_factory=list, description="辩论历史")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    
    class Config:
        """提供模型配置项，统一对象序列化与字段行为。"""
        json_schema_extra = {
            "example": {
                "session_id": "deb_001",
                "incident_id": "inc_001",
                "root_cause": "OrderService.createOrder 方法中订单对象未正确初始化",
                "root_cause_category": "空指针异常",
                "confidence": 0.92,
                "evidence_chain": [
                    {
                        "type": "log",
                        "description": "NullPointerException 在 OrderService.createOrder:156",
                        "source": "运行日志",
                        "location": "OrderService.java:156",
                        "strength": "strong"
                    }
                ],
                "risk_assessment": {
                    "risk_level": "high",
                    "risk_factors": ["影响订单创建功能", "可能导致数据不一致"],
                    "mitigation_suggestions": ["立即修复", "增加空值检查"]
                }
            }
        }
