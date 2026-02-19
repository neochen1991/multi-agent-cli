"""
三态资产模型
Tri-State Asset Models
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AssetType(str, Enum):
    """资产类型"""
    RUNTIME = "runtime"         # 运行态
    DEVELOPMENT = "development" # 开发态
    DESIGN = "design"           # 设计态


class RuntimeAssetType(str, Enum):
    """运行态资产类型"""
    LOG = "log"                 # 日志
    METRIC = "metric"           # 指标
    TRACE = "trace"             # 链路
    ALERT = "alert"             # 告警
    EXCEPTION = "exception"     # 异常


class DevAssetType(str, Enum):
    """开发态资产类型"""
    CODE = "code"               # 代码
    CONFIG = "config"           # 配置
    TEST = "test"               # 测试
    CI = "ci"                   # CI/CD


class DesignAssetType(str, Enum):
    """设计态资产类型"""
    DDD_DOCUMENT = "ddd_document"       # DDD 文档
    API_SPEC = "api_spec"               # API 规范
    DB_SCHEMA = "db_schema"             # 数据库设计
    ARCHITECTURE = "architecture"       # 架构设计
    CASE_LIBRARY = "case_library"       # 案例库


# ============== 运行态资产 ==============

class RuntimeAsset(BaseModel):
    """运行态资产"""
    id: str = Field(..., description="资产ID")
    type: RuntimeAssetType = Field(..., description="资产类型")
    source: str = Field(..., description="数据来源")
    
    # 原始数据
    raw_content: Optional[str] = Field(None, description="原始内容")
    
    # 解析后的结构化数据
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="解析数据")
    
    # 关联信息
    service_name: Optional[str] = Field(None, description="服务名称")
    instance_id: Optional[str] = Field(None, description="实例ID")
    trace_id: Optional[str] = Field(None, description="链路ID")
    
    # 时间信息
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="时间戳")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "rt_001",
                "type": "log",
                "source": "application.log",
                "raw_content": "2024-01-15 10:30:00 ERROR [OrderService] NullPointerException...",
                "parsed_data": {
                    "exception": "NullPointerException",
                    "class": "OrderService",
                    "method": "createOrder",
                    "line": 156
                },
                "service_name": "order-service",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


class LogEntry(BaseModel):
    """日志条目"""
    timestamp: datetime = Field(..., description="时间戳")
    level: str = Field(..., description="日志级别")
    logger: str = Field(..., description="日志器")
    message: str = Field(..., description="日志消息")
    exception: Optional[str] = Field(None, description="异常信息")
    stack_trace: Optional[str] = Field(None, description="堆栈跟踪")
    thread: Optional[str] = Field(None, description="线程名")
    class_name: Optional[str] = Field(None, description="类名")
    method_name: Optional[str] = Field(None, description="方法名")
    line_number: Optional[int] = Field(None, description="行号")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class MetricData(BaseModel):
    """指标数据"""
    name: str = Field(..., description="指标名称")
    value: float = Field(..., description="指标值")
    unit: Optional[str] = Field(None, description="单位")
    labels: Dict[str, str] = Field(default_factory=dict, description="标签")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="时间戳")


class TraceSpan(BaseModel):
    """链路追踪 Span"""
    trace_id: str = Field(..., description="链路ID")
    span_id: str = Field(..., description="Span ID")
    parent_span_id: Optional[str] = Field(None, description="父 Span ID")
    operation_name: str = Field(..., description="操作名称")
    service_name: str = Field(..., description="服务名称")
    start_time: datetime = Field(..., description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    duration_ms: Optional[int] = Field(None, description="耗时(ms)")
    tags: Dict[str, Any] = Field(default_factory=dict, description="标签")
    logs: List[Dict[str, Any]] = Field(default_factory=list, description="日志")


# ============== 开发态资产 ==============

class DevAsset(BaseModel):
    """开发态资产"""
    id: str = Field(..., description="资产ID")
    type: DevAssetType = Field(..., description="资产类型")
    name: str = Field(..., description="资产名称")
    path: str = Field(..., description="文件路径")
    
    # 代码信息
    language: Optional[str] = Field(None, description="编程语言")
    content: Optional[str] = Field(None, description="文件内容")
    
    # Git 信息
    repo_url: Optional[str] = Field(None, description="仓库URL")
    branch: Optional[str] = Field(None, description="分支")
    commit_hash: Optional[str] = Field(None, description="提交哈希")
    last_modified: Optional[datetime] = Field(None, description="最后修改时间")
    
    # 解析后的结构化数据
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="解析数据")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "dev_001",
                "type": "code",
                "name": "OrderService.java",
                "path": "src/main/java/com/example/OrderService.java",
                "language": "java",
                "repo_url": "https://github.com/example/order-service",
                "branch": "main"
            }
        }


class CodeClass(BaseModel):
    """代码类"""
    name: str = Field(..., description="类名")
    package: Optional[str] = Field(None, description="包名")
    file_path: str = Field(..., description="文件路径")
    line_start: int = Field(..., description="起始行")
    line_end: Optional[int] = Field(None, description="结束行")
    
    # 类信息
    is_interface: bool = Field(default=False, description="是否接口")
    is_abstract: bool = Field(default=False, description="是否抽象类")
    extends: Optional[str] = Field(None, description="继承类")
    implements: List[str] = Field(default_factory=list, description="实现接口")
    
    # 注解
    annotations: List[str] = Field(default_factory=list, description="注解")
    
    # 方法
    methods: List[Dict[str, Any]] = Field(default_factory=list, description="方法列表")
    
    # 字段
    fields: List[Dict[str, Any]] = Field(default_factory=list, description="字段列表")


class CodeMethod(BaseModel):
    """代码方法"""
    name: str = Field(..., description="方法名")
    class_name: str = Field(..., description="所属类")
    return_type: Optional[str] = Field(None, description="返回类型")
    parameters: List[Dict[str, str]] = Field(default_factory=list, description="参数")
    line_start: int = Field(..., description="起始行")
    line_end: Optional[int] = Field(None, description="结束行")
    annotations: List[str] = Field(default_factory=list, description="注解")


# ============== 设计态资产 ==============

class DesignAsset(BaseModel):
    """设计态资产"""
    id: str = Field(..., description="资产ID")
    type: DesignAssetType = Field(..., description="资产类型")
    name: str = Field(..., description="资产名称")
    
    # 内容
    content: Optional[str] = Field(None, description="内容")
    
    # 解析后的结构化数据
    parsed_data: Optional[Dict[str, Any]] = Field(None, description="解析数据")
    
    # 关联信息
    domain: Optional[str] = Field(None, description="所属领域")
    owner: Optional[str] = Field(None, description="负责人")
    
    # 版本信息
    version: Optional[str] = Field(None, description="版本")
    last_updated: Optional[datetime] = Field(None, description="最后更新时间")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "des_001",
                "type": "ddd_document",
                "name": "订单域设计文档",
                "domain": "订单域",
                "owner": "订单责任田A组",
                "parsed_data": {
                    "aggregate": "OrderAggregate",
                    "entities": ["Order", "OrderItem"],
                    "value_objects": ["OrderId", "Money"]
                }
            }
        }


class DomainModel(BaseModel):
    """领域模型"""
    name: str = Field(..., description="领域名称")
    description: Optional[str] = Field(None, description="领域描述")
    
    # 聚合
    aggregates: List[str] = Field(default_factory=list, description="聚合列表")
    
    # 实体
    entities: List[str] = Field(default_factory=list, description="实体列表")
    
    # 值对象
    value_objects: List[str] = Field(default_factory=list, description="值对象列表")
    
    # 领域服务
    domain_services: List[str] = Field(default_factory=list, description="领域服务")
    
    # 领域事件
    domain_events: List[str] = Field(default_factory=list, description="领域事件")
    
    # 仓储
    repositories: List[str] = Field(default_factory=list, description="仓储列表")
    
    # 接口
    interfaces: List[Dict[str, Any]] = Field(default_factory=list, description="接口列表")
    
    # 数据库表
    db_tables: List[str] = Field(default_factory=list, description="数据库表")
    
    # 责任田
    owner_team: Optional[str] = Field(None, description="责任团队")
    owner: Optional[str] = Field(None, description="负责人")


class AggregateRoot(BaseModel):
    """聚合根"""
    name: str = Field(..., description="聚合根名称")
    domain: str = Field(..., description="所属领域")
    
    # 实体
    entities: List[str] = Field(default_factory=list, description="内部实体")
    
    # 值对象
    value_objects: List[str] = Field(default_factory=list, description="值对象")
    
    # 领域事件
    domain_events: List[str] = Field(default_factory=list, description="发布的领域事件")
    
    # 仓储
    repository: Optional[str] = Field(None, description="仓储接口")
    
    # 关联的数据库表
    db_tables: List[str] = Field(default_factory=list, description="关联数据库表")
    
    # 关联的接口
    interfaces: List[str] = Field(default_factory=list, description="关联接口")


class CaseLibrary(BaseModel):
    """案例库"""
    id: str = Field(..., description="案例ID")
    title: str = Field(..., description="案例标题")
    description: str = Field(..., description="案例描述")
    
    # 故障信息
    incident_type: str = Field(..., description="故障类型")
    symptoms: List[str] = Field(default_factory=list, description="故障现象")
    
    # 根因
    root_cause: str = Field(..., description="根因")
    root_cause_category: str = Field(..., description="根因类别")
    
    # 解决方案
    solution: str = Field(..., description="解决方案")
    fix_steps: List[str] = Field(default_factory=list, description="修复步骤")
    
    # 关联资产
    related_services: List[str] = Field(default_factory=list, description="关联服务")
    related_code: List[str] = Field(default_factory=list, description="关联代码")
    
    # 元数据
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    tags: List[str] = Field(default_factory=list, description="标签")


# ============== 三态资产统一模型 ==============

class TriStateAsset(BaseModel):
    """三态资产统一模型"""
    id: str = Field(..., description="资产ID")
    
    # 运行态
    runtime_assets: List[RuntimeAsset] = Field(default_factory=list, description="运行态资产")
    
    # 开发态
    dev_assets: List[DevAsset] = Field(default_factory=list, description="开发态资产")
    
    # 设计态
    design_assets: List[DesignAsset] = Field(default_factory=list, description="设计态资产")
    
    # 关联关系
    relationships: Dict[str, List[str]] = Field(default_factory=dict, description="资产关联关系")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="更新时间")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "tri_001",
                "runtime_assets": [
                    {
                        "id": "rt_001",
                        "type": "log",
                        "source": "application.log"
                    }
                ],
                "dev_assets": [
                    {
                        "id": "dev_001",
                        "type": "code",
                        "name": "OrderService.java",
                        "path": "src/main/java/com/example/OrderService.java"
                    }
                ],
                "design_assets": [
                    {
                        "id": "des_001",
                        "type": "ddd_document",
                        "name": "订单域设计文档"
                    }
                ],
                "relationships": {
                    "rt_001": ["dev_001", "des_001"]
                }
            }
        }
