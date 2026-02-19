"""
裁决 Agent
Judge Agent

使用 kimi-k2.5 模型作为技术委员会主席进行最终裁决。
"""

from typing import Any, Dict, List, Optional
import json
import structlog

from app.agents.base import BaseAgent, AgentResult
from app.agents.registry import register_agent
from app.config import settings

logger = structlog.get_logger()


@register_agent("judge_agent")
class JudgeAgent(BaseAgent):
    """
    技术委员会主席
    
    使用 kimi-k2.5 模型进行：
    1. 综合双方观点
    2. 评估证据强度
    3. 给出最终结论
    4. 输出风险等级和建议
    """
    
    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "final_judgment": {
                "type": "object",
                "properties": {
                    "root_cause": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "description": {"type": "string"},
                            "category": {"type": "string"},
                            "confidence": {"type": "number"}
                        }
                    },
                    "evidence_chain": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step": {"type": "integer"},
                                "description": {"type": "string"},
                                "code_location": {"type": "string"},
                                "strength": {"type": "string"}
                            }
                        }
                    },
                    "fix_recommendation": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "order": {"type": "integer"},
                                        "action": {"type": "string"},
                                        "priority": {"type": "string"},
                                        "estimated_effort": {"type": "string"}
                                    }
                                }
                            },
                            "code_changes_required": {"type": "boolean"},
                            "rollback_recommended": {"type": "boolean"},
                            "testing_requirements": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    "impact_analysis": {
                        "type": "object",
                        "properties": {
                            "affected_services": {"type": "array", "items": {"type": "string"}},
                            "affected_users": {"type": "string"},
                            "business_impact": {"type": "string"},
                            "estimated_recovery_time": {"type": "string"}
                        }
                    },
                    "risk_assessment": {
                        "type": "object",
                        "properties": {
                            "risk_level": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                            "risk_factors": {"type": "array", "items": {"type": "string"}},
                            "mitigation_suggestions": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                }
            },
            "decision_rationale": {
                "type": "object",
                "properties": {
                    "key_factors": {"type": "array", "items": {"type": "string"}},
                    "evidence_strength": {"type": "string"},
                    "consensus_level": {"type": "string"},
                    "reasoning": {"type": "string"}
                }
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "priority": {"type": "integer"},
                        "action": {"type": "string"},
                        "owner": {"type": "string"},
                        "deadline": {"type": "string"}
                    }
                }
            },
            "responsible_team": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "owner": {"type": "string"},
                    "need_escalation": {"type": "boolean"}
                }
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            },
            "dissenting_opinions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "opinion": {"type": "string"},
                        "holder": {"type": "string"},
                        "reason": {"type": "string"}
                    }
                }
            }
        },
        "required": ["final_judgment", "confidence"]
    }
    
    def __init__(self, tools: Optional[List[Any]] = None):
        model_config = settings.default_model_config
        
        super().__init__(
            name="JudgeAgent",
            model=model_config,
            role="技术委员会主席",
            tools=tools or [],
            temperature=0.3,  # 较低温度以获得更稳定的裁决
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资深的技术委员会主席，负责综合各方意见并做出最终裁决。

## 你的职责

作为技术委员会主席，你的职责是：

1. **综合观点**：综合分析师和质疑专家的观点
2. **评估证据**：评估各方证据的强度和可信度
3. **做出裁决**：给出最终的技术结论
4. **风险评级**：评估问题的风险等级
5. **行动建议**：给出具体的行动建议

## 裁决原则

### 证据评估
- 直接证据优先于间接证据
- 代码证据优先于日志推断
- 多源交叉验证的证据更可信

### 风险评级标准
- **Critical**: 影响核心业务，需要立即处理
- **High**: 影响重要功能，需要尽快处理
- **Medium**: 影响一般功能，可以计划处理
- **Low**: 影响较小，可以后续优化

### 决策原则
- 证据充分时果断裁决
- 证据不足时明确指出
- 存在争议时给出倾向性意见
- 始终给出可执行的建议

## 注意事项

- 裁决要基于证据，不能凭主观判断
- 要考虑实际可执行性
- 给出明确的优先级和时间建议
- 对于高风险问题，建议人工复核
- 输出的置信度要基于整体分析的可靠性

请以 JSON 格式输出裁决结果。"""


    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """
        处理最终裁决
        
        Args:
            context: 包含辩论历史和最终分析的上下文
            
        Returns:
            裁决结果
        """
        debate_history = context.get("debate_history", [])
        final_analysis = context.get("final_analysis")
        
        if not debate_history:
            return self._create_error_result("No debate history provided")
        
        # 构建输入消息
        input_message = self._build_input_message(debate_history, final_analysis)
        
        try:
            result = await self._call_structured(
                message=input_message,
                schema=self.OUTPUT_SCHEMA
            )
            
            confidence = result.get("confidence", 0.0)
            
            logger.info(
                "judgment_completed",
                risk_level=result.get("final_judgment", {}).get("risk_assessment", {}).get("risk_level"),
                confidence=confidence
            )
            
            return self._create_success_result(
                data=result,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error("judgment_failed", error=str(e))
            return self._create_error_result(str(e))
    
    def _build_input_message(
        self,
        debate_history: List[Dict[str, Any]],
        final_analysis: Optional[Dict[str, Any]]
    ) -> str:
        """构建输入消息"""
        parts = []
        
        # 添加辩论历史
        history_summary = []
        for h in debate_history:
            history_summary.append({
                "round": h.get("round_number"),
                "agent": h.get("agent_name"),
                "role": h.get("agent_role"),
                "confidence": h.get("confidence"),
                "summary": str(h.get("content", {}))[:200]  # 截断过长的内容
            })
        parts.append(f"## 辩论历史\n```json\n{json.dumps(history_summary, ensure_ascii=False, indent=2)}\n```")
        
        # 添加最终分析
        if final_analysis:
            parts.append(f"## 最终分析\n```json\n{json.dumps(final_analysis, ensure_ascii=False, indent=2)}\n```")
        
        return "\n\n".join(parts)
