"""
SRE Debate Platform - FastAPI 应用入口
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
    """应用生命周期管理"""
    # 启动时
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
    """创建 FastAPI 应用实例"""
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

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthRBACMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MetricsMiddleware)

    # 注册路由
    app.include_router(api_router, prefix=settings.API_PREFIX)
    app.include_router(ws_router)

    # 健康检查端点
    @app.get("/health", tags=["Health"])
    async def health_check():
        """健康检查"""
        return {
            "status": "healthy",
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    @app.get("/metrics", tags=["Observability"])
    async def metrics():
        """核心运行指标"""
        return metrics_store.snapshot()

    # 根路径
    @app.get("/", tags=["Root"])
    async def root():
        """根路径"""
        return {
            "message": f"Welcome to {settings.APP_NAME}",
            "docs": "/docs",
            "health": "/health",
        }

    # 全局异常处理
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
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
    """主入口函数"""
    import uvicorn

    log_config_path = Path(__file__).resolve().parents[1] / "logging.ini"

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level=settings.LOG_LEVEL.lower(),
        log_config=str(log_config_path) if log_config_path.exists() else None,
    )


if __name__ == "__main__":
    main()
