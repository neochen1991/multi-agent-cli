"""API 路由汇总模块。

集中挂载各业务子路由，保证 `api/v1` 入口只在一处维护前缀和标签。
"""

from fastapi import APIRouter

from app.api import incidents, assets, debates, reports, auth, settings as settings_api, benchmark, governance, knowledge, monitoring

api_router = APIRouter()

# 统一在此处注册业务子路由，避免主应用层散落 include_router 调用。
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Auth"],
)

api_router.include_router(
    incidents.router,
    prefix="/incidents",
    tags=["Incidents"],
)

api_router.include_router(
    assets.router,
    prefix="/assets",
    tags=["Assets"],
)

api_router.include_router(
    knowledge.router,
    prefix="/knowledge",
    tags=["Knowledge"],
)

api_router.include_router(
    debates.router,
    prefix="/debates",
    tags=["Debates"],
)

api_router.include_router(
    reports.router,
    prefix="/reports",
    tags=["Reports"],
)

api_router.include_router(
    settings_api.router,
    prefix="/settings",
    tags=["Settings"],
)

api_router.include_router(
    benchmark.router,
    prefix="/benchmark",
    tags=["Benchmark"],
)

api_router.include_router(
    governance.router,
    prefix="/governance",
    tags=["Governance"],
)

api_router.include_router(
    monitoring.router,
    prefix="/monitoring",
    tags=["Monitoring"],
)
