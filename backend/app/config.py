"""
应用配置模块

本模块负责管理应用的所有配置项，包括：
1. LLM 配置（模型、API端点、超时等）
2. 数据库配置（PostgreSQL、Redis、Neo4j）
3. 辩论参数配置（最大轮次、共识阈值等）
4. 安全配置（密钥、认证、限流）
5. 日志配置

使用 pydantic-settings 实现配置管理：
- 支持从 .env 文件加载环境变量
- 支持类型验证和默认值
- 使用 @lru_cache 实现单例模式

Application configuration module
"""

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_CONFIG_FILE = Path(__file__).resolve().parents[2] / "config.json"


def _load_root_llm_overrides(config_file: Optional[Path] = None) -> Dict[str, Any]:
    """从仓库根目录 config.json 读取 LLM 配置覆盖项。"""
    target = Path(config_file) if config_file is not None else ROOT_CONFIG_FILE
    if not target.exists() or not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    llm = payload.get("llm")
    if not isinstance(llm, dict):
        return {}

    timeouts = llm.get("timeouts") if isinstance(llm.get("timeouts"), dict) else {}
    queue_timeouts = llm.get("queue_timeouts") if isinstance(llm.get("queue_timeouts"), dict) else {}
    debug = llm.get("debug") if isinstance(llm.get("debug"), dict) else {}

    # 中文注释：保持键名与 Settings 字段一致，后续直接作为默认值覆盖。
    mapping: Dict[str, Any] = {
        "LLM_PROVIDER_ID": llm.get("provider_id"),
        "LLM_MODEL": llm.get("model"),
        "LLM_BASE_URL": llm.get("base_url"),
        "LLM_API_KEY": llm.get("api_key"),
        "LLM_MAX_TURNS": llm.get("max_turns"),
        "LLM_MAX_RETRIES": llm.get("max_retries"),
        "LLM_MAX_CONCURRENCY": llm.get("max_concurrency"),
        "LLM_FAILFAST_ON_RATE_LIMIT": llm.get("failfast_on_rate_limit"),
        "LLM_TIMEOUT": timeouts.get("timeout"),
        "LLM_CONNECT_TIMEOUT": timeouts.get("connect"),
        "LLM_REQUEST_TIMEOUT": timeouts.get("request"),
        "LLM_TOTAL_TIMEOUT": timeouts.get("total"),
        "LLM_ASSET_TIMEOUT": timeouts.get("asset"),
        "LLM_ANALYSIS_TIMEOUT": timeouts.get("analysis"),
        "LLM_REVIEW_TIMEOUT": timeouts.get("review"),
        "LLM_JUDGE_TIMEOUT": timeouts.get("judge"),
        "LLM_JUDGE_RETRY_TIMEOUT": timeouts.get("judge_retry"),
        "LLM_REPORT_TIMEOUT_FIRST": timeouts.get("report_first"),
        "LLM_REPORT_TIMEOUT_RETRY": timeouts.get("report_retry"),
        "LLM_QUEUE_TIMEOUT": queue_timeouts.get("default"),
        "LLM_ANALYSIS_QUEUE_TIMEOUT": queue_timeouts.get("analysis"),
        "LLM_METRICS_QUEUE_TIMEOUT": queue_timeouts.get("metrics"),
        "LLM_JUDGE_QUEUE_TIMEOUT": queue_timeouts.get("judge"),
        "LLM_REPORT_QUEUE_TIMEOUT": queue_timeouts.get("report"),
        "LLM_LOG_FULL_PROMPT": debug.get("log_full_prompt"),
        "LLM_LOG_FULL_RESPONSE": debug.get("log_full_response"),
    }
    return {key: value for key, value in mapping.items() if value is not None}


ROOT_LLM_OVERRIDES = _load_root_llm_overrides()


def _llm_default(name: str, fallback: Any) -> Any:
    """读取 config.json 的同名 LLM 配置，缺失时回退到内置默认值。"""
    return ROOT_LLM_OVERRIDES.get(name, fallback)


class Settings(BaseSettings):
    """
    应用配置类

    使用 Pydantic BaseSettings 实现配置管理：
    - 支持从环境变量和 .env 文件加载配置
    - 自动类型转换和验证
    - 提供默认值，确保开箱即用

    配置分组说明：
    ----------------
    1. 应用基础配置：APP_NAME, APP_VERSION, DEBUG, ENVIRONMENT
    2. API 配置：API_PREFIX, CORS_ORIGINS
    3. 数据库配置：DATABASE_URL, REDIS_URL, NEO4J_*
    4. 本地存储配置：LOCAL_STORE_BACKEND, LOCAL_STORE_DIR
    5. LLM 配置：LLM_MODEL, LLM_BASE_URL, LLM_API_KEY 等
    6. 辩论配置：DEBATE_MAX_ROUNDS, DEBATE_CONSENSUS_THRESHOLD 等
    7. 安全配置：SECRET_KEY, AUTH_ENABLED 等
    8. 限流与熔断：RATE_LIMIT_*, CIRCUIT_BREAKER_*
    9. 日志配置：LOG_LEVEL, LOG_FORMAT
    10. Checkpointer 配置：CHECKPOINT_BACKEND, CHECKPOINT_SQLITE_PATH
    """

    # Pydantic-settings 配置：从 .env 文件加载，忽略大小写，允许额外字段
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用基础配置
    APP_NAME: str = "SRE Debate Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # API 配置
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000", "http://localhost:5173"])

    # 数据库配置
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/sre_debate"
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis 配置
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_CACHE_TTL: int = 3600  # 1 hour
    ENABLE_REDIS_CONTEXT: bool = False
    USE_CELERY: bool = False

    # Neo4j 配置
    NEO4J_URI: Optional[str] = Field(default="bolt://localhost:7687")
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # 本地存储配置（无外部数据库场景）
    # file: 使用文件存储，数据持久化到 LOCAL_STORE_DIR
    # memory: 使用内存存储，重启后数据丢失
    LOCAL_STORE_BACKEND: str = Field(default="file")  # file | memory
    LOCAL_STORE_DIR: str = Field(default="/tmp/sre_debate_store")

    # LLM / LangGraph 配置
    # 模型名称，默认使用 kimi-k2.5
    LLM_MODEL: str = Field(default=_llm_default("LLM_MODEL", "kimi-k2.5"))
    # LLM 最大对话轮次（None 表示不限制）
    LLM_MAX_TURNS: Optional[int] = _llm_default("LLM_MAX_TURNS", None)
    # 各类超时配置（秒），用于控制 LLM API 调用的超时行为
    LLM_TIMEOUT: Optional[int] = _llm_default("LLM_TIMEOUT", None)  # 通用超时
    LLM_CONNECT_TIMEOUT: Optional[int] = _llm_default("LLM_CONNECT_TIMEOUT", None)  # 连接超时
    LLM_REQUEST_TIMEOUT: Optional[int] = _llm_default("LLM_REQUEST_TIMEOUT", None)  # 请求超时
    LLM_TOTAL_TIMEOUT: Optional[int] = _llm_default("LLM_TOTAL_TIMEOUT", None)  # 总超时
    LLM_QUEUE_TIMEOUT: Optional[int] = _llm_default("LLM_QUEUE_TIMEOUT", None)  # 队列等待超时
    LLM_ANALYSIS_QUEUE_TIMEOUT: Optional[int] = _llm_default("LLM_ANALYSIS_QUEUE_TIMEOUT", None)  # 分析阶段队列等待超时
    LLM_METRICS_QUEUE_TIMEOUT: Optional[int] = _llm_default("LLM_METRICS_QUEUE_TIMEOUT", None)  # MetricsAgent 队列等待超时
    LLM_JUDGE_QUEUE_TIMEOUT: Optional[int] = _llm_default("LLM_JUDGE_QUEUE_TIMEOUT", None)  # 裁决阶段队列等待超时
    LLM_REPORT_QUEUE_TIMEOUT: Optional[int] = _llm_default("LLM_REPORT_QUEUE_TIMEOUT", None)  # 报告阶段队列等待超时
    LLM_ASSET_TIMEOUT: Optional[int] = _llm_default("LLM_ASSET_TIMEOUT", None)  # 资产处理超时
    LLM_ANALYSIS_TIMEOUT: Optional[int] = _llm_default("LLM_ANALYSIS_TIMEOUT", None)  # 分析阶段超时
    LLM_REVIEW_TIMEOUT: Optional[int] = _llm_default("LLM_REVIEW_TIMEOUT", None)  # 审查阶段超时
    LLM_JUDGE_TIMEOUT: Optional[int] = _llm_default("LLM_JUDGE_TIMEOUT", None)  # 裁决阶段超时
    LLM_JUDGE_RETRY_TIMEOUT: Optional[int] = _llm_default("LLM_JUDGE_RETRY_TIMEOUT", None)  # 裁决重试超时
    LLM_REPORT_TIMEOUT_FIRST: Optional[int] = _llm_default("LLM_REPORT_TIMEOUT_FIRST", None)  # 报告首次生成超时
    LLM_REPORT_TIMEOUT_RETRY: Optional[int] = _llm_default("LLM_REPORT_TIMEOUT_RETRY", None)  # 报告重试生成超时
    # 最大重试次数，0 表示不重试
    LLM_MAX_RETRIES: int = Field(default=_llm_default("LLM_MAX_RETRIES", 0))
    # 最大并发 LLM 调用数，用于控制 API 调用频率
    LLM_MAX_CONCURRENCY: int = Field(default=_llm_default("LLM_MAX_CONCURRENCY", 3))
    # 遇到限流错误时是否快速失败
    LLM_FAILFAST_ON_RATE_LIMIT: bool = Field(default=_llm_default("LLM_FAILFAST_ON_RATE_LIMIT", True))
    # 是否使用 Agent 工厂模式创建 Agent
    AGENT_USE_FACTORY: bool = False
    # LLM 提供商标识
    LLM_PROVIDER_ID: Optional[str] = _llm_default("LLM_PROVIDER_ID", None)
    # OpenAI-compatible endpoint (LangGraph config_list)
    # LLM API 基础 URL，默认使用 DashScope Coding OpenAI 兼容接口
    LLM_BASE_URL: str = Field(default=_llm_default("LLM_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1"))
    # LLM API 密钥
    LLM_API_KEY: str = Field(default=_llm_default("LLM_API_KEY", ""))
    # 调试开关：是否记录完整 prompt 到 output_refs，并在事件中保留 ref
    LLM_LOG_FULL_PROMPT: bool = Field(default=_llm_default("LLM_LOG_FULL_PROMPT", False))
    # 调试开关：是否记录完整 response 到 output_refs，并在事件中保留 ref
    LLM_LOG_FULL_RESPONSE: bool = Field(default=_llm_default("LLM_LOG_FULL_RESPONSE", False))

    # 辩论配置
    # 分析深度模式：quick | standard | deep
    DEBATE_ANALYSIS_DEPTH_MODE: str = "standard"
    # 按分析深度模式给出的默认轮次
    DEBATE_DEFAULT_MAX_ROUNDS_QUICK: int = 1
    DEBATE_DEFAULT_MAX_ROUNDS_STANDARD: int = 2
    DEBATE_DEFAULT_MAX_ROUNDS_DEEP: int = 4
    # 最大辩论轮次，默认 1 轮
    DEBATE_MAX_ROUNDS: int = 1
    # 共识阈值（0-1），当 JudgeAgent 置信度超过此值时认为达成共识
    DEBATE_CONSENSUS_THRESHOLD: float = 0.75
    # 辩论超时时间（秒），默认 15 分钟
    DEBATE_TIMEOUT: int = 900  # 15 minutes
    # 是否启用质疑阶段（CriticAgent）
    DEBATE_ENABLE_CRITIQUE: bool = True
    # 是否启用协作模式
    DEBATE_ENABLE_COLLABORATION: bool = False
    # 各阶段最大 token 数
    DEBATE_ANALYSIS_MAX_TOKENS: int = 320  # 分析阶段
    DEBATE_REVIEW_MAX_TOKENS: int = 420  # 审查阶段
    DEBATE_JUDGE_MAX_TOKENS: int = 900  # 裁决阶段
    DEBATE_REPORT_MAX_TOKENS: int = 700  # 报告生成
    # 是否要求 LLM 产出有效结论
    DEBATE_REQUIRE_EFFECTIVE_LLM_CONCLUSION: bool = True

    # 安全配置
    # JWT 密钥，生产环境必须更换
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production")
    # Token 过期时间（分钟）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # JWT 签名算法
    ALGORITHM: str = "HS256"
    # 是否启用认证
    AUTH_ENABLED: bool = False

    # 限流与熔断配置
    # 是否启用限流
    RATE_LIMIT_ENABLED: bool = True
    # 每分钟最大请求数
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 120
    # 熔断器失败阈值，超过此数量触发熔断
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    # 熔断器恢复时间（秒）
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 30

    # 日志配置
    # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_LEVEL: str = "INFO"
    # 日志格式：json 或 console
    LOG_FORMAT: str = "json"
    # 错误率告警阈值
    ALERT_ERROR_RATE_THRESHOLD: float = 0.2
    # Git 工具允许访问的主机白名单
    TOOL_GIT_HOST_ALLOWLIST: List[str] = Field(default=["github.com", "gitlab.com", "gitee.com"])
    # 远程 HTTP 工具允许访问的 URL 白名单
    TOOL_REMOTE_HTTP_ALLOWLIST: List[str] = Field(default=[])

    # Checkpointer 配置（LangGraph 状态持久化）
    # 后端类型：memory（内存）或 sqlite（SQLite 数据库）
    CHECKPOINT_BACKEND: str = Field(default="memory")  # memory | sqlite
    # SQLite 检查点文件路径
    CHECKPOINT_SQLITE_PATH: str = Field(default="/tmp/sre_debate_checkpoints/checkpoints.db")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """
        解析 CORS 允许源配置

        支持两种输入格式：
        - 字符串：逗号分隔的 URL 列表
        - 列表：直接返回

        Args:
            v: 输入值（字符串或列表）

        Returns:
            List[str]: URL 列表
        """
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("TOOL_GIT_HOST_ALLOWLIST", "TOOL_REMOTE_HTTP_ALLOWLIST", mode="before")
    @classmethod
    def parse_host_allowlists(cls, v):
        """
        解析主机白名单配置

        将输入转换为小写主机名列表，过滤空值。

        Args:
            v: 输入值（字符串、列表或 None）

        Returns:
            List[str]: 小写主机名列表
        """
        if isinstance(v, str):
            return [item.strip().lower() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip().lower() for item in v if str(item).strip()]
        return v

    @field_validator("LOCAL_STORE_BACKEND", mode="before")
    @classmethod
    def normalize_local_store_backend(cls, v):
        """
        标准化本地存储后端配置

        确保值为 "file" 或 "memory" 之一，默认为 "file"。

        Args:
            v: 输入值

        Returns:
            str: 标准化后的值
        """
        if not v:
            return "file"
        value = str(v).strip().lower()
        if value not in {"file", "memory"}:
            return "file"
        return value

    @field_validator("DEBATE_ANALYSIS_DEPTH_MODE", mode="before")
    @classmethod
    def normalize_debate_analysis_depth_mode(cls, v):
        """标准化分析深度模式，仅允许 quick/standard/deep。"""
        value = str(v or "standard").strip().lower()
        if value not in {"quick", "standard", "deep"}:
            return "standard"
        return value

    @property
    def debate_default_max_rounds_by_mode(self) -> Dict[str, int]:
        """返回按分析深度模式划分的默认轮次。"""
        return {
            "quick": max(1, min(8, int(self.DEBATE_DEFAULT_MAX_ROUNDS_QUICK or 1))),
            "standard": max(1, min(8, int(self.DEBATE_DEFAULT_MAX_ROUNDS_STANDARD or 2))),
            "deep": max(1, min(8, int(self.DEBATE_DEFAULT_MAX_ROUNDS_DEEP or 4))),
        }

    @property
    def is_development(self) -> bool:
        """检查是否为开发环境"""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """检查是否为生产环境"""
        return self.ENVIRONMENT == "production"

    @property
    def llm_options(self) -> Dict[str, str]:
        """
        获取 LLM 选项配置

        返回 LangChain/OpenAI 客户端所需的选项。

        Returns:
            Dict[str, str]: 包含 baseURL 和 apiKey 的字典
        """
        return {
            "baseURL": self.LLM_BASE_URL,
            "apiKey": self.LLM_API_KEY,
        }

    @property
    def llm_models(self) -> Dict[str, Dict[str, str]]:
        """
        获取 LLM 模型配置

        Returns:
            Dict[str, Dict[str, str]]: 模型名称到模型配置的映射
        """
        return {
            self.llm_model: {
                "name": self.llm_model,
            }
        }

    @property
    def llm_config(self) -> Dict[str, Dict[str, str]]:
        """
        获取完整的 LLM 配置

        合并选项和模型配置，用于 LangChain 初始化。

        Returns:
            Dict[str, Dict[str, str]]: 包含 options 和 models 的字典
        """
        return {
            "options": self.llm_options,
            "models": self.llm_models,
        }

    @property
    def default_model_config(self) -> Dict[str, str]:
        """
        获取默认模型配置

        用于前端展示当前使用的模型。

        Returns:
            Dict[str, str]: 包含模型名称和提供者信息的字典
        """
        return {
            "name": self.llm_model,
            "providerID": self.llm_provider_id,
            "modelID": self.llm_model,
        }

    @property
    def llm_model(self) -> str:
        """获取 LLM 模型名称"""
        return self.LLM_MODEL

    @property
    def llm_max_turns(self) -> int:
        """获取 LLM 最大对话轮次，默认为 1"""
        return self.LLM_MAX_TURNS or 1

    @property
    def llm_timeout(self) -> int:
        """获取通用 LLM 超时时间（秒），默认为 180 秒。"""
        return self.LLM_TIMEOUT or 180

    @property
    def llm_connect_timeout(self) -> int:
        """获取连接超时时间（秒），默认为 10 秒"""
        return self.LLM_CONNECT_TIMEOUT or 10

    @property
    def llm_request_timeout(self) -> int:
        """获取请求超时时间（秒），默认允许到 180 秒。"""
        return self.LLM_REQUEST_TIMEOUT or min(self.llm_timeout, 180)

    @property
    def llm_total_timeout(self) -> int:
        """获取总超时时间（秒），范围 45-90 秒。"""
        return self.LLM_TOTAL_TIMEOUT or max(45, min(self.llm_timeout, 90))

    @property
    def llm_queue_timeout(self) -> int:
        """获取通用队列等待超时时间（秒），默认放宽到 45 秒。"""
        return self.LLM_QUEUE_TIMEOUT or max(20, min(self.llm_total_timeout, 45))

    @property
    def llm_analysis_queue_timeout(self) -> int:
        """获取分析阶段队列等待超时时间（秒），默认放宽到 60 秒。"""
        return self.LLM_ANALYSIS_QUEUE_TIMEOUT or max(int(self.llm_queue_timeout), 60)

    @property
    def llm_metrics_queue_timeout(self) -> int:
        """获取 MetricsAgent 队列等待超时时间（秒），默认不低于 90 秒。"""
        return self.LLM_METRICS_QUEUE_TIMEOUT or max(int(self.llm_analysis_queue_timeout), 90)

    @property
    def llm_judge_queue_timeout(self) -> int:
        """获取裁决阶段队列等待超时时间（秒），默认放宽到 90 秒。"""
        return self.LLM_JUDGE_QUEUE_TIMEOUT or max(int(self.llm_analysis_queue_timeout), 90)

    @property
    def llm_report_queue_timeout(self) -> int:
        """获取报告阶段队列等待超时时间（秒），默认放宽到 60 秒。"""
        return self.LLM_REPORT_QUEUE_TIMEOUT or max(int(self.llm_queue_timeout), 60)

    @property
    def llm_asset_timeout(self) -> int:
        """获取资产处理超时时间（秒），范围 30-90 秒。"""
        return self.LLM_ASSET_TIMEOUT or max(30, min(self.llm_request_timeout, 90))

    @property
    def llm_analysis_timeout(self) -> int:
        """获取分析阶段超时时间（秒），范围 30-55 秒。"""
        return self.LLM_ANALYSIS_TIMEOUT or max(30, min(self.llm_total_timeout, 55))

    @property
    def llm_review_timeout(self) -> int:
        """获取审查阶段超时时间（秒），范围 35-60 秒。"""
        return self.LLM_REVIEW_TIMEOUT or max(35, min(self.llm_total_timeout, 60))

    @property
    def llm_judge_timeout(self) -> int:
        """获取裁决阶段超时时间（秒），范围 45-75 秒。"""
        return self.LLM_JUDGE_TIMEOUT or max(45, min(self.llm_total_timeout, 75))

    @property
    def llm_judge_retry_timeout(self) -> int:
        """获取裁决重试超时时间（秒），至少 60 秒。"""
        return self.LLM_JUDGE_RETRY_TIMEOUT or max(self.llm_judge_timeout, 60)

    @property
    def llm_report_timeout_first(self) -> int:
        """获取报告首次生成超时时间（秒），范围 24-50 秒。"""
        return self.LLM_REPORT_TIMEOUT_FIRST or max(24, min(self.llm_total_timeout, 50))

    @property
    def llm_report_timeout_retry(self) -> int:
        """获取报告重试生成超时时间（秒），至少 70 秒。"""
        return self.LLM_REPORT_TIMEOUT_RETRY or max(self.llm_report_timeout_first, 70)

    @property
    def llm_provider_id(self) -> str:
        """获取 LLM 提供者 ID，默认为 'langgraph'"""
        return self.LLM_PROVIDER_ID or "langgraph"


@lru_cache
def get_settings() -> Settings:
    """
    获取配置单例

    使用 functools.lru_cache 装饰器确保整个应用只创建一个 Settings 实例。
    这样可以避免重复读取环境变量和 .env 文件。

    Returns:
        Settings: 配置实例
    """
    return Settings()


# 导出配置实例，供其他模块直接使用
settings = get_settings()
