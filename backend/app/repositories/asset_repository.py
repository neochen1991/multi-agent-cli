"""
三态资产仓储
Asset Repository
"""

from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from app.models.asset import (
    CaseLibrary,
    DesignAsset,
    DevAsset,
    DomainModel,
    RuntimeAsset,
    TriStateAsset,
)


class AssetRepository(ABC):
    """三态资产仓储接口"""

    @abstractmethod
    async def save_runtime_asset(self, asset: RuntimeAsset) -> RuntimeAsset:
        pass

    @abstractmethod
    async def get_runtime_asset(self, asset_id: str) -> Optional[RuntimeAsset]:
        pass

    @abstractmethod
    async def list_runtime_assets(self) -> List[RuntimeAsset]:
        pass

    @abstractmethod
    async def save_dev_asset(self, asset: DevAsset) -> DevAsset:
        pass

    @abstractmethod
    async def get_dev_asset(self, asset_id: str) -> Optional[DevAsset]:
        pass

    @abstractmethod
    async def list_dev_assets(self) -> List[DevAsset]:
        pass

    @abstractmethod
    async def save_design_asset(self, asset: DesignAsset) -> DesignAsset:
        pass

    @abstractmethod
    async def get_design_asset(self, asset_id: str) -> Optional[DesignAsset]:
        pass

    @abstractmethod
    async def list_design_assets(self) -> List[DesignAsset]:
        pass

    @abstractmethod
    async def save_domain_model(self, model: DomainModel) -> DomainModel:
        pass

    @abstractmethod
    async def get_domain_model(self, name: str) -> Optional[DomainModel]:
        pass

    @abstractmethod
    async def list_domain_models(self) -> List[DomainModel]:
        pass

    @abstractmethod
    async def save_case(self, case: CaseLibrary) -> CaseLibrary:
        pass

    @abstractmethod
    async def get_case(self, case_id: str) -> Optional[CaseLibrary]:
        pass

    @abstractmethod
    async def list_cases(self) -> List[CaseLibrary]:
        pass

    @abstractmethod
    async def save_tri_state_asset(self, asset: TriStateAsset) -> TriStateAsset:
        pass

    @abstractmethod
    async def get_tri_state_asset(self, asset_id: str) -> Optional[TriStateAsset]:
        pass

    @abstractmethod
    async def list_tri_state_assets(self) -> List[TriStateAsset]:
        pass


class InMemoryAssetRepository(AssetRepository):
    """基于内存的三态资产仓储"""

    def __init__(self):
        self._runtime_assets: Dict[str, RuntimeAsset] = {}
        self._dev_assets: Dict[str, DevAsset] = {}
        self._design_assets: Dict[str, DesignAsset] = {}
        self._domain_models: Dict[str, DomainModel] = {}
        self._cases: Dict[str, CaseLibrary] = {}
        self._tri_state_assets: Dict[str, TriStateAsset] = {}
        self._case_dir = Path(os.getenv("CASE_LIBRARY_PATH", "/tmp/case_library"))
        self._case_dir.mkdir(parents=True, exist_ok=True)

    async def save_runtime_asset(self, asset: RuntimeAsset) -> RuntimeAsset:
        self._runtime_assets[asset.id] = asset
        return asset

    async def get_runtime_asset(self, asset_id: str) -> Optional[RuntimeAsset]:
        return self._runtime_assets.get(asset_id)

    async def list_runtime_assets(self) -> List[RuntimeAsset]:
        return list(self._runtime_assets.values())

    async def save_dev_asset(self, asset: DevAsset) -> DevAsset:
        self._dev_assets[asset.id] = asset
        return asset

    async def get_dev_asset(self, asset_id: str) -> Optional[DevAsset]:
        return self._dev_assets.get(asset_id)

    async def list_dev_assets(self) -> List[DevAsset]:
        return list(self._dev_assets.values())

    async def save_design_asset(self, asset: DesignAsset) -> DesignAsset:
        self._design_assets[asset.id] = asset
        return asset

    async def get_design_asset(self, asset_id: str) -> Optional[DesignAsset]:
        return self._design_assets.get(asset_id)

    async def list_design_assets(self) -> List[DesignAsset]:
        return list(self._design_assets.values())

    async def save_domain_model(self, model: DomainModel) -> DomainModel:
        self._domain_models[model.name] = model
        return model

    async def get_domain_model(self, name: str) -> Optional[DomainModel]:
        return self._domain_models.get(name)

    async def list_domain_models(self) -> List[DomainModel]:
        return list(self._domain_models.values())

    async def save_case(self, case: CaseLibrary) -> CaseLibrary:
        self._cases[case.id] = case
        self._persist_case(case)
        return case

    async def get_case(self, case_id: str) -> Optional[CaseLibrary]:
        cached = self._cases.get(case_id)
        if cached:
            return cached
        file = self._case_dir / f"{case_id}.md"
        if not file.exists():
            return None
        loaded = self._load_case(file)
        if loaded:
            self._cases[loaded.id] = loaded
        return loaded

    async def list_cases(self) -> List[CaseLibrary]:
        if not self._cases:
            for file in self._case_dir.glob("*.md"):
                loaded = self._load_case(file)
                if loaded:
                    self._cases[loaded.id] = loaded
        return list(self._cases.values())

    async def save_tri_state_asset(self, asset: TriStateAsset) -> TriStateAsset:
        self._tri_state_assets[asset.id] = asset
        return asset

    async def get_tri_state_asset(self, asset_id: str) -> Optional[TriStateAsset]:
        return self._tri_state_assets.get(asset_id)

    async def list_tri_state_assets(self) -> List[TriStateAsset]:
        return list(self._tri_state_assets.values())

    def _persist_case(self, case: CaseLibrary) -> None:
        payload = case.model_dump(mode="json")
        file = self._case_dir / f"{case.id}.md"
        file.write_text(
            "---\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "---\n\n"
            f"# {case.title}\n\n"
            f"{case.description}\n",
            encoding="utf-8",
        )

    def _load_case(self, file: Path) -> Optional[CaseLibrary]:
        try:
            content = file.read_text(encoding="utf-8")
            if not content.startswith("---\n"):
                return None
            parts = content.split("\n---\n", 1)
            if len(parts) < 2:
                return None
            meta = parts[0].replace("---\n", "", 1).strip()
            return CaseLibrary(**json.loads(meta))
        except Exception:
            return None
