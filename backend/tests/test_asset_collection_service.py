"""资产采集服务的日志降噪回归测试。"""

from __future__ import annotations

import pytest

from app.services import asset_collection_service as asset_collection_module
from app.services.asset_collection_service import AssetCollectionService


class _RecorderLogger:
    """记录 info/warning 调用，便于断言日志级别。"""

    def __init__(self) -> None:
        self.infos: list[tuple[str, dict]] = []
        self.warnings: list[tuple[str, dict]] = []

    def info(self, event: str, **kwargs) -> None:
        self.infos.append((event, kwargs))

    def warning(self, event: str, **kwargs) -> None:
        self.warnings.append((event, kwargs))

    def error(self, event: str, **kwargs) -> None:  # pragma: no cover - 本测试不会走到 error。
        raise AssertionError((event, kwargs))


@pytest.mark.asyncio
async def test_collect_dev_assets_skips_warning_when_repo_not_configured(monkeypatch):
    """未提供 repo_url / repo_path 时，应静默跳过开发态资产采集。"""

    recorder = _RecorderLogger()
    monkeypatch.setattr(asset_collection_module, "logger", recorder)
    service = AssetCollectionService()

    assets = await service.collect_dev_assets()

    assert assets == []
    assert recorder.warnings == []
    assert recorder.infos[0][0] == "repo_path_not_configured_skip"


@pytest.mark.asyncio
async def test_collect_dev_assets_warns_when_explicit_repo_path_missing(monkeypatch):
    """显式传入错误 repo_path 时，仍应保留 warning 方便排查。"""

    recorder = _RecorderLogger()
    monkeypatch.setattr(asset_collection_module, "logger", recorder)
    service = AssetCollectionService()

    assets = await service.collect_dev_assets(repo_path="/tmp/definitely-missing-repo")

    assert assets == []
    assert recorder.warnings[0][0] == "repo_path_not_found"


@pytest.mark.asyncio
async def test_collect_design_assets_skips_warning_when_default_docs_path_missing(monkeypatch):
    """默认设计文档目录缺失时，只记 info，避免每次 smoke 都刷 warning。"""

    recorder = _RecorderLogger()
    monkeypatch.setattr(asset_collection_module, "logger", recorder)
    monkeypatch.delenv("DESIGN_DOCS_PATH", raising=False)
    service = AssetCollectionService()

    assets = await service.collect_design_assets()

    assert assets == []
    assert recorder.warnings == []
    assert recorder.infos[0][0] == "design_docs_path_not_configured_skip"


@pytest.mark.asyncio
async def test_collect_design_assets_warns_when_explicit_docs_path_missing(monkeypatch):
    """显式传入不存在的设计文档目录时，应继续保留 warning。"""

    recorder = _RecorderLogger()
    monkeypatch.setattr(asset_collection_module, "logger", recorder)
    service = AssetCollectionService()

    assets = await service.collect_design_assets(design_docs_path="/tmp/definitely-missing-docs")

    assert assets == []
    assert recorder.warnings[0][0] == "design_docs_path_not_found"
