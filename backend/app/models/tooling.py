"""
Agent tooling configuration models.
"""

from __future__ import annotations

from datetime import datetime
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


class AgentToolingConfig(BaseModel):
    code_repo: CodeRepoToolConfig = Field(default_factory=CodeRepoToolConfig)
    log_file: LogFileToolConfig = Field(default_factory=LogFileToolConfig)
    domain_excel: DomainExcelToolConfig = Field(default_factory=DomainExcelToolConfig)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

