"""
业务服务层
Business Services

Use lazy export to avoid importing heavy service graphs at package import time.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "IncidentService",
    "incident_service",
    "DebateService",
    "debate_service",
    "AssetService",
    "asset_service",
    "AssetCollectionService",
    "asset_collection_service",
    "ReportGenerationService",
    "report_generation_service",
    "ReportService",
    "report_service",
]


def __getattr__(name: str) -> Any:
    service_module_map = {
        "IncidentService": "app.services.incident_service",
        "incident_service": "app.services.incident_service",
        "DebateService": "app.services.debate_service",
        "debate_service": "app.services.debate_service",
        "AssetService": "app.services.asset_service",
        "asset_service": "app.services.asset_service",
        "AssetCollectionService": "app.services.asset_collection_service",
        "asset_collection_service": "app.services.asset_collection_service",
        "ReportGenerationService": "app.services.report_generation_service",
        "report_generation_service": "app.services.report_generation_service",
        "ReportService": "app.services.report_service",
        "report_service": "app.services.report_service",
    }
    module_path = service_module_map.get(name)
    if not module_path:
        raise AttributeError(f"module 'app.services' has no attribute {name!r}")
    mod = import_module(module_path)
    return getattr(mod, name)
