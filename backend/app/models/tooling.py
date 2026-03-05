"""
Agent tooling configuration models.
"""

from __future__ import annotations

from datetime import datetime
from typing import List
from pydantic import BaseModel, Field


class CodeRepoToolConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 CodeAgent Git 工具")
    repo_url: str = Field(default="", description="Git 仓库地址")
    access_token: str = Field(default="", description="Git 访问 Token")
    branch: str = Field(default="main", description="默认分支")
    local_repo_path: str = Field(default="", description="本地仓库路径（可选，优先于 repo_url）")
    max_hits: int = Field(default=40, ge=1, le=200, description="最大匹配条数")


class LogFileToolConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 LogAgent 日志文件工具")
    file_path: str = Field(default="", description="日志文件本地路径")
    max_lines: int = Field(default=300, ge=50, le=5000, description="最多读取日志行数")


class DomainExcelToolConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 DomainAgent 责任田文档工具")
    excel_path: str = Field(default="", description="Excel/CSV 文件路径")
    sheet_name: str = Field(default="", description="工作表名称（可选）")
    max_rows: int = Field(default=500, ge=50, le=5000, description="最大扫描行数")
    max_matches: int = Field(default=20, ge=1, le=200, description="最大命中行数")


class DatabaseToolConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 DatabaseAgent 数据库工具")
    engine: str = Field(default="sqlite", description="数据库引擎类型：sqlite/postgresql")
    db_path: str = Field(default="", description="SQLite 数据库文件路径")
    postgres_dsn: str = Field(default="", description="PostgreSQL 连接串，例如 postgresql://user:pass@host:5432/db")
    pg_schema: str = Field(default="public", description="PostgreSQL schema")
    connect_timeout_seconds: int = Field(default=8, ge=2, le=60, description="数据库连接超时（秒）")
    max_rows: int = Field(default=50, ge=1, le=500, description="慢 SQL / Top SQL 最大返回条数")


class TelemetrySourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用远程遥测数据源入口")
    endpoint: str = Field(default="", description="遥测平台 API 地址（占位）")
    api_token: str = Field(default="", description="遥测平台访问 Token（占位）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class CMDBSourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用远程 CMDB 数据源入口")
    endpoint: str = Field(default="", description="CMDB API 地址（占位）")
    api_token: str = Field(default="", description="CMDB 访问 Token（占位）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class PrometheusSourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 Prometheus 入口")
    endpoint: str = Field(default="", description="Prometheus HTTP API 地址")
    api_token: str = Field(default="", description="Prometheus 访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class LokiSourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 Loki 入口")
    endpoint: str = Field(default="", description="Loki HTTP API 地址")
    api_token: str = Field(default="", description="Loki 访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class GrafanaSourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 Grafana 入口")
    endpoint: str = Field(default="", description="Grafana API 地址")
    api_token: str = Field(default="", description="Grafana 访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class APMSourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用 APM 链路平台入口")
    endpoint: str = Field(default="", description="APM API 地址")
    api_token: str = Field(default="", description="APM 访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class LogCloudSourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用日志云平台入口")
    endpoint: str = Field(default="", description="日志云 API 地址")
    api_token: str = Field(default="", description="日志云访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class AlertPlatformSourceConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用监控告警平台入口")
    endpoint: str = Field(default="", description="告警平台 API 地址")
    api_token: str = Field(default="", description="告警平台访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class AgentSkillConfig(BaseModel):
    enabled: bool = Field(default=True, description="是否启用 Agent Skill 路由")
    skills_dir: str = Field(default="backend/skills", description="Skill 文档目录（本地）")
    max_skills: int = Field(default=3, ge=1, le=10, description="单次最多注入 Skill 数量")
    max_skill_chars: int = Field(default=1600, ge=200, le=8000, description="单个 Skill 最大注入字符数")
    allowed_agents: List[str] = Field(default_factory=list, description="允许调用 Skill 的 Agent 列表；为空表示全部")


class AgentToolingConfig(BaseModel):
    code_repo: CodeRepoToolConfig = Field(default_factory=CodeRepoToolConfig)
    log_file: LogFileToolConfig = Field(default_factory=LogFileToolConfig)
    domain_excel: DomainExcelToolConfig = Field(default_factory=DomainExcelToolConfig)
    database: DatabaseToolConfig = Field(default_factory=DatabaseToolConfig)
    telemetry_source: TelemetrySourceConfig = Field(default_factory=TelemetrySourceConfig)
    cmdb_source: CMDBSourceConfig = Field(default_factory=CMDBSourceConfig)
    prometheus_source: PrometheusSourceConfig = Field(default_factory=PrometheusSourceConfig)
    loki_source: LokiSourceConfig = Field(default_factory=LokiSourceConfig)
    grafana_source: GrafanaSourceConfig = Field(default_factory=GrafanaSourceConfig)
    apm_source: APMSourceConfig = Field(default_factory=APMSourceConfig)
    logcloud_source: LogCloudSourceConfig = Field(default_factory=LogCloudSourceConfig)
    alert_platform_source: AlertPlatformSourceConfig = Field(default_factory=AlertPlatformSourceConfig)
    skills: AgentSkillConfig = Field(default_factory=AgentSkillConfig)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
