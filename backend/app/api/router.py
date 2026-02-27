"""
API 路由汇总
API Router Aggregation
"""

from fastapi import APIRouter

from app.api import incidents, assets, debates, reports, auth, settings as settings_api

api_router = APIRouter()

# 注册各模块路由
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
