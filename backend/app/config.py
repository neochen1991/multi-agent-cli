"""
应用配置模块
Application configuration module
"""

from functools import lru_cache
from typing import Dict, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

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
    LOCAL_STORE_BACKEND: str = Field(default="file")  # file | memory
    LOCAL_STORE_DIR: str = Field(default="/tmp/sre_debate_store")

    # LLM / AutoGen 配置
    # 新字段（推荐）
    LLM_MODEL: Optional[str] = Field(default=None)
    LLM_MAX_TURNS: Optional[int] = None
    LLM_TIMEOUT: Optional[int] = None
    LLM_PROVIDER_ID: Optional[str] = None
    # 兼容历史字段
    CLAUDE_MODEL: str = Field(default="kimi-k2.5")
    CLAUDE_MAX_TURNS: int = 1
    OPENCODE_TIMEOUT: int = 300  # 5 minutes, reused as LLM timeout

    # OpenAI-compatible endpoint (AutoGen config_list)
    LLM_BASE_URL: str = Field(default="https://ark.cn-beijing.volces.com/api/coding")
    LLM_API_KEY: str = Field(default="b0f69e9a-7708-4bf8-af61-7b7822947ce4")
    OPENCODE_PROVIDER_ID: str = "autogen"
    OPENCODE_MODEL_NAME: str = "kimi-k2.5"

    # 辩论配置
    DEBATE_MAX_ROUNDS: int = 1
    DEBATE_CONSENSUS_THRESHOLD: float = 0.85
    DEBATE_TIMEOUT: int = 600  # 10 minutes

    # 安全配置
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"
    AUTH_ENABLED: bool = False

    # 限流与熔断
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 120
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 30

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    ALERT_ERROR_RATE_THRESHOLD: float = 0.2

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("LOCAL_STORE_BACKEND", mode="before")
    @classmethod
    def normalize_local_store_backend(cls, v):
        if not v:
            return "file"
        value = str(v).strip().lower()
        if value not in {"file", "memory"}:
            return "file"
        return value

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def opencode_options(self) -> Dict[str, str]:
        return self.llm_options

    @property
    def llm_options(self) -> Dict[str, str]:
        return {
            "baseURL": self.LLM_BASE_URL,
            "apiKey": self.LLM_API_KEY,
        }

    @property
    def opencode_models(self) -> Dict[str, Dict[str, str]]:
        return self.llm_models

    @property
    def llm_models(self) -> Dict[str, Dict[str, str]]:
        return {
            self.llm_model: {
                "name": self.llm_model,
            }
        }

    @property
    def llm_config(self) -> Dict[str, Dict[str, str]]:
        return {
            "options": self.llm_options,
            "models": self.llm_models,
        }

    @property
    def default_model_config(self) -> Dict[str, str]:
        return {
            "name": self.llm_model,
            "providerID": self.llm_provider_id,
            "modelID": self.llm_model,
        }

    @property
    def llm_model(self) -> str:
        return self.LLM_MODEL or self.CLAUDE_MODEL or self.OPENCODE_MODEL_NAME

    @property
    def llm_max_turns(self) -> int:
        return self.LLM_MAX_TURNS or self.CLAUDE_MAX_TURNS

    @property
    def llm_timeout(self) -> int:
        return self.LLM_TIMEOUT or self.OPENCODE_TIMEOUT

    @property
    def llm_provider_id(self) -> str:
        return self.LLM_PROVIDER_ID or self.OPENCODE_PROVIDER_ID or "autogen"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


# 导出配置实例
settings = get_settings()
