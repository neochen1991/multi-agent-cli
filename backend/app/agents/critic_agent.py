"""
质疑 Agent
Critic Agent

使用 kimi-k2.5 模型进行架构质疑和交叉验证。
"""

from typing import Any, Dict, List, Optional
import json
import structlog

from app.agents.base import BaseAgent, AgentResult
from app.agents.registry import register_agent
from app.config import settings

logger = structlog.get_logger()


@register_agent("critic_agent")
class CriticAgent(BaseAgent):
    """
    架构质疑专家
    
    使用 kimi-k2.5 模型进行：
    1. 检查是否违反 DDD 原则
    2. 验证证据链的完整性
    3. 质疑分析中的漏洞
    4. 提出替代假设
    """
    
    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "overall_assessment": {
                "type": "object",
                "properties": {
                    "agreement_level": {"type": "string", "enum": ["full", "partial", "disagree"]},
                    "confidence_in_analysis": {"type": "number"},
                    "summary": {"type": "string"}
                }
            },
            "critiques": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                        "point": {"type": "string"},
                        "reason": {"type": "string"},
                        "evidence": {"type": "string"},
                        "suggestion": {"type": "string"}
                    }
                }
            },
            "alternative_hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "hypothesis": {"type": "string"},
                        "probability": {"type": "number"},
                        "supporting_evidence": {"type": "array", "items": {"type": "string"}},
                        "how_to_verify": {"type": "string"}
                    }
                }
            },
            "missing_analyses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "aspect": {"type": "string"},
                        "importance": {"type": "string"},
                        "suggestion": {"type": "string"}
                    }
                }
            },
            "risk_assessment": {
                "type": "object",
                "properties": {
                    "fix_risks": {"type": "array", "items": {"type": "string"}},
                    "rollback_complexity": {"type": "string"},
                    "testing_requirements": {"type": "array", "items": {"type": "string"}}
                }
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            }
        },
        "required": ["overall_assessment", "confidence"]
    }
    
    def __init__(self, tools: Optional[List[Any]] = None):
        model_config = settings.default_model_config
        
        super().__init__(
            name="CriticAgent",
            model=model_config,
            role="架构质疑专家",
            tools=tools or [],
            temperature=0.5,  # 较高温度以获得更多质疑角度
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资深的软件架构师和代码审查专家，擅长发现问题和提出质疑。

## 你的职责

作为技术委员会的质疑专家，你的职责是：

1. **DDD 原则检查**：检查分析是否违反 DDD 设计原则
2. **证据链验证**：验证证据链是否完整、逻辑是否通顺
3. **漏洞发现**：发现分析中的漏洞和薄弱环节
4. **替代假设**：提出可能的替代根因假设
5. **风险评估**：评估修复方案的风险

## 质疑角度

请从以下角度进行质疑：

### 1. DDD 架构角度
- 聚合边界是否合理？
- 是否违反聚合根唯一入口原则？
- 跨聚合调用是否正确？
- 领域服务是否正确放置？

### 2. 代码质量角度
- 是否有遗漏的代码路径？
- 并发场景是否考虑完整？
- 异常处理是否完善？
- 边界条件是否处理？

### 3. 证据链角度
- 证据是否充分？
- 推理是否逻辑严密？
- 是否有跳跃性结论？
- 是否忽略了关键信息？

### 4. 修复方案角度
- 修复方案是否可行？
- 是否会引入新问题？
- 是否考虑了向后兼容？
- 测试覆盖是否充分？

## 注意事项

- 质疑要有理有据，不是为了质疑而质疑
- 关注关键问题，不要纠结于细枝末节
- 提出的替代假设要有一定可能性
- 改进建议要具体可行
- 输出的置信度要基于质疑的合理性

请以 JSON 格式输出质疑结果。"""


    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """
        处理质疑分析
        
        Args:
            context: 包含之前分析结果和辩论历史的上下文
            
        Returns:
            质疑结果
        """
        previous_analysis = context.get("previous_analysis")
        debate_history = context.get("debate_history", [])
        
        if not previous_analysis:
            return self._create_error_result("No previous analysis to critique")
        
        # 构建输入消息
        input_message = self._build_input_message(previous_analysis, debate_history)
        
        try:
            result = await self._call_structured(
                message=input_message,
                schema=self.OUTPUT_SCHEMA
            )
            
            confidence = result.get("confidence", 0.0)
            
            logger.info(
                "critique_completed",
                agreement_level=result.get("overall_assessment", {}).get("agreement_level"),
                critiques_count=len(result.get("critiques", [])),
                confidence=confidence
            )
            
            return self._create_success_result(
                data=result,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error("critique_failed", error=str(e))
            return self._create_error_result(str(e))
    
    def _build_input_message(
        self,
        previous_analysis: Dict[str, Any],
        debate_history: List[Dict[str, Any]]
    ) -> str:
        """构建输入消息"""
        parts = []
        
        # 添加待质疑的分析
        parts.append(f"## 待质疑的分析\n```json\n{json.dumps(previous_analysis, ensure_ascii=False, indent=2)}\n```")
        
        # 添加辩论历史摘要
        if debate_history:
            history_summary = []
            for h in debate_history[-6:]:  # 只取最近6轮
                history_summary.append({
                    "agent": h.get("agent_name"),
                    "round": h.get("round_number"),
                    "confidence": h.get("confidence")
                })
            parts.append(f"## 辩论历史摘要\n```json\n{json.dumps(history_summary, ensure_ascii=False, indent=2)}\n```")
        
        return "\n\n".join(parts)
