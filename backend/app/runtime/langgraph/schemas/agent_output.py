"""
Pydantic schemas for structured agent output.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Type

from pydantic import BaseModel, Field


class AgentOutputSchema(BaseModel):
    """封装AgentOutputSchema相关数据结构或服务能力。"""
    chat_message: str = ""
    analysis: str = ""
    conclusion: str = ""
    evidence_chain: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class RootCauseSchema(BaseModel):
    """封装RootCauseSchema相关数据结构或服务能力。"""
    summary: str = ""
    category: str = ""
    confidence: float = 0.0


class EvidenceItemSchema(BaseModel):
    """封装EvidenceItemSchema相关数据结构或服务能力。"""
    type: Literal["log", "code", "domain", "metrics"] | str = "log"
    description: str = ""
    source: str = ""
    location: str = ""
    strength: Literal["strong", "medium", "weak"] | str = "medium"


class FixRecommendationSchema(BaseModel):
    """封装FixRecommendationSchema相关数据结构或服务能力。"""
    summary: str = ""
    steps: List[str] = Field(default_factory=list)
    code_changes_required: bool = False


class ImpactAnalysisSchema(BaseModel):
    """封装ImpactAnalysisSchema相关数据结构或服务能力。"""
    affected_services: List[str] = Field(default_factory=list)
    business_impact: str = ""
    affected_users: str = ""
    affected_functions: List[Dict[str, Any]] = Field(default_factory=list)
    affected_interfaces: List[Dict[str, Any]] = Field(default_factory=list)
    affected_user_scope: Dict[str, Any] = Field(default_factory=dict)
    unknowns: List[str] = Field(default_factory=list)


class ImpactAnalysisAgentOutputSchema(AgentOutputSchema):
    """ImpactAnalysisAgent 的结构化输出。"""
    impact_summary: ImpactAnalysisSchema = Field(default_factory=ImpactAnalysisSchema)
    follow_up_actions: List[str] = Field(default_factory=list)


class RiskAssessmentSchema(BaseModel):
    """封装RiskAssessmentSchema相关数据结构或服务能力。"""
    risk_level: Literal["critical", "high", "medium", "low"] | str = "medium"
    risk_factors: List[str] = Field(default_factory=list)


class FinalJudgmentSchema(BaseModel):
    """封装FinalJudgmentSchema相关数据结构或服务能力。"""
    root_cause: RootCauseSchema = Field(default_factory=RootCauseSchema)
    evidence_chain: List[EvidenceItemSchema] = Field(default_factory=list)
    fix_recommendation: FixRecommendationSchema = Field(default_factory=FixRecommendationSchema)
    impact_analysis: ImpactAnalysisSchema = Field(default_factory=ImpactAnalysisSchema)
    risk_assessment: RiskAssessmentSchema = Field(default_factory=RiskAssessmentSchema)


class DecisionRationaleSchema(BaseModel):
    """封装DecisionRationaleSchema相关数据结构或服务能力。"""
    key_factors: List[str] = Field(default_factory=list)
    reasoning: str = ""


class ResponsibleTeamSchema(BaseModel):
    """封装ResponsibleTeamSchema相关数据结构或服务能力。"""
    team: str = ""
    owner: str = ""


class JudgeOutputSchema(BaseModel):
    """封装JudgeOutputSchema相关数据结构或服务能力。"""
    chat_message: str = ""
    final_judgment: FinalJudgmentSchema = Field(default_factory=FinalJudgmentSchema)
    decision_rationale: DecisionRationaleSchema = Field(default_factory=DecisionRationaleSchema)
    action_items: List[str] = Field(default_factory=list)
    responsible_team: ResponsibleTeamSchema = Field(default_factory=ResponsibleTeamSchema)
    confidence: float = 0.0


class CommanderOutputSchema(BaseModel):
    """封装CommanderOutputSchema相关数据结构或服务能力。"""
    chat_message: str = ""
    analysis: str = ""
    conclusion: str = ""
    next_mode: str = ""
    next_agent: str = ""
    should_stop: bool = False
    stop_reason: str = ""
    commands: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_chain: List[str] = Field(default_factory=list)
    confidence: float = 0.0


def get_schema_for_agent(agent_name: str) -> Type[BaseModel]:
    """负责获取SchemaforAgent，并返回后续流程可直接消费的数据结果。"""
    if agent_name == "JudgeAgent":
        return JudgeOutputSchema
    if agent_name == "ProblemAnalysisAgent":
        return CommanderOutputSchema
    if agent_name == "ImpactAnalysisAgent":
        return ImpactAnalysisAgentOutputSchema
    return AgentOutputSchema


__all__ = [
    "AgentOutputSchema",
    "JudgeOutputSchema",
    "CommanderOutputSchema",
    "ImpactAnalysisAgentOutputSchema",
    "RootCauseSchema",
    "EvidenceItemSchema",
    "FixRecommendationSchema",
    "ImpactAnalysisSchema",
    "RiskAssessmentSchema",
    "FinalJudgmentSchema",
    "DecisionRationaleSchema",
    "ResponsibleTeamSchema",
    "get_schema_for_agent",
]
