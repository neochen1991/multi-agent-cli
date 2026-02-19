"""
三态资产服务
Tri-State Asset Service
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from app.models.asset import (
    TriStateAsset,
    RuntimeAsset,
    DevAsset,
    DesignAsset,
    RuntimeAssetType,
    DevAssetType,
    DesignAssetType,
    DomainModel,
    CaseLibrary,
)
from app.repositories.asset_repository import (
    AssetRepository,
    InMemoryAssetRepository,
)
from app.services.asset_knowledge_service import asset_knowledge_service

logger = structlog.get_logger()


class AssetService:
    """三态资产服务"""
    
    def __init__(self, repository: Optional[AssetRepository] = None):
        self._repository = repository or InMemoryAssetRepository()
        self._sample_bootstrapped = False
        self._bootstrap_repo_id = id(self._repository)

    async def _ensure_sample_knowledge_loaded(self) -> None:
        """
        将本地 Markdown 示例注入到内存仓储。
        仅在首次或仓储实例更换后执行一次。
        """
        if id(self._repository) != self._bootstrap_repo_id:
            self._sample_bootstrapped = False
            self._bootstrap_repo_id = id(self._repository)

        if self._sample_bootstrapped:
            return

        payload = asset_knowledge_service.build_bootstrap_models()
        domain_models = payload.get("domain_models", [])
        cases = payload.get("cases", [])

        for model in domain_models:
            if not await self._repository.get_domain_model(model.name):
                await self._repository.save_domain_model(model)

        for case in cases:
            if not await self._repository.get_case(case.id):
                await self._repository.save_case(case)

        self._sample_bootstrapped = True
    
    # ============== 运行态资产 ==============
    
    async def create_runtime_asset(
        self,
        type: RuntimeAssetType,
        source: str,
        raw_content: Optional[str] = None,
        parsed_data: Optional[Dict[str, Any]] = None,
        service_name: Optional[str] = None,
        trace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RuntimeAsset:
        """创建运行态资产"""
        asset_id = f"rt_{uuid.uuid4().hex[:8]}"
        
        asset = RuntimeAsset(
            id=asset_id,
            type=type,
            source=source,
            raw_content=raw_content,
            parsed_data=parsed_data,
            service_name=service_name,
            trace_id=trace_id,
            metadata=metadata or {}
        )
        
        await self._repository.save_runtime_asset(asset)
        
        logger.info(
            "runtime_asset_created",
            asset_id=asset_id,
            type=type,
            source=source
        )
        
        return asset
    
    async def get_runtime_asset(self, asset_id: str) -> Optional[RuntimeAsset]:
        """获取运行态资产"""
        return await self._repository.get_runtime_asset(asset_id)
    
    async def list_runtime_assets(
        self,
        type: Optional[RuntimeAssetType] = None,
        service_name: Optional[str] = None
    ) -> List[RuntimeAsset]:
        """列出运行态资产"""
        assets = await self._repository.list_runtime_assets()
        
        if type:
            assets = [a for a in assets if a.type == type]
        if service_name:
            assets = [a for a in assets if a.service_name == service_name]
        
        return assets
    
    # ============== 开发态资产 ==============
    
    async def create_dev_asset(
        self,
        type: DevAssetType,
        name: str,
        path: str,
        language: Optional[str] = None,
        content: Optional[str] = None,
        repo_url: Optional[str] = None,
        branch: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DevAsset:
        """创建开发态资产"""
        asset_id = f"dev_{uuid.uuid4().hex[:8]}"
        
        asset = DevAsset(
            id=asset_id,
            type=type,
            name=name,
            path=path,
            language=language,
            content=content,
            repo_url=repo_url,
            branch=branch,
            metadata=metadata or {}
        )
        
        await self._repository.save_dev_asset(asset)
        
        logger.info(
            "dev_asset_created",
            asset_id=asset_id,
            type=type,
            name=name
        )
        
        return asset
    
    async def get_dev_asset(self, asset_id: str) -> Optional[DevAsset]:
        """获取开发态资产"""
        return await self._repository.get_dev_asset(asset_id)
    
    async def list_dev_assets(
        self,
        type: Optional[DevAssetType] = None,
        language: Optional[str] = None
    ) -> List[DevAsset]:
        """列出开发态资产"""
        assets = await self._repository.list_dev_assets()
        
        if type:
            assets = [a for a in assets if a.type == type]
        if language:
            assets = [a for a in assets if a.language == language]
        
        return assets
    
    async def search_code(self, query: str) -> List[DevAsset]:
        """
        搜索代码
        
        Args:
            query: 搜索关键词（类名、方法名等）
            
        Returns:
            匹配的代码资产列表
        """
        results = []
        query_lower = query.lower()
        
        for asset in await self._repository.list_dev_assets():
            if asset.type != DevAssetType.CODE:
                continue
            
            # 搜索名称
            if query_lower in asset.name.lower():
                results.append(asset)
                continue
            
            # 搜索内容
            if asset.content and query_lower in asset.content.lower():
                results.append(asset)
                continue
            
            # 搜索解析数据
            if asset.parsed_data:
                parsed_str = str(asset.parsed_data).lower()
                if query_lower in parsed_str:
                    results.append(asset)
        
        return results
    
    # ============== 设计态资产 ==============
    
    async def create_design_asset(
        self,
        type: DesignAssetType,
        name: str,
        content: Optional[str] = None,
        parsed_data: Optional[Dict[str, Any]] = None,
        domain: Optional[str] = None,
        owner: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DesignAsset:
        """创建设计态资产"""
        asset_id = f"des_{uuid.uuid4().hex[:8]}"
        
        asset = DesignAsset(
            id=asset_id,
            type=type,
            name=name,
            content=content,
            parsed_data=parsed_data,
            domain=domain,
            owner=owner,
            metadata=metadata or {}
        )
        
        await self._repository.save_design_asset(asset)
        
        logger.info(
            "design_asset_created",
            asset_id=asset_id,
            type=type,
            name=name
        )
        
        return asset
    
    async def get_design_asset(self, asset_id: str) -> Optional[DesignAsset]:
        """获取设计态资产"""
        return await self._repository.get_design_asset(asset_id)
    
    async def list_design_assets(
        self,
        type: Optional[DesignAssetType] = None,
        domain: Optional[str] = None
    ) -> List[DesignAsset]:
        """列出设计态资产"""
        assets = await self._repository.list_design_assets()
        
        if type:
            assets = [a for a in assets if a.type == type]
        if domain:
            assets = [a for a in assets if a.domain == domain]
        
        return assets
    
    # ============== 领域模型 ==============
    
    async def create_domain_model(
        self,
        name: str,
        description: Optional[str] = None,
        aggregates: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
        owner_team: Optional[str] = None
    ) -> DomainModel:
        """创建领域模型"""
        model = DomainModel(
            name=name,
            description=description,
            aggregates=aggregates or [],
            entities=entities or [],
            owner_team=owner_team
        )
        
        await self._repository.save_domain_model(model)
        
        logger.info(
            "domain_model_created",
            name=name,
            aggregates=len(aggregates or [])
        )
        
        return model
    
    async def get_domain_model(self, name: str) -> Optional[DomainModel]:
        """获取领域模型"""
        await self._ensure_sample_knowledge_loaded()
        return await self._repository.get_domain_model(name)
    
    async def list_domain_models(self) -> List[DomainModel]:
        """列出所有领域模型"""
        await self._ensure_sample_knowledge_loaded()
        return await self._repository.list_domain_models()
    
    async def find_domain_by_aggregate(self, aggregate_name: str) -> Optional[DomainModel]:
        """
        根据聚合名称查找领域
        
        Args:
            aggregate_name: 聚合名称
            
        Returns:
            领域模型或 None
        """
        await self._ensure_sample_knowledge_loaded()
        for model in await self._repository.list_domain_models():
            if aggregate_name in model.aggregates:
                return model
        return None
    
    # ============== 案例库 ==============
    
    async def create_case(
        self,
        title: str,
        description: str,
        incident_type: str,
        root_cause: str,
        solution: str,
        symptoms: Optional[List[str]] = None,
        related_services: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> CaseLibrary:
        """创建案例"""
        case_id = f"case_{uuid.uuid4().hex[:8]}"
        
        case = CaseLibrary(
            id=case_id,
            title=title,
            description=description,
            incident_type=incident_type,
            symptoms=symptoms or [],
            root_cause=root_cause,
            root_cause_category=incident_type,
            solution=solution,
            fix_steps=[],
            related_services=related_services or [],
            related_code=[],
            tags=tags or []
        )
        
        await self._repository.save_case(case)
        
        logger.info(
            "case_created",
            case_id=case_id,
            title=title,
            incident_type=incident_type
        )
        
        return case
    
    async def get_case(self, case_id: str) -> Optional[CaseLibrary]:
        """获取案例"""
        await self._ensure_sample_knowledge_loaded()
        return await self._repository.get_case(case_id)
    
    async def list_cases(
        self,
        incident_type: Optional[str] = None,
        tag: Optional[str] = None
    ) -> List[CaseLibrary]:
        """列出案例"""
        await self._ensure_sample_knowledge_loaded()
        cases = await self._repository.list_cases()
        
        if incident_type:
            cases = [c for c in cases if c.incident_type == incident_type]
        if tag:
            cases = [c for c in cases if tag in c.tags]
        
        return cases
    
    async def search_similar_cases(
        self,
        symptoms: List[str],
        exception_type: Optional[str] = None,
        limit: int = 5
    ) -> List[CaseLibrary]:
        """
        搜索相似案例
        
        Args:
            symptoms: 症状列表
            exception_type: 异常类型
            limit: 返回数量限制
            
        Returns:
            相似案例列表
        """
        await self._ensure_sample_knowledge_loaded()
        results = []
        
        for case in await self._repository.list_cases():
            score = 0
            
            # 匹配异常类型
            if exception_type and exception_type in case.root_cause:
                score += 10
            
            # 匹配症状
            for symptom in symptoms:
                if symptom.lower() in case.description.lower():
                    score += 1
                for case_symptom in case.symptoms:
                    if symptom.lower() in case_symptom.lower():
                        score += 2
            
            if score > 0:
                results.append((case, score))
        
        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        return [r[0] for r in results[:limit]]

    async def locate_interface_context(
        self,
        log_content: str,
        symptom: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        根据日志/现象中的接口信息，定位领域-聚合根责任田。
        """
        await self._ensure_sample_knowledge_loaded()
        return asset_knowledge_service.locate_by_log(
            log_content=log_content or "",
            symptom=symptom,
        )
    
    # ============== 三态资产关联 ==============
    
    async def create_tri_state_asset(
        self,
        runtime_assets: Optional[List[RuntimeAsset]] = None,
        dev_assets: Optional[List[DevAsset]] = None,
        design_assets: Optional[List[DesignAsset]] = None
    ) -> TriStateAsset:
        """创建三态资产"""
        asset_id = f"tri_{uuid.uuid4().hex[:8]}"
        
        asset = TriStateAsset(
            id=asset_id,
            runtime_assets=runtime_assets or [],
            dev_assets=dev_assets or [],
            design_assets=design_assets or []
        )
        
        await self._repository.save_tri_state_asset(asset)
        
        return asset
    
    async def get_tri_state_asset(self, asset_id: str) -> Optional[TriStateAsset]:
        """获取三态资产"""
        return await self._repository.get_tri_state_asset(asset_id)
    
    async def link_assets(
        self,
        runtime_asset_id: str,
        dev_asset_id: str,
        design_asset_id: Optional[str] = None
    ) -> bool:
        """
        关联三态资产
        
        Args:
            runtime_asset_id: 运行态资产ID
            dev_asset_id: 开发态资产ID
            design_asset_id: 设计态资产ID（可选）
            
        Returns:
            是否成功
        """
        runtime = await self._repository.get_runtime_asset(runtime_asset_id)
        dev = await self._repository.get_dev_asset(dev_asset_id)
        
        if not runtime or not dev:
            return False
        
        # 创建关联
        tri_asset = await self.create_tri_state_asset(
            runtime_assets=[runtime],
            dev_assets=[dev]
        )
        
        if design_asset_id:
            design = await self._repository.get_design_asset(design_asset_id)
            if design:
                tri_asset.design_assets.append(design)
        
        # 更新关系映射
        tri_asset.relationships[runtime_asset_id] = [dev_asset_id]
        if design_asset_id:
            tri_asset.relationships[runtime_asset_id].append(design_asset_id)

        tri_asset.updated_at = datetime.utcnow()
        await self._repository.save_tri_state_asset(tri_asset)
        
        logger.info(
            "assets_linked",
            runtime_id=runtime_asset_id,
            dev_id=dev_asset_id,
            design_id=design_asset_id
        )
        
        return True


# 全局实例
asset_service = AssetService()
