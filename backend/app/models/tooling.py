"""
Agent 工具配置模型。

这里集中定义各类本地工具、远端连接器和 Skill 路由的配置结构，
用于：
- 配置存储
- API 入参与出参校验
- 前后端共享统一字段语义
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from pydantic import BaseModel, Field


class CodeRepoToolConfig(BaseModel):
    """CodeAgent 的代码仓检索配置。"""
    enabled: bool = Field(default=False, description="是否启用 CodeAgent Git 工具")
    repo_url: str = Field(default="", description="Git 仓库地址")
    access_token: str = Field(default="", description="Git 访问 Token")
    branch: str = Field(default="main", description="默认分支")
    local_repo_path: str = Field(default="", description="本地仓库路径（可选，优先于 repo_url）")
    max_hits: int = Field(default=40, ge=1, le=200, description="最大匹配条数")


class LogFileToolConfig(BaseModel):
    """LogAgent 的本地日志文件读取配置。"""
    enabled: bool = Field(default=False, description="是否启用 LogAgent 日志文件工具")
    file_path: str = Field(default="", description="日志文件本地路径")
    max_lines: int = Field(default=300, ge=50, le=5000, description="最多读取日志行数")


class DomainExcelToolConfig(BaseModel):
    """DomainAgent 的责任田 Excel/CSV 检索配置。"""
    enabled: bool = Field(default=False, description="是否启用 DomainAgent 责任田文档工具")
    excel_path: str = Field(default="", description="Excel/CSV 文件路径")
    sheet_name: str = Field(default="", description="工作表名称（可选）")
    max_rows: int = Field(default=500, ge=50, le=5000, description="最大扫描行数")
    max_matches: int = Field(default=20, ge=1, le=200, description="最大命中行数")


class DatabaseToolConfig(BaseModel):
    """DatabaseAgent 的数据库元信息/慢 SQL 查询配置。"""
    enabled: bool = Field(default=False, description="是否启用 DatabaseAgent 数据库工具")
    engine: str = Field(default="sqlite", description="数据库引擎类型：sqlite/postgresql")
    db_path: str = Field(default="", description="SQLite 数据库文件路径")
    postgres_dsn: str = Field(default="", description="PostgreSQL 连接串，例如 postgresql://user:pass@host:5432/db")
    pg_schema: str = Field(default="public", description="PostgreSQL schema")
    connect_timeout_seconds: int = Field(default=8, ge=2, le=60, description="数据库连接超时（秒）")
    max_rows: int = Field(default=50, ge=1, le=500, description="慢 SQL / Top SQL 最大返回条数")


class TelemetrySourceConfig(BaseModel):
    """统一遥测入口配置，用于接入外部遥测平台。"""
    enabled: bool = Field(default=False, description="是否启用远程遥测数据源入口")
    endpoint: str = Field(default="", description="遥测平台 API 地址（占位）")
    api_token: str = Field(default="", description="遥测平台访问 Token（占位）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class CMDBSourceConfig(BaseModel):
    """CMDB 连接器配置。"""
    enabled: bool = Field(default=False, description="是否启用远程 CMDB 数据源入口")
    endpoint: str = Field(default="", description="CMDB API 地址（占位）")
    api_token: str = Field(default="", description="CMDB 访问 Token（占位）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class PrometheusSourceConfig(BaseModel):
    """Prometheus 连接器配置。"""
    enabled: bool = Field(default=False, description="是否启用 Prometheus 入口")
    endpoint: str = Field(default="", description="Prometheus HTTP API 地址")
    api_token: str = Field(default="", description="Prometheus 访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class LokiSourceConfig(BaseModel):
    """Loki 连接器配置。"""
    enabled: bool = Field(default=False, description="是否启用 Loki 入口")
    endpoint: str = Field(default="", description="Loki HTTP API 地址")
    api_token: str = Field(default="", description="Loki 访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class GrafanaSourceConfig(BaseModel):
    """Grafana 连接器配置。"""
    enabled: bool = Field(default=False, description="是否启用 Grafana 入口")
    endpoint: str = Field(default="", description="Grafana API 地址")
    api_token: str = Field(default="", description="Grafana 访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class APMSourceConfig(BaseModel):
    """APM 链路平台连接器配置。"""
    enabled: bool = Field(default=False, description="是否启用 APM 链路平台入口")
    endpoint: str = Field(default="", description="APM API 地址")
    api_token: str = Field(default="", description="APM 访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class LogCloudSourceConfig(BaseModel):
    """日志云平台连接器配置。"""
    enabled: bool = Field(default=False, description="是否启用日志云平台入口")
    endpoint: str = Field(default="", description="日志云 API 地址")
    api_token: str = Field(default="", description="日志云访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class AlertPlatformSourceConfig(BaseModel):
    """告警平台连接器配置。"""
    enabled: bool = Field(default=False, description="是否启用监控告警平台入口")
    endpoint: str = Field(default="", description="告警平台 API 地址")
    api_token: str = Field(default="", description="告警平台访问 Token（可选）")
    timeout_seconds: int = Field(default=8, ge=2, le=60, description="请求超时时间")
    verify_ssl: bool = Field(default=True, description="是否校验证书")


class AgentSkillConfig(BaseModel):
    """本地 Skill 路由配置。"""
    enabled: bool = Field(default=True, description="是否启用 Agent Skill 路由")
    skills_dir: str = Field(default="backend/skills", description="Skill 文档目录（本地）")
    extensions_enabled: bool = Field(default=True, description="是否启用扩展 Skill 目录")
    extensions_dir: str = Field(default="backend/extensions/skills", description="扩展 Skill 文档目录")
    max_skills: int = Field(default=3, ge=1, le=10, description="单次最多注入 Skill 数量")
    max_skill_chars: int = Field(default=1600, ge=200, le=8000, description="单个 Skill 最大注入字符数")
    allowed_agents: List[str] = Field(default_factory=list, description="允许调用 Skill 的 Agent 列表；为空表示全部")


class AgentToolPluginConfig(BaseModel):
    """可扩展 Tool 插件配置。"""

    enabled: bool = Field(default=True, description="是否启用专家 Agent 的扩展 Tool 插件能力")
    plugins_dir: str = Field(default="backend/extensions/tools", description="Tool 插件目录")
    max_calls: int = Field(default=3, ge=1, le=20, description="单轮最多调用插件工具次数")
    default_timeout_seconds: int = Field(default=60, ge=5, le=600, description="插件默认超时时间")
    allowed_tools: List[str] = Field(default_factory=list, description="允许调用的插件工具名单；为空表示全部")


class MCPServerConfig(BaseModel):
    """MCP 服务配置。"""

    id: str = Field(default="", description="服务唯一 ID")
    name: str = Field(default="", description="服务名称")
    enabled: bool = Field(default=True, description="是否启用")
    type: str = Field(default="remote", description="服务类型：remote/local")
    transport: str = Field(default="http", description="传输协议：http/sse/stdio")
    protocol_mode: str = Field(
        default="gateway",
        description="调用模式：gateway=HTTP网关查询；mcp=远程标准MCP；local=本地STDIO MCP",
    )
    endpoint: str = Field(default="", description="MCP 服务地址（http/sse）")
    command: str = Field(default="", description="stdio 模式命令")
    command_list: List[str] = Field(default_factory=list, description="stdio 命令数组（兼容 OpenCode 风格）")
    args: List[str] = Field(default_factory=list, description="stdio 模式参数")
    env: Dict[str, str] = Field(default_factory=dict, description="stdio 模式环境变量")
    api_token: str = Field(default="", description="访问令牌")
    timeout_seconds: int = Field(default=12, ge=2, le=120, description="调用超时时间")
    capabilities: List[str] = Field(
        default_factory=lambda: ["logs", "metrics"],
        description="MCP 能力声明，例如 logs/metrics/alerts/traces/cmdb",
    )
    # 中文注释：支持按能力配置服务端 path，便于兼容不同 MCP 网关实现。
    tool_paths: Dict[str, str] = Field(
        default_factory=lambda: {
            "logs": "/logs/search",
            "metrics": "/metrics/query",
            "alerts": "/alerts/query",
            "traces": "/traces/query",
        },
        description="能力到 HTTP 路径的映射（仅 http/sse）",
    )
    metadata: Dict[str, str] = Field(default_factory=dict, description="扩展元数据")


class AgentMCPBindingConfig(BaseModel):
    """Agent 与 MCP 服务绑定配置。"""

    enabled: bool = Field(default=True, description="是否启用 MCP 绑定")
    bindings: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="agent_name -> [mcp_server_id...]",
    )


class AgentToolingConfig(BaseModel):
    """整套 Agent Tooling 配置聚合模型。"""
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
    tool_plugins: AgentToolPluginConfig = Field(default_factory=AgentToolPluginConfig)
    mcp_servers: List[MCPServerConfig] = Field(default_factory=list)
    mcp_bindings: AgentMCPBindingConfig = Field(default_factory=AgentMCPBindingConfig)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
