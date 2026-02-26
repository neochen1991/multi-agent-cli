"""
Agent 基类
Base Agent Class

所有专家 Agent 的基类，定义统一的接口和行为。
使用 LangGraph 多 Agent 进行 AI 交互。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
import structlog

from pydantic import BaseModel, Field

from app.core.llm_client import get_llm_client

logger = structlog.get_logger()


class AgentResult(BaseModel):
    """Agent 执行结果"""
    
    agent_name: str = Field(..., description="Agent 名称")
    agent_role: str = Field(..., description="Agent 角色")
    success: bool = Field(default=True, description="是否成功")
    data: Dict[str, Any] = Field(default_factory=dict, description="结果数据")
    confidence: float = Field(default=0.0, ge=0, le=1, description="置信度")
    reasoning: Optional[str] = Field(None, description="推理过程")
    error: Optional[str] = Field(None, description="错误信息")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="时间戳")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BaseAgent(ABC):
    """
    Agent 基类
    
    所有专家 Agent 都需要继承此类并实现以下方法：
    - _build_system_prompt(): 构建系统提示词
    - process(): 处理输入并返回结果
    
    使用 LangGraph 多 Agent 进行 AI 交互。
    工作流程：
    1. 创建会话 (session.create)
    2. 发送系统提示（可选，使用 noReply）
    3. 发送用户消息并获取响应
    """
    
    def __init__(
        self,
        name: str,
        model: Dict[str, str],
        role: str,
        tools: Optional[List[Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        """
        初始化 Agent
        
        Args:
            name: Agent 名称
            model: 模型配置，格式: {"name": "glm-5"}
            role: Agent 角色描述
            tools: 可用工具列表
            temperature: 生成温度
            max_tokens: 最大 token 数
        """
        self.name = name
        self.model = model
        self.role = role
        self.tools = tools or []
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = self._build_system_prompt()
        self._session_id: Optional[str] = None
        
        logger.info(
            "agent_initialized",
            name=name,
            model=model,
            role=role,
            tools_count=len(self.tools)
        )
    
    @abstractmethod
    def _build_system_prompt(self) -> str:
        """
        构建系统提示词
        
        子类必须实现此方法，返回适合该 Agent 的系统提示词。
        
        Returns:
            系统提示词字符串
        """
        pass
    
    @abstractmethod
    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """
        处理输入上下文
        
        子类必须实现此方法，定义 Agent 的核心处理逻辑。
        
        Args:
            context: 输入上下文，包含各种资产和之前的分析结果
            
        Returns:
            Agent 执行结果
        """
        pass
    
    async def _ensure_session(self) -> str:
        """
        确保有可用的会话
        
        Returns:
            会话 ID
        """
        if self._session_id is None:
            client = get_llm_client()
            session = await client.create_session(title=f"{self.name} Session")
            self._session_id = session.id
            
            # 发送系统提示（不触发响应）
            if self.system_prompt:
                await client.send_prompt(
                    session_id=self._session_id,
                    parts=[{"type": "text", "text": self.system_prompt}],
                    no_reply=True
                )
            
            logger.debug(
                "session_created",
                agent_name=self.name,
                session_id=self._session_id
            )
        
        return self._session_id
    
    async def _call_model(
        self,
        message: str,
        format: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        调用模型
        
        Args:
            message: 用户消息
            format: 结构化输出格式
            
        Returns:
            模型响应
        """
        session_id = await self._ensure_session()
        client = get_llm_client()
        
        response = await client.send_prompt(
            session_id=session_id,
            parts=[{"type": "text", "text": message}],
            model=self.model,
            format=format
        )
        
        return response
    
    async def _call_structured(
        self,
        message: str,
        schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        调用模型并获取结构化输出
        
        Args:
            message: 用户消息
            schema: JSON Schema
            
        Returns:
            结构化响应
        """
        session_id = await self._ensure_session()
        client = get_llm_client()
        
        response = await client.send_structured_prompt(
            session_id=session_id,
            text=message,
            schema=schema,
            model=self.model
        )
        
        # 提取结构化输出（兼容新老返回格式）
        structured_output = response.get("structured")
        if isinstance(structured_output, dict) and structured_output:
            return structured_output

        info = response.get("info", {})
        candidate = info.get("structured")
        if isinstance(candidate, dict) and candidate:
            return candidate

        candidate = info.get("structured_output")
        if isinstance(candidate, dict) and candidate:
            return candidate

        return {}
    
    def register_tool(self, tool: Any) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self.tools.append(tool)
        
        logger.debug(
            "tool_registered",
            agent_name=self.name,
            tool=str(tool)
        )
    
    def _create_success_result(
        self,
        data: Dict[str, Any],
        confidence: float = 0.0,
        reasoning: Optional[str] = None
    ) -> AgentResult:
        """
        创建成功结果
        
        Args:
            data: 结果数据
            confidence: 置信度
            reasoning: 推理过程
            
        Returns:
            成功的 AgentResult
        """
        return AgentResult(
            agent_name=self.name,
            agent_role=self.role,
            success=True,
            data=data,
            confidence=confidence,
            reasoning=reasoning,
        )
    
    def _create_error_result(
        self,
        error: str,
        data: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        创建错误结果
        
        Args:
            error: 错误信息
            data: 可选的部分结果数据
            
        Returns:
            错误的 AgentResult
        """
        return AgentResult(
            agent_name=self.name,
            agent_role=self.role,
            success=False,
            data=data or {},
            confidence=0.0,
            error=error,
        )
    
    async def _run_with_retry(
        self,
        input_data: Dict[str, Any],
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> AgentResult:
        """
        带重试的运行 Agent
        
        Args:
            input_data: 输入数据
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            
        Returns:
            Agent 执行结果
        """
        import asyncio
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                result = await self.process(input_data)
                return result
                    
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "agent_run_failed",
                    agent_name=self.name,
                    attempt=attempt + 1,
                    error=last_error
                )
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
        
        return self._create_error_result(
            error=f"Agent failed after {max_retries} retries: {last_error}"
        )
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, model={self.model}, role={self.role})"
