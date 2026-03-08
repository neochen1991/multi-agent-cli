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
        """保存运行态资产。"""
        pass

    @abstractmethod
    async def get_runtime_asset(self, asset_id: str) -> Optional[RuntimeAsset]:
        """读取单个运行态资产。"""
        pass

    @abstractmethod
    async def list_runtime_assets(self) -> List[RuntimeAsset]:
        """列出全部运行态资产。"""
        pass

    @abstractmethod
    async def save_dev_asset(self, asset: DevAsset) -> DevAsset:
        """保存开发态资产。"""
        pass

    @abstractmethod
    async def get_dev_asset(self, asset_id: str) -> Optional[DevAsset]:
        """读取单个开发态资产。"""
        pass

    @abstractmethod
    async def list_dev_assets(self) -> List[DevAsset]:
        """列出全部开发态资产。"""
        pass

    @abstractmethod
    async def save_design_asset(self, asset: DesignAsset) -> DesignAsset:
        """保存设计态资产。"""
        pass

    @abstractmethod
    async def get_design_asset(self, asset_id: str) -> Optional[DesignAsset]:
        """读取单个设计态资产。"""
        pass

    @abstractmethod
    async def list_design_assets(self) -> List[DesignAsset]:
        """列出全部设计态资产。"""
        pass

    @abstractmethod
    async def save_domain_model(self, model: DomainModel) -> DomainModel:
        """保存领域模型定义。"""
        pass

    @abstractmethod
    async def get_domain_model(self, name: str) -> Optional[DomainModel]:
        """按名称读取领域模型。"""
        pass

    @abstractmethod
    async def list_domain_models(self) -> List[DomainModel]:
        """列出全部领域模型。"""
        pass

    @abstractmethod
    async def save_case(self, case: CaseLibrary) -> CaseLibrary:
        """保存案例库条目。"""
        pass

    @abstractmethod
    async def get_case(self, case_id: str) -> Optional[CaseLibrary]:
        """按案例 ID 读取单条案例。"""
        pass

    @abstractmethod
    async def list_cases(self) -> List[CaseLibrary]:
        """列出全部案例库条目。"""
        pass

    @abstractmethod
    async def save_tri_state_asset(self, asset: TriStateAsset) -> TriStateAsset:
        """保存三态聚合资产。"""
        pass

    @abstractmethod
    async def get_tri_state_asset(self, asset_id: str) -> Optional[TriStateAsset]:
        """读取单个三态聚合资产。"""
        pass

    @abstractmethod
    async def list_tri_state_assets(self) -> List[TriStateAsset]:
        """列出全部三态聚合资产。"""
        pass


class InMemoryAssetRepository(AssetRepository):
    """基于内存的三态资产仓储"""

    def __init__(self):
        """初始化各态资产缓存，并准备案例库落盘目录。"""
        self._runtime_assets: Dict[str, RuntimeAsset] = {}
        self._dev_assets: Dict[str, DevAsset] = {}
        self._design_assets: Dict[str, DesignAsset] = {}
        self._domain_models: Dict[str, DomainModel] = {}
        self._cases: Dict[str, CaseLibrary] = {}
        self._tri_state_assets: Dict[str, TriStateAsset] = {}
        self._case_dir = Path(os.getenv("CASE_LIBRARY_PATH", "/tmp/case_library"))
        self._case_dir.mkdir(parents=True, exist_ok=True)

    async def save_runtime_asset(self, asset: RuntimeAsset) -> RuntimeAsset:
        """执行保存运行时资产，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._runtime_assets[asset.id] = asset
        return asset

    async def get_runtime_asset(self, asset_id: str) -> Optional[RuntimeAsset]:
        """负责获取运行时资产，并返回后续流程可直接消费的数据结果。"""
        return self._runtime_assets.get(asset_id)

    async def list_runtime_assets(self) -> List[RuntimeAsset]:
        """负责列出运行时assets，并返回后续流程可直接消费的数据结果。"""
        return list(self._runtime_assets.values())

    async def save_dev_asset(self, asset: DevAsset) -> DevAsset:
        """执行保存dev资产，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._dev_assets[asset.id] = asset
        return asset

    async def get_dev_asset(self, asset_id: str) -> Optional[DevAsset]:
        """负责获取dev资产，并返回后续流程可直接消费的数据结果。"""
        return self._dev_assets.get(asset_id)

    async def list_dev_assets(self) -> List[DevAsset]:
        """负责列出devassets，并返回后续流程可直接消费的数据结果。"""
        return list(self._dev_assets.values())

    async def save_design_asset(self, asset: DesignAsset) -> DesignAsset:
        """执行保存design资产，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._design_assets[asset.id] = asset
        return asset

    async def get_design_asset(self, asset_id: str) -> Optional[DesignAsset]:
        """负责获取design资产，并返回后续流程可直接消费的数据结果。"""
        return self._design_assets.get(asset_id)

    async def list_design_assets(self) -> List[DesignAsset]:
        """负责列出designassets，并返回后续流程可直接消费的数据结果。"""
        return list(self._design_assets.values())

    async def save_domain_model(self, model: DomainModel) -> DomainModel:
        """执行保存domainmodel，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._domain_models[model.name] = model
        return model

    async def get_domain_model(self, name: str) -> Optional[DomainModel]:
        """负责获取domainmodel，并返回后续流程可直接消费的数据结果。"""
        return self._domain_models.get(name)

    async def list_domain_models(self) -> List[DomainModel]:
        """负责列出domainmodels，并返回后续流程可直接消费的数据结果。"""
        return list(self._domain_models.values())

    async def save_case(self, case: CaseLibrary) -> CaseLibrary:
        """执行保存案例，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._cases[case.id] = case
        self._persist_case(case)
        return case

    async def get_case(self, case_id: str) -> Optional[CaseLibrary]:
        """负责获取案例，并返回后续流程可直接消费的数据结果。"""
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
        """负责列出cases，并返回后续流程可直接消费的数据结果。"""
        if not self._cases:
            for file in self._case_dir.glob("*.md"):
                loaded = self._load_case(file)
                if loaded:
                    self._cases[loaded.id] = loaded
        return list(self._cases.values())

    async def save_tri_state_asset(self, asset: TriStateAsset) -> TriStateAsset:
        """执行保存tri状态资产，并同步更新运行时状态、持久化结果或审计轨迹。"""
        self._tri_state_assets[asset.id] = asset
        return asset

    async def get_tri_state_asset(self, asset_id: str) -> Optional[TriStateAsset]:
        """负责获取tri状态资产，并返回后续流程可直接消费的数据结果。"""
        return self._tri_state_assets.get(asset_id)

    async def list_tri_state_assets(self) -> List[TriStateAsset]:
        """负责列出tri状态assets，并返回后续流程可直接消费的数据结果。"""
        return list(self._tri_state_assets.values())

    def _persist_case(self, case: CaseLibrary) -> None:
        """将案例以 markdown front matter 形式写盘，便于人工浏览与版本管理。"""
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
        """从 markdown front matter 恢复案例对象；格式不符合约定时返回空。"""
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
