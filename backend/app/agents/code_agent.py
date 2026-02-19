"""
代码分析 Agent
Code Analysis Agent

使用 kimi-k2.5 模型进行代码分析和根因定位。
"""

from typing import Any, Dict, List, Optional
import json
import structlog

from app.agents.base import BaseAgent, AgentResult
from app.agents.registry import register_agent
from app.config import settings

logger = structlog.get_logger()


@register_agent("code_agent")
class CodeAgent(BaseAgent):
    """
    代码分析专家
    
    使用 kimi-k2.5 模型进行：
    1. 分析代码层面的根因
    2. 构建证据链
    3. 定位问题代码
    4. 提出修复建议
    """
    
    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "root_cause_hypothesis": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"}
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
                        "snippet": {"type": "string"},
                        "explanation": {"type": "string"}
                    }
                }
            },
            "affected_files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "change_type": {"type": "string"},
                        "priority": {"type": "string"},
                        "reason": {"type": "string"}
                    }
                }
            },
            "fix_suggestion": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "approach": {"type": "string"},
                    "code_changes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "change_type": {"type": "string"},
                                "original_code": {"type": "string"},
                                "suggested_code": {"type": "string"},
                                "explanation": {"type": "string"}
                            }
                        }
                    },
                    "testing_suggestions": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "risks": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                }
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            },
            "alternative_hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "hypothesis": {"type": "string"},
                        "probability": {"type": "number"},
                        "reason": {"type": "string"}
                    }
                }
            }
        },
        "required": ["root_cause_hypothesis", "confidence"]
    }
    
    def __init__(self, tools: Optional[List[Any]] = None):
        model_config = settings.default_model_config
        
        super().__init__(
            name="CodeAgent",
            model=model_config,
            role="代码分析专家",
            tools=tools or [],
            temperature=0.3,
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资深的代码分析专家，精通 Java Spring 和 DDD 架构。

## 你的职责

1. **根因分析**：分析代码层面的根本原因
2. **证据链构建**：构建从异常到根因的证据链
3. **代码定位**：精确定位问题代码位置
4. **修复建议**：提出可行的修复方案

## 代码分析要点

在分析代码时，请关注：

1. **空指针检查**：是否有未检查的空引用
2. **并发安全**：是否有线程安全问题
3. **事务边界**：事务是否正确配置
4. **异常处理**：异常是否被正确处理
5. **资源管理**：资源是否被正确关闭
6. **数据验证**：输入数据是否被验证
7. **边界条件**：边界条件是否被处理
8. **性能问题**：是否存在性能瓶颈

## 注意事项

- 关注业务逻辑而非框架代码
- 分析时考虑 DDD 架构约束
- 修复建议要具体可执行
- 考虑修复可能带来的副作用
- 输出的置信度要基于证据的充分程度

请以 JSON 格式输出分析结果。"""


    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """
        处理代码分析
        
        Args:
            context: 包含开发态资产、日志分析结果和领域映射结果的上下文
            
        Returns:
            代码分析结果
        """
        development_asset = context.get("development_asset", {})
        log_analysis = context.get("log_analysis")
        domain_mapping = context.get("domain_mapping")
        
        if not development_asset and not log_analysis:
            return self._create_error_result("No development asset or log analysis provided")
        
        # 构建输入消息
        input_message = self._build_input_message(development_asset, log_analysis, domain_mapping)
        
        try:
            result = await self._call_structured(
                message=input_message,
                schema=self.OUTPUT_SCHEMA
            )
            
            confidence = result.get("confidence", 0.0)
            
            logger.info(
                "code_analysis_completed",
                root_cause=result.get("root_cause_hypothesis", {}).get("summary"),
                confidence=confidence
            )
            
            return self._create_success_result(
                data=result,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error("code_analysis_failed", error=str(e))
            return self._create_error_result(str(e))
    
    def _build_input_message(
        self,
        development_asset: Dict[str, Any],
        log_analysis: Optional[AgentResult],
        domain_mapping: Optional[AgentResult]
    ) -> str:
        """构建输入消息"""
        parts = []
        
        # 添加仓库信息
        repository = development_asset.get("repository")
        if repository:
            parts.append(f"## Git 仓库\n```json\n{json.dumps(repository, ensure_ascii=False, indent=2)}\n```")
        
        # 添加聚合根
        aggregate_roots = development_asset.get("aggregateRoots", [])
        if aggregate_roots:
            parts.append(f"## 聚合根\n```json\n{json.dumps(aggregate_roots[:5], ensure_ascii=False, indent=2)}\n```")
        
        # 添加 Controller
        controllers = development_asset.get("controllers", [])
        if controllers:
            parts.append(f"## Controllers\n```json\n{json.dumps(controllers[:5], ensure_ascii=False, indent=2)}\n```")
        
        # 添加日志分析结果
        if log_analysis and log_analysis.success:
            parts.append(f"## 日志分析结果\n```json\n{json.dumps(log_analysis.data, ensure_ascii=False, indent=2)}\n```")
        
        # 添加领域映射结果
        if domain_mapping and domain_mapping.success:
            parts.append(f"## 领域映射结果\n```json\n{json.dumps(domain_mapping.data, ensure_ascii=False, indent=2)}\n```")
        
        return "\n\n".join(parts)
