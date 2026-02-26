"""
日志分析 Agent
Log Analysis Agent

使用 glm-5 模型进行日志分析和异常提取。
"""

from typing import Any, Dict, List, Optional
import json
import structlog

from app.agents.base import BaseAgent, AgentResult
from app.agents.registry import register_agent
from app.config import settings

logger = structlog.get_logger()


@register_agent("log_agent")
class LogAgent(BaseAgent):
    """
    日志分析专家
    
    使用 glm-5 模型进行：
    1. 解析和分析运行态日志
    2. 提取异常栈、URL、类路径等关键信息
    3. 识别异常模式和潜在问题
    4. 关联 JVM 监控指标
    """
    
    # 输出格式的 JSON Schema
    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "exception_type": {"type": "string", "description": "异常类型"},
            "exception_message": {"type": "string", "description": "异常消息"},
            "stack_trace_summary": {"type": "string", "description": "堆栈摘要"},
            "suspected_components": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可疑组件列表"
            },
            "related_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "相关URL列表"
            },
            "slow_queries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                        "execution_time_ms": {"type": "number"},
                        "table": {"type": "string"}
                    }
                }
            },
            "jvm_anomalies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "JVM异常指标列表"
            },
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关键发现列表"
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "置信度"
            }
        },
        "required": ["exception_type", "key_findings", "confidence"]
    }
    
    def __init__(self, tools: Optional[List[Any]] = None):
        model_config = settings.default_model_config
        
        super().__init__(
            name="LogAgent",
            model=model_config,
            role="日志分析专家",
            tools=tools or [],
            temperature=0.3,  # 较低温度以获得更确定的分析结果
        )
    
    def _build_system_prompt(self) -> str:
        return """你是一位资深的 SRE 日志分析专家，精通 Java 应用日志分析和故障诊断。

## 你的职责

1. **日志解析**：解析各种格式的应用日志，提取关键信息
2. **异常识别**：识别异常类型、异常消息和堆栈跟踪
3. **模式分析**：发现日志中的异常模式和潜在问题
4. **关联分析**：关联 JVM 监控指标、Trace 信息和慢 SQL

## 分析步骤

1. 识别异常类型和消息
2. 解析堆栈跟踪，定位关键代码位置
3. 分析线程状态和并发问题
4. 关联 Trace 信息，追踪调用链
5. 识别慢 SQL 和数据库问题
6. 分析 JVM 指标，发现内存、GC 等问题

## 注意事项

- 重点关注业务异常而非框架异常
- 注意区分根因异常和包装异常
- 分析堆栈时关注应用代码而非框架代码
- 结合 JVM 指标判断是否存在资源问题
- 输出的置信度要基于证据的充分程度

请以 JSON 格式输出分析结果。"""


    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """
        处理日志分析
        
        Args:
            context: 包含运行态资产的上下文
            
        Returns:
            分析结果
        """
        runtime_asset = context.get("runtime_asset", {})
        
        if not runtime_asset:
            return self._create_error_result("No runtime asset provided")
        
        # 构建输入消息
        input_message = self._build_input_message(runtime_asset)
        
        try:
            # 调用模型获取结构化输出
            result = await self._call_structured(
                message=input_message,
                schema=self.OUTPUT_SCHEMA
            )
            
            confidence = result.get("confidence", 0.0)
            
            logger.info(
                "log_analysis_completed",
                exception_type=result.get("exception_type"),
                confidence=confidence
            )
            
            return self._create_success_result(
                data=result,
                confidence=confidence,
                reasoning=f"分析完成，发现 {len(result.get('key_findings', []))} 个关键发现"
            )
            
        except Exception as e:
            logger.error("log_analysis_failed", error=str(e))
            return self._create_error_result(str(e))
    
    def _build_input_message(self, runtime_asset: Dict[str, Any]) -> str:
        """
        构建输入消息
        
        Args:
            runtime_asset: 运行态资产
            
        Returns:
            格式化的输入消息
        """
        parts = []
        
        # 添加异常信息
        exception = runtime_asset.get("exception")
        if exception:
            parts.append(f"## 异常信息\n```json\n{json.dumps(exception, ensure_ascii=False, indent=2)}\n```")
        
        # 添加原始日志
        raw_logs = runtime_asset.get("rawLogs", [])
        if raw_logs:
            logs_text = "\n".join(raw_logs[:50])  # 限制日志行数
            parts.append(f"## 原始日志\n```\n{logs_text}\n```")
        
        # 添加 JVM 指标
        jvm_metrics = runtime_asset.get("jvmMetrics")
        if jvm_metrics:
            parts.append(f"## JVM 指标\n```json\n{json.dumps(jvm_metrics, ensure_ascii=False, indent=2)}\n```")
        
        # 添加慢 SQL
        slow_sqls = runtime_asset.get("slowSQLs", [])
        if slow_sqls:
            parts.append(f"## 慢 SQL\n```json\n{json.dumps(slow_sqls, ensure_ascii=False, indent=2)}\n```")
        
        # 添加 Trace 信息
        traces = runtime_asset.get("traces", [])
        if traces:
            parts.append(f"## Trace 信息\n```json\n{json.dumps(traces[:10], ensure_ascii=False, indent=2)}\n```")
        
        # 添加来源信息
        source = runtime_asset.get("source", {})
        if source:
            parts.append(f"## 来源信息\n服务名称: {source.get('serviceName', 'unknown')}\n环境: {source.get('environment', 'unknown')}")
        
        return "\n\n".join(parts)
