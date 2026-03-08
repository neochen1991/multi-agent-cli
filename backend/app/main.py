"""
SRE Debate Platform - FastAPI 应用入口

本模块是整个多智能体辩论平台的主入口，负责：
1. 创建和配置 FastAPI 应用实例
2. 注册中间件（CORS、认证、限流、监控）
3. 注册 API 路由和 WebSocket 端点
4. 配置结构化日志
5. 定义应用生命周期管理

Multi-Agent Debate Platform for SRE
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.config import settings
from app.api.router import api_router
from app.api.ws_debates import router as ws_router
from app.core.observability import MetricsMiddleware, beijing_timestamp_processor, metrics_store
from app.core.rate_limit import RateLimitMiddleware
from app.core.security import AuthRBACMiddleware

# 配置结构化日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        beijing_timestamp_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(ensure_ascii=False) if settings.LOG_FORMAT == "json" 
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理器

    使用 async context manager 管理应用的启动和关闭过程：
    - 启动时：记录应用信息，初始化资源
    - 关闭时：清理资源，记录关闭日志

    Args:
        app: FastAPI 应用实例

    Yields:
        None: 控制权交给应用运行期间
    """
    # 启动时：记录应用启动信息
    logger.info(
        "application_starting",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
    
    yield
    
    # 关闭时
    logger.info("application_shutting_down")


def create_application() -> FastAPI:
    """
    创建 FastAPI 应用实例

    本函数负责：
    1. 创建 FastAPI 应用并设置元数据（标题、描述、版本）
    2. 配置 CORS 中间件，支持跨域请求
    3. 注册认证/权限中间件（AuthRBACMiddleware）
    4. 注册限流中间件（RateLimitMiddleware）
    5. 注册监控指标中间件（MetricsMiddleware）
    6. 注册 API 路由和 WebSocket 路由
    7. 配置健康检查和指标端点
    8. 设置全局异常处理器

    Returns:
        FastAPI: 配置完成的 FastAPI 应用实例
    """
    app = FastAPI(
        title=settings.APP_NAME,
        description="""
## 多模型辩论式 SRE 智能体平台

基于 LangGraph 多 Agent 编排构建的多模型辩论式 SRE 智能体平台，实现三态资产融合与 AI 技术委员会决策系统。

### 核心功能
- 🔥 三态资产融合（运行态/开发态/设计态）
- 🧠 多模型专家委员会
- ⚖️ AI 内部辩论机制
- 🔗 可扩展自动修复能力

### 多模型专家
| Agent | 模型 | 角色 |
|-------|------|------|
| LogAgent | glm-5 | 日志分析专家 |
| DomainAgent | glm-5 | 领域映射专家 |
| CodeAgent | glm-5 | 代码分析专家 |
| CriticAgent | glm-5 | 架构质疑专家 |
| RebuttalAgent | glm-5 | 技术反驳专家 |
| JudgeAgent | glm-5 | 技术委员会主席 |
        """,
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS 中间件：允许跨域请求，支持前后端分离架构
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,  # 允许的源列表
        allow_credentials=True,  # 允许携带凭证（cookies）
        allow_methods=["*"],  # 允许所有 HTTP 方法
        allow_headers=["*"],  # 允许所有请求头
    )
    # 认证与权限控制中间件
    app.add_middleware(AuthRBACMiddleware)
    # API 限流中间件，防止滥用
    app.add_middleware(RateLimitMiddleware)
    # 监控指标收集中间件
    app.add_middleware(MetricsMiddleware)

    # 注册路由：API 路由带 /api/v1 前缀，WebSocket 路由独立注册
    app.include_router(api_router, prefix=settings.API_PREFIX)
    app.include_router(ws_router)

    # 健康检查端点：用于 Kubernetes 探针或负载均衡健康检测
    @app.get("/health", tags=["Health"])
    async def health_check():
        """
        健康检查端点

        返回应用状态信息，包括：
        - status: 健康状态
        - app_name: 应用名称
        - version: 版本号
        - environment: 运行环境

        Returns:
            dict: 健康状态信息
        """
        return {
            "status": "healthy",
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    # 指标端点：暴露应用运行指标
    @app.get("/metrics", tags=["Observability"])
    async def metrics():
        """
        核心运行指标端点

        返回应用运行时的各种监控指标，用于 Prometheus 等监控系统抓取。

        Returns:
            dict: 监控指标快照
        """
        return metrics_store.snapshot()

    # 根路径：返回 API 导航信息
    @app.get("/", tags=["Root"])
    async def root():
        """
        根路径端点

        提供 API 入口导航信息。

        Returns:
            dict: API 导航信息
        """
        return {
            "message": f"Welcome to {settings.APP_NAME}",
            "docs": "/docs",
            "health": "/health",
        }

    # 全局异常处理器：捕获所有未处理的异常，返回统一的错误响应
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        """
        全局异常处理器

        捕获所有未处理的异常，记录错误日志，返回统一的错误响应。
        开发环境会返回详细错误信息，生产环境只返回通用错误消息。

        Args:
            request: 请求对象
            exc: 异常实例

        Returns:
            JSONResponse: 统一格式的错误响应
        """
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "message": str(exc) if settings.DEBUG else "An unexpected error occurred",
            },
        )

    return app


# 创建应用实例
app = create_application()


def main():
    """
    主入口函数

    使用 uvicorn 启动 ASGI 服务器：
    - 监听 0.0.0.0:8000（所有网络接口）
    - 开发环境启用热重载
    - 从 logging.ini 加载日志配置
    """
    import uvicorn

    # 定位日志配置文件路径（backend/logging.ini）
    log_config_path = Path(__file__).resolve().parents[1] / "logging.ini"

    uvicorn.run(
        "app.main:app",  # 应用入口点
        host="0.0.0.0",  # 监听所有网络接口
        port=8000,  # 默认端口
        reload=settings.is_development,  # 开发环境启用热重载
        log_level=settings.LOG_LEVEL.lower(),  # 日志级别
        log_config=str(log_config_path) if log_config_path.exists() else None,  # 日志配置
    )


if __name__ == "__main__":
    main()
