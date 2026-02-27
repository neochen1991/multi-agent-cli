"""
Pydantic schemas for structured agent output.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Type

from pydantic import BaseModel, Field


class AgentOutputSchema(BaseModel):
    chat_message: str = ""
    analysis: str = ""
    conclusion: str = ""
    evidence_chain: List[str] = Field(default_factory=list)
    confidence: float = 0.0


class RootCauseSchema(BaseModel):
    summary: str = ""
    category: str = ""
    confidence: float = 0.0


class EvidenceItemSchema(BaseModel):
    type: Literal["log", "code", "domain", "metrics"] | str = "log"
    description: str = ""
    source: str = ""
    location: str = ""
    strength: Literal["strong", "medium", "weak"] | str = "medium"


class FixRecommendationSchema(BaseModel):
    summary: str = ""
    steps: List[str] = Field(default_factory=list)
    code_changes_required: bool = False


class ImpactAnalysisSchema(BaseModel):
    affected_services: List[str] = Field(default_factory=list)
    business_impact: str = ""


class RiskAssessmentSchema(BaseModel):
    risk_level: Literal["critical", "high", "medium", "low"] | str = "medium"
    risk_factors: List[str] = Field(default_factory=list)


class FinalJudgmentSchema(BaseModel):
    root_cause: RootCauseSchema = Field(default_factory=RootCauseSchema)
    evidence_chain: List[EvidenceItemSchema] = Field(default_factory=list)
    fix_recommendation: FixRecommendationSchema = Field(default_factory=FixRecommendationSchema)
    impact_analysis: ImpactAnalysisSchema = Field(default_factory=ImpactAnalysisSchema)
    risk_assessment: RiskAssessmentSchema = Field(default_factory=RiskAssessmentSchema)


class DecisionRationaleSchema(BaseModel):
    key_factors: List[str] = Field(default_factory=list)
    reasoning: str = ""


class ResponsibleTeamSchema(BaseModel):
    team: str = ""
    owner: str = ""


class JudgeOutputSchema(BaseModel):
    chat_message: str = ""
    final_judgment: FinalJudgmentSchema = Field(default_factory=FinalJudgmentSchema)
    decision_rationale: DecisionRationaleSchema = Field(default_factory=DecisionRationaleSchema)
    action_items: List[str] = Field(default_factory=list)
    responsible_team: ResponsibleTeamSchema = Field(default_factory=ResponsibleTeamSchema)
    confidence: float = 0.0


class CommanderOutputSchema(BaseModel):
    chat_message: str = ""
    analysis: str = ""
    conclusion: str = ""
    next_mode: str = ""
    next_agent: str = ""
    should_stop: bool = False
    stop_reason: str = ""
    commands: List[Dict[str, str]] = Field(default_factory=list)
    evidence_chain: List[str] = Field(default_factory=list)
    confidence: float = 0.0


def get_schema_for_agent(agent_name: str) -> Type[BaseModel]:
    if agent_name == "JudgeAgent":
        return JudgeOutputSchema
    if agent_name == "ProblemAnalysisAgent":
        return CommanderOutputSchema
    return AgentOutputSchema


__all__ = [
    "AgentOutputSchema",
    "JudgeOutputSchema",
    "CommanderOutputSchema",
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

