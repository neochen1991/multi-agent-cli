"""三态资产 API。

覆盖运行态、开发态、设计态资产，以及责任田映射、案例库、资产融合和接口定位等能力。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from app.models.asset import (
    RuntimeAssetType,
    DevAssetType,
    DesignAssetType,
)
from app.services.asset_service import asset_service
from app.services.asset_knowledge_service import asset_knowledge_service
from app.services.incident_service import incident_service
from app.services.debate_service import debate_service

router = APIRouter()


# ==================== API 数据模型 ====================

class RuntimeAssetCreate(BaseModel):
    """创建运行态资产请求。"""
    type: str = Field(..., description="资产类型: log/metric/trace/alert/exception")
    source: str = Field(..., description="数据来源")
    raw_content: Optional[str] = Field(None, description="原始内容")
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="解析数据")
    service_name: Optional[str] = Field(None, description="服务名称")
    trace_id: Optional[str] = Field(None, description="链路ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class RuntimeAssetResponse(BaseModel):
    """运行态资产响应。"""
    id: str
    type: str
    source: str
    service_name: Optional[str]
    trace_id: Optional[str]
    timestamp: datetime
    metadata: Dict[str, Any]


class DevAssetCreate(BaseModel):
    """创建开发态资产请求。"""
    type: str = Field(..., description="资产类型: code/config/test/ci")
    name: str = Field(..., description="资产名称")
    path: str = Field(..., description="文件路径")
    language: Optional[str] = Field(None, description="编程语言")
    content: Optional[str] = Field(None, description="文件内容")
    repo_url: Optional[str] = Field(None, description="仓库URL")
    branch: Optional[str] = Field(None, description="分支")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class DevAssetResponse(BaseModel):
    """开发态资产响应。"""
    id: str
    type: str
    name: str
    path: str
    language: Optional[str]
    repo_url: Optional[str]
    branch: Optional[str]
    last_modified: Optional[datetime]


class DesignAssetCreate(BaseModel):
    """创建设计态资产请求。"""
    type: str = Field(..., description="资产类型: ddd_document/api_spec/db_schema/architecture/case_library")
    name: str = Field(..., description="资产名称")
    content: Optional[str] = Field(None, description="内容")
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="解析数据")
    domain: Optional[str] = Field(None, description="所属领域")
    owner: Optional[str] = Field(None, description="负责人")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class DesignAssetResponse(BaseModel):
    """设计态资产响应。"""
    id: str
    type: str
    name: str
    domain: Optional[str]
    owner: Optional[str]
    version: Optional[str]
    last_updated: Optional[datetime]


class DomainModelResponse(BaseModel):
    """领域模型响应。"""
    name: str
    description: Optional[str]
    aggregates: List[str]
    entities: List[str]
    value_objects: List[str]
    domain_services: List[str]
    owner_team: Optional[str]


class CaseCreate(BaseModel):
    """创建案例请求。"""
    title: str = Field(..., description="案例标题")
    description: str = Field(..., description="案例描述")
    incident_type: str = Field(..., description="故障类型")
    root_cause: str = Field(..., description="根因")
    solution: str = Field(..., description="解决方案")
    symptoms: Optional[List[str]] = Field(None, description="故障现象")
    related_services: Optional[List[str]] = Field(None, description="关联服务")
    tags: Optional[List[str]] = Field(None, description="标签")


class CaseResponse(BaseModel):
    """案例响应。"""
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
    """通用资产列表响应。"""
    items: List[Any]
    total: int


class AssetFusionResponse(BaseModel):
    """三态资产融合结果响应。"""
    incident_id: str
    debate_session_id: str
    runtime_assets: List[Dict[str, Any]]
    dev_assets: List[Dict[str, Any]]
    design_assets: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]


class InterfaceLocateRequest(BaseModel):
    """接口定位请求，用于从日志/现象映射责任田和关联资产。"""
    log_content: str = Field(..., description="接口报错日志")
    symptom: Optional[str] = Field(None, description="故障现象描述")


class InterfaceLocateResponse(BaseModel):
    """接口定位响应，返回责任田命中结果和衍生线索。"""
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


class ResponsibilityAssetRecord(BaseModel):
    """责任田资产记录。"""

    asset_id: str
    feature: str
    domain: str
    aggregate: str
    frontend_pages: List[str] = Field(default_factory=list)
    api_interfaces: List[str] = Field(default_factory=list)
    code_items: List[str] = Field(default_factory=list)
    database_tables: List[str] = Field(default_factory=list)
    dependency_services: List[str] = Field(default_factory=list)
    monitor_items: List[str] = Field(default_factory=list)
    owner_team: str = ""
    owner: str = ""
    source_file: str = ""
    row_index: Optional[int] = None
    created_at: str
    updated_at: str


class ResponsibilityAssetUpsertRequest(BaseModel):
    """手工新增或更新责任田资产记录的请求体。"""

    asset_id: Optional[str] = None
    feature: str
    domain: str
    aggregate: str
    frontend_pages: List[str] = Field(default_factory=list)
    api_interfaces: List[str] = Field(default_factory=list)
    code_items: List[str] = Field(default_factory=list)
    database_tables: List[str] = Field(default_factory=list)
    dependency_services: List[str] = Field(default_factory=list)
    monitor_items: List[str] = Field(default_factory=list)
    owner_team: str = ""
    owner: str = ""


class ResponsibilityAssetUploadResponse(BaseModel):
    """责任田资产批量导入结果。"""

    file_name: str
    replace_existing: bool
    imported: int
    stored: int
    preview: List[ResponsibilityAssetRecord]


# ==================== 运行态资产 API ====================

@router.post(
    "/runtime/",
    response_model=RuntimeAssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建运行态资产",
    description="创建新的运行态资产（日志、指标、链路等）"
)
async def create_runtime_asset(request: RuntimeAssetCreate):
    """创建运行态资产。"""
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
    """查询运行态资产列表，并支持按类型和服务过滤。"""
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
    """创建开发态资产。"""
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
    """查询开发态资产列表，并支持按类型和语言过滤。"""
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
    """按关键字搜索开发态代码资产。"""
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
    """创建设计态资产。"""
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
    """查询设计态资产列表，并支持按类型和领域过滤。"""
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
    """列出所有领域模型定义。"""
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
    """按名称读取单个领域模型。"""
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
    """创建案例库条目。"""
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
    """查询案例库列表。"""
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
    """按症状和异常类型搜索相似案例。"""
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
    """读取某个 incident 在会话上下文中的三态资产融合结果。"""
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
    """根据日志和症状定位责任田上下文。"""
    result = await asset_service.locate_interface_context(
        log_content=request.log_content,
        symptom=request.symptom,
    )
    return InterfaceLocateResponse(**result)


@router.get(
    "/resources",
    summary="资产资源源入口",
    description="返回本地优先、可插拔外部源的资源入口清单",
)
async def list_asset_resource_sources():
    """列出资产知识来源入口，包括本地责任田资产统计。"""
    payload = asset_knowledge_service.list_resource_sources()
    payload["responsibility_assets"] = await asset_service.responsibility_asset_stats()
    return payload


@router.get(
    "/responsibility/schema",
    summary="责任田资产模板字段",
    description="返回责任田资产维护建议字段与别名映射",
)
async def get_responsibility_schema():
    """返回责任田资产模板字段与导入建议。"""
    return asset_service.responsibility_asset_schema()


@router.get(
    "/responsibility",
    response_model=AssetListResponse,
    summary="责任田资产列表",
    description="查询用户维护的责任田资产记录",
)
async def list_responsibility_assets(
    q: Optional[str] = Query(None, description="全文检索关键词"),
    domain: Optional[str] = Query(None, description="按领域筛选"),
    aggregate: Optional[str] = Query(None, description="按聚合根筛选"),
    api: Optional[str] = Query(None, description="按接口关键词筛选"),
):
    """查询责任田资产记录。"""
    rows = await asset_service.list_responsibility_assets(
        query=q,
        domain=domain,
        aggregate=aggregate,
        api_keyword=api,
    )
    return AssetListResponse(items=[ResponsibilityAssetRecord(**x) for x in rows], total=len(rows))


@router.post(
    "/responsibility",
    response_model=ResponsibilityAssetRecord,
    summary="新增或更新责任田资产",
    description="手工维护责任田资产单行记录",
)
async def upsert_responsibility_asset(request: ResponsibilityAssetUpsertRequest):
    """手工新增或更新一条责任田资产记录。"""
    row = await asset_service.upsert_responsibility_asset(request.model_dump(mode="json"))
    return ResponsibilityAssetRecord(**row)


@router.delete(
    "/responsibility/{asset_id}",
    summary="删除责任田资产",
    description="按 asset_id 删除责任田资产记录",
)
async def delete_responsibility_asset(asset_id: str):
    """按 asset_id 删除责任田资产。"""
    ok = await asset_service.delete_responsibility_asset(asset_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"asset {asset_id} not found")
    return {"deleted": True, "asset_id": asset_id}


@router.post(
    "/responsibility/upload",
    response_model=ResponsibilityAssetUploadResponse,
    summary="上传责任田资产 Excel/CSV",
    description="上传并导入责任田资产清单；支持替换或追加合并",
)
async def upload_responsibility_assets(
    file: UploadFile = File(..., description="Excel/CSV 文件"),
    replace_existing: bool = Form(True, description="是否替换现有数据"),
):
    """上传 Excel/CSV 并批量导入责任田资产。"""
    file_name = str(file.filename or "").strip()
    if not file_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file name is required")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is empty")
    try:
        result = await asset_service.import_responsibility_assets_from_file(
            file_name=file_name,
            file_bytes=content,
            replace_existing=replace_existing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponsibilityAssetUploadResponse(
        file_name=str(result.get("file_name") or file_name),
        replace_existing=bool(result.get("replace_existing")),
        imported=int(result.get("imported") or 0),
        stored=int(result.get("stored") or 0),
        preview=[ResponsibilityAssetRecord(**x) for x in list(result.get("preview") or [])],
    )


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
    """手工建立运行态、开发态、设计态资产的关联关系。"""
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
    """根据运行态异常、代码类和责任田映射生成可展示的三态资产关系边。"""
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
        # 已定位到接口后，把数据库表、代码线索、设计文档等都回挂到这个接口节点上，供前端画关系图。
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
