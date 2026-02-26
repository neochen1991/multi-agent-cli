"""
反驳 Agent
Rebuttal Agent

使用 glm-5 模型进行技术反驳和修正。
"""

from typing import Any, Dict, List, Optional
import json
import structlog

from app.agents.base import BaseAgent, AgentResult
from app.agents.registry import register_agent
from app.config import settings

logger = structlog.get_logger()


@register_agent("rebuttal_agent")
class RebuttalAgent(BaseAgent):
    """
    技术反驳专家
    
    使用 glm-5 模型进行：
    1. 回应质疑意见
    2. 修正推理过程
    3. 补充证据
    4. 更新置信度
    """
    
    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "response_summary": {"type": "string"},
            "point_by_point_response": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "critique_point": {"type": "string"},
                        "response_type": {"type": "string", "enum": ["accept", "partial_accept", "reject"]},
                        "response": {"type": "string"},
                        "supporting_evidence": {"type": "array", "items": {"type": "string"}},
                        "revision": {"type": "string"}
                    }
                }
            },
            "revised_analysis": {
                "type": "object",
                "properties": {
                    "root_cause_hypothesis": {"type": "string"},
                    "evidence_chain_updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step": {"type": "integer"},
                                "action": {"type": "string"},
                                "content": {"type": "string"}
                            }
                        }
                    },
                    "fix_suggestion_updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "aspect": {"type": "string"},
                                "action": {"type": "string"},
                                "content": {"type": "string"}
                            }
                        }
                    }
                }
            },
            "unaddressed_critiques": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "point": {"type": "string"},
                        "reason": {"type": "string"},
                        "need_more_info": {"type": "boolean"}
                    }
                }
            },
            "consensus_reached": {"type": "boolean"},
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            },
            "confidence_change": {
                "type": "object",
                "properties": {
                    "previous": {"type": "number"},
                    "current": {"type": "number"},
                    "reason": {"type": "string"}
                }
            }
        },
        "required": ["response_summary", "consensus_reached", "confidence"]
    }
    
    def __init__(self, tools: Optional[List[Any]] = None):
        model_config = settings.default_model_config
        
        super().__init__(
            name="RebuttalAgent",
            model=model_config,
            role="技术反驳专家",
            tools=tools or [],
            temperature=0.4,
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资深的软件工程师，擅长技术辩论和问题分析。

## 你的职责

作为技术反驳专家，你的职责是：

1. **回应质疑**：对质疑意见进行技术性回应
2. **修正推理**：根据质疑修正不完善的分析
3. **补充证据**：提供更多支持性证据
4. **承认不足**：坦诚承认分析中的不足
5. **更新结论**：根据讨论更新结论和置信度

## 回应策略

### 对于有效的质疑
- 坦诚承认不足
- 提供修正后的分析
- 更新置信度

### 对于部分有效的质疑
- 承认部分合理性
- 提供补充说明
- 调整相关结论

### 对于无效的质疑
- 提供技术性反驳
- 引用证据支持原分析
- 解释为什么质疑不成立

## 注意事项

- 保持技术客观性，不要情绪化
- 承认不足是专业表现，不是软弱
- 修正后的分析应该更加完善
- 如果质疑确实有效，应该调整结论
- 输出的置信度要基于修正后的分析质量

请以 JSON 格式输出反驳结果。"""


    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """
        处理反驳分析
        
        Args:
            context: 包含质疑意见、之前分析和辩论历史的上下文
            
        Returns:
            反驳结果
        """
        criticism = context.get("criticism")
        previous_analysis = context.get("previous_analysis")
        debate_history = context.get("debate_history", [])
        
        if not criticism or not previous_analysis:
            return self._create_error_result("No criticism or previous analysis provided")
        
        # 构建输入消息
        input_message = self._build_input_message(criticism, previous_analysis, debate_history)
        
        try:
            result = await self._call_structured(
                message=input_message,
                schema=self.OUTPUT_SCHEMA
            )
            
            confidence = result.get("confidence", 0.0)
            
            logger.info(
                "rebuttal_completed",
                consensus_reached=result.get("consensus_reached"),
                confidence=confidence
            )
            
            return self._create_success_result(
                data=result,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error("rebuttal_failed", error=str(e))
            return self._create_error_result(str(e))
    
    def _build_input_message(
        self,
        criticism: Dict[str, Any],
        previous_analysis: Dict[str, Any],
        debate_history: List[Dict[str, Any]]
    ) -> str:
        """构建输入消息"""
        parts = []
        
        # 添加之前的分析
        parts.append(f"## 之前的分析\n```json\n{json.dumps(previous_analysis, ensure_ascii=False, indent=2)}\n```")
        
        # 添加质疑意见
        parts.append(f"## 质疑意见\n```json\n{json.dumps(criticism, ensure_ascii=False, indent=2)}\n```")
        
        # 添加辩论历史摘要
        if debate_history:
            history_summary = []
            for h in debate_history[-4:]:
                history_summary.append({
                    "agent": h.get("agent_name"),
                    "round": h.get("round_number"),
                    "confidence": h.get("confidence")
                })
            parts.append(f"## 辩论历史摘要\n```json\n{json.dumps(history_summary, ensure_ascii=False, indent=2)}\n```")
        
        return "\n\n".join(parts)
