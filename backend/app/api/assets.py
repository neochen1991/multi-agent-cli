"""
三态资产 API
Tri-State Asset API Endpoints
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.asset import (
    RuntimeAssetType,
    DevAssetType,
    DesignAssetType,
)
from app.services.asset_service import asset_service
from app.services.incident_service import incident_service
from app.services.debate_service import debate_service

router = APIRouter()


# ==================== API 数据模型 ====================

class RuntimeAssetCreate(BaseModel):
    """创建运行态资产请求"""
    type: str = Field(..., description="资产类型: log/metric/trace/alert/exception")
    source: str = Field(..., description="数据来源")
    raw_content: Optional[str] = Field(None, description="原始内容")
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="解析数据")
    service_name: Optional[str] = Field(None, description="服务名称")
    trace_id: Optional[str] = Field(None, description="链路ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class RuntimeAssetResponse(BaseModel):
    """运行态资产响应"""
    id: str
    type: str
    source: str
    service_name: Optional[str]
    trace_id: Optional[str]
    timestamp: datetime
    metadata: Dict[str, Any]


class DevAssetCreate(BaseModel):
    """创建开发态资产请求"""
    type: str = Field(..., description="资产类型: code/config/test/ci")
    name: str = Field(..., description="资产名称")
    path: str = Field(..., description="文件路径")
    language: Optional[str] = Field(None, description="编程语言")
    content: Optional[str] = Field(None, description="文件内容")
    repo_url: Optional[str] = Field(None, description="仓库URL")
    branch: Optional[str] = Field(None, description="分支")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class DevAssetResponse(BaseModel):
    """开发态资产响应"""
    id: str
    type: str
    name: str
    path: str
    language: Optional[str]
    repo_url: Optional[str]
    branch: Optional[str]
    last_modified: Optional[datetime]


class DesignAssetCreate(BaseModel):
    """创建设计态资产请求"""
    type: str = Field(..., description="资产类型: ddd_document/api_spec/db_schema/architecture/case_library")
    name: str = Field(..., description="资产名称")
    content: Optional[str] = Field(None, description="内容")
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="解析数据")
    domain: Optional[str] = Field(None, description="所属领域")
    owner: Optional[str] = Field(None, description="负责人")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class DesignAssetResponse(BaseModel):
    """设计态资产响应"""
    id: str
    type: str
    name: str
    domain: Optional[str]
    owner: Optional[str]
    version: Optional[str]
    last_updated: Optional[datetime]


class DomainModelResponse(BaseModel):
    """领域模型响应"""
    name: str
    description: Optional[str]
    aggregates: List[str]
    entities: List[str]
    value_objects: List[str]
    domain_services: List[str]
    owner_team: Optional[str]


class CaseCreate(BaseModel):
    """创建案例请求"""
    title: str = Field(..., description="案例标题")
    description: str = Field(..., description="案例描述")
    incident_type: str = Field(..., description="故障类型")
    root_cause: str = Field(..., description="根因")
    solution: str = Field(..., description="解决方案")
    symptoms: Optional[List[str]] = Field(None, description="故障现象")
    related_services: Optional[List[str]] = Field(None, description="关联服务")
    tags: Optional[List[str]] = Field(None, description="标签")


class CaseResponse(BaseModel):
    """案例响应"""
    id: str
    title: str
    description: str
    incident_type: str
    root_cause: str
    symptoms: List[str]
    solution: str
    related_services: List[str]
    tags: List[str]
    created_at: datetime


class AssetListResponse(BaseModel):
    """资产列表响应"""
    items: List[Any]
    total: int


class AssetFusionResponse(BaseModel):
    """资产融合结果响应"""
    incident_id: str
    debate_session_id: str
    runtime_assets: List[Dict[str, Any]]
    dev_assets: List[Dict[str, Any]]
    design_assets: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]


class InterfaceLocateRequest(BaseModel):
    """接口定位请求"""
    log_content: str = Field(..., description="接口报错日志")
    symptom: Optional[str] = Field(None, description="故障现象描述")


class InterfaceLocateResponse(BaseModel):
    """接口定位响应"""
    matched: bool
    confidence: float
    reason: str
    guidance: List[str]
    interface_hints: List[Dict[str, str]]
    domain: Optional[str]
    aggregate: Optional[str]
    owner_team: Optional[str]
    owner: Optional[str]
    matched_endpoint: Optional[Dict[str, Any]]
    code_artifacts: List[Dict[str, Any]]
    db_tables: List[str]
    design_ref: Optional[Dict[str, Any]]
    design_details: Optional[Dict[str, Any]]
    similar_cases: List[Dict[str, Any]]


# ==================== 运行态资产 API ====================

@router.post(
    "/runtime/",
    response_model=RuntimeAssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建运行态资产",
    description="创建新的运行态资产（日志、指标、链路等）"
)
async def create_runtime_asset(request: RuntimeAssetCreate):
    """创建运行态资产"""
    asset = await asset_service.create_runtime_asset(
        type=RuntimeAssetType(request.type),
        source=request.source,
        raw_content=request.raw_content,
        parsed_data=request.parsed_data,
        service_name=request.service_name,
        trace_id=request.trace_id,
        metadata=request.metadata,
    )
    
    return RuntimeAssetResponse(
        id=asset.id,
        type=asset.type.value,
        source=asset.source,
        service_name=asset.service_name,
        trace_id=asset.trace_id,
        timestamp=asset.timestamp,
        metadata=asset.metadata,
    )


@router.get(
    "/runtime/",
    response_model=AssetListResponse,
    summary="获取运行态资产列表",
    description="获取运行态资产列表"
)
async def list_runtime_assets(
    type: Optional[str] = Query(None, description="按类型筛选"),
    service_name: Optional[str] = Query(None, description="按服务名称筛选"),
):
    """获取运行态资产列表"""
    type_filter = RuntimeAssetType(type) if type else None
    assets = await asset_service.list_runtime_assets(
        type=type_filter,
        service_name=service_name
    )
    
    items = [
        RuntimeAssetResponse(
            id=a.id,
            type=a.type.value,
            source=a.source,
            service_name=a.service_name,
            trace_id=a.trace_id,
            timestamp=a.timestamp,
            metadata=a.metadata,
        )
        for a in assets
    ]
    
    return AssetListResponse(items=items, total=len(items))


# ==================== 开发态资产 API ====================

@router.post(
    "/dev/",
    response_model=DevAssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建开发态资产",
    description="创建新的开发态资产（代码、配置等）"
)
async def create_dev_asset(request: DevAssetCreate):
    """创建开发态资产"""
    asset = await asset_service.create_dev_asset(
        type=DevAssetType(request.type),
        name=request.name,
        path=request.path,
        language=request.language,
        content=request.content,
        repo_url=request.repo_url,
        branch=request.branch,
        metadata=request.metadata,
    )
    
    return DevAssetResponse(
        id=asset.id,
        type=asset.type.value,
        name=asset.name,
        path=asset.path,
        language=asset.language,
        repo_url=asset.repo_url,
        branch=asset.branch,
        last_modified=asset.last_modified,
    )


@router.get(
    "/dev/",
    response_model=AssetListResponse,
    summary="获取开发态资产列表",
    description="获取开发态资产列表"
)
async def list_dev_assets(
    type: Optional[str] = Query(None, description="按类型筛选"),
    language: Optional[str] = Query(None, description="按语言筛选"),
):
    """获取开发态资产列表"""
    type_filter = DevAssetType(type) if type else None
    assets = await asset_service.list_dev_assets(
        type=type_filter,
        language=language
    )
    
    items = [
        DevAssetResponse(
            id=a.id,
            type=a.type.value,
            name=a.name,
            path=a.path,
            language=a.language,
            repo_url=a.repo_url,
            branch=a.branch,
            last_modified=a.last_modified,
        )
        for a in assets
    ]
    
    return AssetListResponse(items=items, total=len(items))


@router.get(
    "/dev/search",
    response_model=AssetListResponse,
    summary="搜索代码",
    description="根据关键词搜索代码资产"
)
async def search_code(
    q: str = Query(..., description="搜索关键词"),
):
    """搜索代码"""
    assets = await asset_service.search_code(q)
    
    items = [
        DevAssetResponse(
            id=a.id,
            type=a.type.value,
            name=a.name,
            path=a.path,
            language=a.language,
            repo_url=a.repo_url,
            branch=a.branch,
            last_modified=a.last_modified,
        )
        for a in assets
    ]
    
    return AssetListResponse(items=items, total=len(items))


# ==================== 设计态资产 API ====================

@router.post(
    "/design/",
    response_model=DesignAssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建设计态资产",
    description="创建新的设计态资产（DDD文档、API规范等）"
)
async def create_design_asset(request: DesignAssetCreate):
    """创建设计态资产"""
    asset = await asset_service.create_design_asset(
        type=DesignAssetType(request.type),
        name=request.name,
        content=request.content,
        parsed_data=request.parsed_data,
        domain=request.domain,
        owner=request.owner,
        metadata=request.metadata,
    )
    
    return DesignAssetResponse(
        id=asset.id,
        type=asset.type.value,
        name=asset.name,
        domain=asset.domain,
        owner=asset.owner,
        version=asset.version,
        last_updated=asset.last_updated,
    )


@router.get(
    "/design/",
    response_model=AssetListResponse,
    summary="获取设计态资产列表",
    description="获取设计态资产列表"
)
async def list_design_assets(
    type: Optional[str] = Query(None, description="按类型筛选"),
    domain: Optional[str] = Query(None, description="按领域筛选"),
):
    """获取设计态资产列表"""
    type_filter = DesignAssetType(type) if type else None
    assets = await asset_service.list_design_assets(
        type=type_filter,
        domain=domain
    )
    
    items = [
        DesignAssetResponse(
            id=a.id,
            type=a.type.value,
            name=a.name,
            domain=a.domain,
            owner=a.owner,
            version=a.version,
            last_updated=a.last_updated,
        )
        for a in assets
    ]
    
    return AssetListResponse(items=items, total=len(items))


# ==================== 领域模型 API ====================

@router.get(
    "/domains/",
    response_model=List[DomainModelResponse],
    summary="获取领域模型列表",
    description="获取所有领域模型"
)
async def list_domain_models():
    """获取领域模型列表"""
    models = await asset_service.list_domain_models()
    
    return [
        DomainModelResponse(
            name=m.name,
            description=m.description,
            aggregates=m.aggregates,
            entities=m.entities,
            value_objects=m.value_objects,
            domain_services=m.domain_services,
            owner_team=m.owner_team,
        )
        for m in models
    ]


@router.get(
    "/domains/{name}",
    response_model=DomainModelResponse,
    summary="获取领域模型详情",
    description="根据名称获取领域模型详情"
)
async def get_domain_model(name: str):
    """获取领域模型详情"""
    model = await asset_service.get_domain_model(name)
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain model {name} not found"
        )
    
    return DomainModelResponse(
        name=model.name,
        description=model.description,
        aggregates=model.aggregates,
        entities=model.entities,
        value_objects=model.value_objects,
        domain_services=model.domain_services,
        owner_team=model.owner_team,
    )


# ==================== 案例库 API ====================

@router.post(
    "/cases/",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建案例",
    description="创建新的故障案例"
)
async def create_case(request: CaseCreate):
    """创建案例"""
    case = await asset_service.create_case(
        title=request.title,
        description=request.description,
        incident_type=request.incident_type,
        root_cause=request.root_cause,
        solution=request.solution,
        symptoms=request.symptoms,
        related_services=request.related_services,
        tags=request.tags,
    )
    
    return CaseResponse(
        id=case.id,
        title=case.title,
        description=case.description,
        incident_type=case.incident_type,
        root_cause=case.root_cause,
        symptoms=case.symptoms,
        solution=case.solution,
        related_services=case.related_services,
        tags=case.tags,
        created_at=case.created_at,
    )


@router.get(
    "/cases/",
    response_model=AssetListResponse,
    summary="获取案例列表",
    description="获取故障案例列表"
)
async def list_cases(
    incident_type: Optional[str] = Query(None, description="按故障类型筛选"),
    tag: Optional[str] = Query(None, description="按标签筛选"),
):
    """获取案例列表"""
    cases = await asset_service.list_cases(
        incident_type=incident_type,
        tag=tag
    )
    
    items = [
        CaseResponse(
            id=c.id,
            title=c.title,
            description=c.description,
            incident_type=c.incident_type,
            root_cause=c.root_cause,
            symptoms=c.symptoms,
            solution=c.solution,
            related_services=c.related_services,
            tags=c.tags,
            created_at=c.created_at,
        )
        for c in cases
    ]
    
    return AssetListResponse(items=items, total=len(items))


@router.get(
    "/cases/search",
    response_model=AssetListResponse,
    summary="搜索相似案例",
    description="根据症状搜索相似案例"
)
async def search_similar_cases(
    symptoms: str = Query(..., description="症状列表，逗号分隔"),
    exception_type: Optional[str] = Query(None, description="异常类型"),
    limit: int = Query(5, ge=1, le=20, description="返回数量"),
):
    """搜索相似案例"""
    symptom_list = [s.strip() for s in symptoms.split(",")]
    
    cases = await asset_service.search_similar_cases(
        symptoms=symptom_list,
        exception_type=exception_type,
        limit=limit
    )
    
    items = [
        CaseResponse(
            id=c.id,
            title=c.title,
            description=c.description,
            incident_type=c.incident_type,
            root_cause=c.root_cause,
            symptoms=c.symptoms,
            solution=c.solution,
            related_services=c.related_services,
            tags=c.tags,
            created_at=c.created_at,
        )
        for c in cases
    ]
    
    return AssetListResponse(items=items, total=len(items))


@router.get(
    "/fusion/{incident_id}",
    response_model=AssetFusionResponse,
    summary="查询资产融合结果",
    description="按故障事件ID获取三态资产融合结果及其关联关系"
)
async def get_asset_fusion(incident_id: str):
    incident = await incident_service.get_incident(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )

    if not incident.debate_session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} has no debate session"
        )

    session = await debate_service.get_session(incident.debate_session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Debate session {incident.debate_session_id} not found"
        )

    assets = session.context.get("assets", {})
    runtime_assets = assets.get("runtime_assets", [])
    dev_assets = assets.get("dev_assets", [])
    design_assets = assets.get("design_assets", [])
    relationships = _build_fusion_relationships(
        runtime_assets,
        dev_assets,
        design_assets,
        assets.get("interface_mapping", {}),
    )

    return AssetFusionResponse(
        incident_id=incident_id,
        debate_session_id=incident.debate_session_id,
        runtime_assets=runtime_assets,
        dev_assets=dev_assets,
        design_assets=design_assets,
        relationships=relationships,
    )


@router.post(
    "/locate",
    response_model=InterfaceLocateResponse,
    summary="按接口日志定位领域-聚合根",
    description="根据接口报错日志/现象，映射到领域、聚合根、代码、数据库表、设计文档与运维案例"
)
async def locate_by_interface(request: InterfaceLocateRequest):
    result = await asset_service.locate_interface_context(
        log_content=request.log_content,
        symptom=request.symptom,
    )
    return InterfaceLocateResponse(**result)


# ==================== 资产关联 API ====================

@router.post(
    "/link",
    summary="关联三态资产",
    description="关联运行态、开发态和设计态资产"
)
async def link_assets(
    runtime_asset_id: str = Query(..., description="运行态资产ID"),
    dev_asset_id: str = Query(..., description="开发态资产ID"),
    design_asset_id: Optional[str] = Query(None, description="设计态资产ID"),
):
    """关联三态资产"""
    success = await asset_service.link_assets(
        runtime_asset_id=runtime_asset_id,
        dev_asset_id=dev_asset_id,
        design_asset_id=design_asset_id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to link assets. Check if all asset IDs are valid."
        )
    
    return {"message": "Assets linked successfully"}


def _build_fusion_relationships(
    runtime_assets: List[Dict[str, Any]],
    dev_assets: List[Dict[str, Any]],
    design_assets: List[Dict[str, Any]],
    interface_mapping: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    relationships: List[Dict[str, Any]] = []

    dev_by_class: Dict[str, Dict[str, Any]] = {}
    for dev in dev_assets:
        parsed = dev.get("parsed_data") or {}
        class_name = parsed.get("class_name")
        if class_name:
            dev_by_class[class_name] = dev
        name = dev.get("name")
        if name:
            dev_by_class[name.replace(".java", "")] = dev

    design_by_domain: Dict[str, Dict[str, Any]] = {}
    for design in design_assets:
        domain = design.get("domain")
        if domain:
            design_by_domain[domain.lower()] = design

    for rt in runtime_assets:
        parsed = rt.get("parsed_data") or {}
        key_classes = parsed.get("key_classes", [])
        service_name = (rt.get("service_name") or parsed.get("service_name") or "").lower()

        for cls in key_classes:
            dev = dev_by_class.get(cls)
            if dev:
                relationships.append(
                    {
                        "source_id": rt.get("id"),
                        "source_type": "runtime",
                        "target_id": dev.get("id"),
                        "target_type": "development",
                        "relation": "exception_related_code",
                    }
                )
                domain_hit = None
                for domain, design in design_by_domain.items():
                    if domain in service_name:
                        domain_hit = design
                        break
                if domain_hit:
                    relationships.append(
                        {
                            "source_id": dev.get("id"),
                            "source_type": "development",
                            "target_id": domain_hit.get("id"),
                            "target_type": "design",
                            "relation": "domain_alignment",
                        }
                    )

    mapping = interface_mapping if isinstance(interface_mapping, dict) else {}
    endpoint = mapping.get("matched_endpoint") if isinstance(mapping.get("matched_endpoint"), dict) else {}
    endpoint_id = ""
    if endpoint:
        endpoint_id = f"{endpoint.get('method', 'ANY')} {endpoint.get('path', '-')}"

    if endpoint_id:
        # 反向追溯：数据库表 -> 接口
        for table in mapping.get("db_tables", []) or []:
            relationships.append(
                {
                    "source_id": table,
                    "source_type": "database",
                    "target_id": endpoint_id,
                    "target_type": "interface",
                    "relation": "db_table_to_interface",
                }
            )
        # 反向追溯：代码符号 -> 接口
        for artifact in mapping.get("code_artifacts", []) or []:
            symbol = artifact.get("symbol") if isinstance(artifact, dict) else None
            if not symbol:
                continue
            relationships.append(
                {
                    "source_id": symbol,
                    "source_type": "development",
                    "target_id": endpoint_id,
                    "target_type": "interface",
                    "relation": "code_symbol_to_interface",
                }
            )

    return relationships
