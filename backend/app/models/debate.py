"""
辩论会话模型
Debate Models
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DebateStatus(str, Enum):
    """辩论状态"""
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
    """辩论阶段"""
    ANALYSIS = "analysis"        # 独立分析
    CRITIQUE = "critique"        # 交叉质疑
    REBUTTAL = "rebuttal"        # 反驳修正
    JUDGMENT = "judgment"        # 最终裁决


class AgentRole(str, Enum):
    """Agent 角色"""
    LOG_ANALYST = "log_analyst"           # 日志分析专家
    DOMAIN_EXPERT = "domain_expert"       # 领域映射专家
    CODE_EXPERT = "code_expert"           # 代码分析专家
    CRITIC = "critic"                     # 架构质疑专家
    REBUTTAL = "rebuttal"                 # 技术反驳专家
    JUDGE = "judge"                       # 技术委员会主席


class DebateRound(BaseModel):
    """辩论轮次"""
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
        json_schema_extra = {
            "example": {
                "round_number": 1,
                "phase": "analysis",
                "agent_name": "CodeAgent",
                "agent_role": "code_expert",
                "model": {"name": "kimi-k2.5"},
                "input_message": "分析以下日志...",
                "output_content": {"root_cause": "...", "evidence": [...]},
                "confidence": 0.85
            }
        }


class DebateSession(BaseModel):
    """辩论会话"""
    id: str = Field(..., description="会话ID")
    incident_id: str = Field(..., description="关联故障ID")
    status: DebateStatus = Field(default=DebateStatus.PENDING, description="状态")
    current_phase: Optional[DebatePhase] = Field(None, description="当前阶段")
    current_round: int = Field(default=0, description="当前轮次")
    
    # 辩论历史
    rounds: List[DebateRound] = Field(default_factory=list, description="辩论轮次")
    
    # 上下文
    context: Dict[str, Any] = Field(default_factory=dict, description="上下文数据")
    
    # LLM 会话（兼容历史字段名）
    llm_session_id: Optional[str] = Field(None, description="LLM 会话ID")
    opencode_session_id: Optional[str] = Field(None, description="历史兼容字段（已废弃）")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    
    class Config:
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
    """证据项"""
    type: str = Field(..., description="证据类型")
    description: str = Field(..., description="证据描述")
    source: str = Field(..., description="证据来源")
    location: Optional[str] = Field(None, description="代码位置")
    strength: str = Field(default="medium", description="证据强度: strong/medium/weak")


class FixRecommendation(BaseModel):
    """修复建议"""
    summary: str = Field(..., description="修复摘要")
    steps: List[Dict[str, Any]] = Field(default_factory=list, description="修复步骤")
    code_changes_required: bool = Field(default=False, description="是否需要代码修改")
    rollback_recommended: bool = Field(default=False, description="是否建议回滚")
    testing_requirements: List[str] = Field(default_factory=list, description="测试要求")


class ImpactAnalysis(BaseModel):
    """影响分析"""
    affected_services: List[str] = Field(default_factory=list, description="受影响服务")
    affected_users: Optional[str] = Field(None, description="受影响用户")
    business_impact: Optional[str] = Field(None, description="业务影响")
    estimated_recovery_time: Optional[str] = Field(None, description="预计恢复时间")


class RiskAssessment(BaseModel):
    """风险评估"""
    risk_level: str = Field(..., description="风险等级: critical/high/medium/low")
    risk_factors: List[str] = Field(default_factory=list, description="风险因素")
    mitigation_suggestions: List[str] = Field(default_factory=list, description="缓解建议")


class DebateResult(BaseModel):
    """辩论结果"""
    session_id: str = Field(..., description="会话ID")
    incident_id: str = Field(..., description="故障ID")
    
    # 最终结论
    root_cause: str = Field(..., description="根因")
    root_cause_category: Optional[str] = Field(None, description="根因类别")
    confidence: float = Field(..., ge=0, le=1, description="置信度")
    
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
    
    # 异议记录
    dissenting_opinions: List[Dict[str, Any]] = Field(default_factory=list, description="异议意见")
    
    # 完整辩论历史
    debate_history: List[DebateRound] = Field(default_factory=list, description="辩论历史")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    
    class Config:
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
