"""
领域映射 Agent
Domain Mapping Agent

使用 glm-5 模型进行领域映射和 DDD 分析。
"""

from typing import Any, Dict, List, Optional
import json
import structlog

from app.agents.base import BaseAgent, AgentResult
from app.agents.registry import register_agent
from app.config import settings

logger = structlog.get_logger()


@register_agent("domain_agent")
class DomainAgent(BaseAgent):
    """
    领域映射专家
    
    使用 glm-5 模型进行：
    1. 将运行态异常映射到领域模型
    2. 识别涉及的聚合根和限界上下文
    3. 分析跨域影响
    4. 定位责任田
    """
    
    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "bounded_context": {"type": "string"}
                }
            },
            "aggregate": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "aggregate_root": {"type": "string"},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "value_objects": {"type": "array", "items": {"type": "string"}}
                }
            },
            "affected_entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "role": {"type": "string"}
                    }
                }
            },
            "cross_domain_impact": {
                "type": "object",
                "properties": {
                    "has_cross_domain": {"type": "boolean"},
                    "affected_domains": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "domain": {"type": "string"},
                                "impact_type": {"type": "string"},
                                "impact_description": {"type": "string"}
                            }
                        }
                    }
                }
            },
            "responsibility": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "owner": {"type": "string"}
                }
            },
            "ddd_violations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "description": {"type": "string"},
                        "severity": {"type": "string"}
                    }
                }
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string"}
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            }
        },
        "required": ["domain", "confidence"]
    }
    
    def __init__(self, tools: Optional[List[Any]] = None):
        model_config = settings.default_model_config
        
        super().__init__(
            name="DomainAgent",
            model=model_config,
            role="领域映射专家",
            tools=tools or [],
            temperature=0.4,
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位 DDD（领域驱动设计）专家，精通领域建模和微服务架构。

## 你的职责

1. **领域映射**：将运行态异常映射到领域模型
2. **聚合识别**：识别涉及的聚合根和聚合边界
3. **上下文分析**：分析限界上下文和上下文映射
4. **跨域影响**：分析跨域调用和影响范围
5. **责任定位**：定位责任田和负责人

## DDD 原则检查

在分析时，请检查以下 DDD 原则是否被违反：

1. **聚合边界**：聚合是否过大或过小
2. **聚合根唯一入口**：是否通过聚合根访问聚合内实体
3. **不变性约束**：聚合内不变性约束是否被维护
4. **限界上下文**：上下文边界是否清晰
5. **上下文映射**：上下文间的关系是否合理
6. **领域服务**：领域服务是否正确放置

## 注意事项

- 关注业务领域而非技术实现
- 识别核心域、支撑域和通用域
- 注意聚合间的最终一致性
- 分析事件驱动的影响
- 输出的置信度要基于领域理解的准确程度

请以 JSON 格式输出分析结果。"""


    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """
        处理领域映射
        
        Args:
            context: 包含运行态资产、设计态资产和日志分析结果的上下文
            
        Returns:
            领域映射结果
        """
        design_asset = context.get("design_asset", {})
        log_analysis = context.get("log_analysis")
        runtime_asset = context.get("runtime_asset", {})
        
        if not design_asset and not runtime_asset:
            return self._create_error_result("No design asset or runtime asset provided")
        
        # 构建输入消息
        input_message = self._build_input_message(design_asset, log_analysis, runtime_asset)
        
        try:
            result = await self._call_structured(
                message=input_message,
                schema=self.OUTPUT_SCHEMA
            )
            
            confidence = result.get("confidence", 0.0)
            
            logger.info(
                "domain_mapping_completed",
                domain=result.get("domain", {}).get("name"),
                confidence=confidence
            )
            
            return self._create_success_result(
                data=result,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error("domain_mapping_failed", error=str(e))
            return self._create_error_result(str(e))
    
    def _build_input_message(
        self,
        design_asset: Dict[str, Any],
        log_analysis: Optional[AgentResult],
        runtime_asset: Dict[str, Any]
    ) -> str:
        """构建输入消息"""
        parts = []
        
        # 添加领域模型
        domain = design_asset.get("domain")
        if domain:
            parts.append(f"## 领域模型\n```json\n{json.dumps(domain, ensure_ascii=False, indent=2)}\n```")
        
        # 添加聚合设计
        aggregates = design_asset.get("aggregates", [])
        if aggregates:
            parts.append(f"## 聚合设计\n```json\n{json.dumps(aggregates, ensure_ascii=False, indent=2)}\n```")
        
        # 添加接口设计
        interfaces = design_asset.get("interfaces", [])
        if interfaces:
            parts.append(f"## 接口设计\n```json\n{json.dumps(interfaces[:5], ensure_ascii=False, indent=2)}\n```")
        
        # 添加日志分析结果
        if log_analysis and log_analysis.success:
            parts.append(f"## 日志分析结果\n```json\n{json.dumps(log_analysis.data, ensure_ascii=False, indent=2)}\n```")
        
        # 添加来源信息
        source = runtime_asset.get("source", {})
        if source:
            parts.append(f"## 来源信息\n服务名称: {source.get('serviceName', 'unknown')}")
        
        return "\n\n".join(parts)
