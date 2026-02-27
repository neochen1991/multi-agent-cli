"""
Build per-agent external tool context with on/off switches.
"""

from __future__ import annotations

import asyncio
import csv
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha1
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit

import structlog

from app.config import settings
from app.models.tooling import AgentToolingConfig
from app.services.tooling_service import tooling_service

logger = structlog.get_logger()


SOURCE_SUFFIXES = {
    ".py",
    ".java",
    ".kt",
    ".go",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rs",
    ".sql",
    ".yaml",
    ".yml",
    ".json",
    ".xml",
    ".properties",
    ".md",
}

GIT_FETCH_TIMEOUTS = (45, 90)
GIT_CLONE_TIMEOUTS = (90, 180)
GIT_LOCAL_TIMEOUT = 30


@dataclass
class ToolContextResult:
    name: str
    enabled: bool
    used: bool
    status: str
    summary: str
    data: Dict[str, Any]
    command_gate: Dict[str, Any] = field(default_factory=dict)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "used": self.used,
            "status": self.status,
            "summary": self.summary,
            "data": self.data,
            "command_gate": self.command_gate,
            "audit_log": self.audit_log,
        }


class AgentToolContextService:
    async def build_context(
        self,
        *,
        agent_name: str,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        command_gate = self._decide_tool_invocation(agent_name=agent_name, assigned_command=assigned_command)
        cfg = await tooling_service.get_config()
        if agent_name == "CodeAgent":
            result = await self._build_code_context(
                cfg, compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "LogAgent":
            result = await self._build_log_context(
                cfg, compact_context, incident_context, assigned_command, command_gate
            )
        elif agent_name == "DomainAgent":
            result = await self._build_domain_context(
                cfg, compact_context, incident_context, assigned_command, command_gate
            )
        else:
            result = ToolContextResult(
                name="none",
                enabled=False,
                used=False,
                status="skipped",
                summary="当前 Agent 无外部工具配置。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    self._audit(
                        tool_name="none",
                        action="tool_skip",
                        status="skipped",
                        detail={"reason": "当前 Agent 无外部工具配置。"},
                    )
                ],
            )
        return result.to_dict()

    async def _build_code_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        tool_cfg = cfg.code_repo
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="git_repo_search",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not tool_cfg.enabled:
            return ToolContextResult(
                name="git_repo_search",
                enabled=False,
                used=False,
                status="disabled",
                summary="CodeAgent Git 工具开关已关闭，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="git_repo_search",
                        action="config_check",
                        status="disabled",
                        detail={"enabled": False},
                    ),
                ],
            )
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="git_repo_search",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 CodeAgent 调用 Git 工具：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )

        try:
            repo_path = await asyncio.to_thread(
                self._resolve_repo_path,
                tool_cfg.repo_url,
                tool_cfg.access_token,
                tool_cfg.branch,
                tool_cfg.local_repo_path,
                audit_log,
            )
            if not repo_path:
                return ToolContextResult(
                    name="git_repo_search",
                    enabled=True,
                    used=False,
                    status="unavailable",
                    summary="未配置可用仓库地址/本地路径，使用默认分析逻辑。",
                    data={},
                    command_gate=command_gate,
                    audit_log=audit_log,
                )
            keywords = self._extract_keywords(compact_context, incident_context, assigned_command)
            hits, scan_meta = await asyncio.to_thread(
                self._search_repo,
                repo_path,
                keywords,
                int(tool_cfg.max_hits),
            )
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="repo_search",
                    status="ok",
                    detail=scan_meta,
                )
            )
            summary = f"仓库检索完成，命中 {len(hits)} 条代码片段。"
            return ToolContextResult(
                name="git_repo_search",
                enabled=True,
                used=True,
                status="ok",
                summary=summary,
                data={
                    "repo_path": str(repo_path),
                    "keywords": keywords,
                    "hits": hits[: int(tool_cfg.max_hits)],
                },
                command_gate=command_gate,
                audit_log=audit_log,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            logger.warning("code_tool_context_failed", error=error_text)
            return ToolContextResult(
                name="git_repo_search",
                enabled=True,
                used=False,
                status="error",
                summary=f"Git 工具调用失败：{error_text}，已回退默认分析逻辑。",
                data={"error": error_text},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="git_repo_search",
                        action="tool_execute",
                        status="error",
                        detail={"error": error_text},
                    ),
                ],
            )

    async def _build_log_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        tool_cfg = cfg.log_file
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="local_log_reader",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not tool_cfg.enabled:
            return ToolContextResult(
                name="local_log_reader",
                enabled=False,
                used=False,
                status="disabled",
                summary="LogAgent 日志文件工具开关已关闭，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="local_log_reader",
                        action="config_check",
                        status="disabled",
                        detail={"enabled": False},
                    ),
                ],
            )
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="local_log_reader",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 LogAgent 读取日志：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        path = Path(str(tool_cfg.file_path or "").strip())
        if not path.exists() or not path.is_file():
            return ToolContextResult(
                name="local_log_reader",
                enabled=True,
                used=False,
                status="unavailable",
                summary="日志文件路径不可用，已回退默认分析逻辑。",
                data={"file_path": str(path)},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="local_log_reader",
                        action="file_check",
                        status="unavailable",
                        detail={"file_path": str(path)},
                    ),
                ],
            )
        try:
            keywords = self._extract_keywords(compact_context, incident_context, assigned_command)
            excerpt, line_count, read_meta = await asyncio.to_thread(
                self._read_log_excerpt,
                path,
                int(tool_cfg.max_lines),
                keywords,
            )
            audit_log.append(
                self._audit(
                    tool_name="local_log_reader",
                    action="file_read",
                    status="ok",
                    detail=read_meta,
                )
            )
            return ToolContextResult(
                name="local_log_reader",
                enabled=True,
                used=True,
                status="ok",
                summary=f"日志文件读取完成，采样 {line_count} 行。",
                data={
                    "file_path": str(path),
                    "line_count": line_count,
                    "keywords": keywords,
                    "excerpt": excerpt,
                },
                command_gate=command_gate,
                audit_log=audit_log,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            logger.warning("log_tool_context_failed", error=error_text)
            return ToolContextResult(
                name="local_log_reader",
                enabled=True,
                used=False,
                status="error",
                summary=f"日志文件读取失败：{error_text}，已回退默认分析逻辑。",
                data={"error": error_text},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="local_log_reader",
                        action="file_read",
                        status="error",
                        detail={"error": error_text, "file_path": str(path)},
                    ),
                ],
            )

    async def _build_domain_context(
        self,
        cfg: AgentToolingConfig,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
        command_gate: Dict[str, Any],
    ) -> ToolContextResult:
        tool_cfg = cfg.domain_excel
        audit_log: List[Dict[str, Any]] = [
            self._audit(
                tool_name="domain_excel_lookup",
                action="command_gate",
                status="ok" if command_gate.get("allow_tool") else "skipped",
                detail={
                    "reason": str(command_gate.get("reason") or ""),
                    "has_command": bool(command_gate.get("has_command")),
                    "decision_source": str(command_gate.get("decision_source") or ""),
                    "command_preview": self._command_preview(assigned_command),
                },
            )
        ]
        if not tool_cfg.enabled:
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=False,
                used=False,
                status="disabled",
                summary="DomainAgent 责任田 Excel 工具开关已关闭，使用默认分析逻辑。",
                data={},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="domain_excel_lookup",
                        action="config_check",
                        status="disabled",
                        detail={"enabled": False},
                    ),
                ],
            )
        if not bool(command_gate.get("allow_tool")):
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=True,
                used=False,
                status="skipped_by_command",
                summary=f"主Agent命令未要求 DomainAgent 查询责任田文档：{str(command_gate.get('reason') or '未授权工具调用')}",
                data={"command_preview": self._command_preview(assigned_command)},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        path = Path(str(tool_cfg.excel_path or "").strip())
        if not path.exists() or not path.is_file():
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=True,
                used=False,
                status="unavailable",
                summary="责任田 Excel 路径不可用，已回退默认分析逻辑。",
                data={"excel_path": str(path)},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="domain_excel_lookup",
                        action="file_check",
                        status="unavailable",
                        detail={"excel_path": str(path)},
                    ),
                ],
            )
        try:
            keywords = self._extract_keywords(compact_context, incident_context, assigned_command)
            result = await asyncio.to_thread(
                self._lookup_domain_file,
                path,
                str(tool_cfg.sheet_name or "").strip(),
                int(tool_cfg.max_rows),
                int(tool_cfg.max_matches),
                keywords,
            )
            audit_log.append(
                self._audit(
                    tool_name="domain_excel_lookup",
                    action="file_read",
                    status="ok",
                    detail={
                        "excel_path": str(path),
                        "row_count": int(result.get("row_count") or 0),
                        "match_count": len(list(result.get("matches") or [])),
                        "sheet_used": str(result.get("sheet_used") or ""),
                        "format": str(result.get("format") or ""),
                    },
                )
            )
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=True,
                used=True,
                status="ok",
                summary=f"责任田文档查询完成，命中 {len(result.get('matches') or [])} 行。",
                data={"excel_path": str(path), "keywords": keywords, **result},
                command_gate=command_gate,
                audit_log=audit_log,
            )
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            logger.warning("domain_tool_context_failed", error=error_text)
            return ToolContextResult(
                name="domain_excel_lookup",
                enabled=True,
                used=False,
                status="error",
                summary=f"责任田文档查询失败：{error_text}，已回退默认分析逻辑。",
                data={"error": error_text},
                command_gate=command_gate,
                audit_log=[
                    *audit_log,
                    self._audit(
                        tool_name="domain_excel_lookup",
                        action="file_read",
                        status="error",
                        detail={"error": error_text, "excel_path": str(path)},
                    ),
                ],
            )

    def _resolve_repo_path(
        self,
        repo_url: str,
        access_token: str,
        branch: str,
        local_repo_path: str,
        audit_log: List[Dict[str, Any]],
    ) -> str:
        raw_local_path = str(local_repo_path or "").strip()
        local_path = Path(raw_local_path) if raw_local_path else None
        if local_path and local_path.exists() and local_path.is_dir():
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="repo_path_resolve",
                    status="ok",
                    detail={
                        "mode": "local",
                        "local_repo_path": str(local_path),
                    },
                )
            )
            return str(local_path)

        url = str(repo_url or "").strip()
        if not url:
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="repo_path_resolve",
                    status="unavailable",
                    detail={"reason": "repo_url 为空且 local_repo_path 不可用"},
                )
            )
            return ""

        cache_root = Path(settings.LOCAL_STORE_DIR) / "tool_cache" / "repos"
        cache_root.mkdir(parents=True, exist_ok=True)
        repo_key = sha1(url.encode("utf-8")).hexdigest()[:20]
        repo_path = cache_root / repo_key
        auth_url = self._inject_token(url, access_token)
        safe_branch = str(branch or "main").strip() or "main"
        safe_url = self._mask_url_secret(url)
        audit_log.append(
            self._audit(
                tool_name="git_repo_search",
                action="repo_path_resolve",
                status="ok",
                detail={
                    "mode": "remote",
                    "repo_url": safe_url,
                    "branch": safe_branch,
                    "cache_repo_path": str(repo_path),
                },
            )
        )

        if (repo_path / ".git").exists():
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="http_request",
                    status="started",
                    detail={
                        "operation": "git_fetch",
                        "repo_url": safe_url,
                        "branch": safe_branch,
                    },
                )
            )
            try:
                self._run_git_with_retry(
                    ["git", "fetch", "--depth", "1", "origin", safe_branch],
                    cwd=repo_path,
                    audit_log=audit_log,
                    action="git_fetch",
                    repo_url=safe_url,
                    timeout_plan=GIT_FETCH_TIMEOUTS,
                )
                self._run_git(
                    ["git", "checkout", safe_branch],
                    cwd=repo_path,
                    audit_log=audit_log,
                    action="git_checkout",
                    repo_url="",
                    timeout_seconds=GIT_LOCAL_TIMEOUT,
                )
                self._run_git(
                    ["git", "reset", "--hard", f"origin/{safe_branch}"],
                    cwd=repo_path,
                    audit_log=audit_log,
                    action="git_reset",
                    repo_url="",
                    timeout_seconds=GIT_LOCAL_TIMEOUT,
                )
            except Exception as exc:
                error_text = str(exc).strip() or exc.__class__.__name__
                audit_log.append(
                    self._audit(
                        tool_name="git_repo_search",
                        action="repo_sync_degraded",
                        status="fallback",
                        detail={
                            "reason": "remote fetch 失败，回退到本地缓存仓库",
                            "repo_path": str(repo_path),
                            "error": error_text[:400],
                        },
                    )
                )
                logger.warning(
                    "git_repo_sync_degraded",
                    repo_path=str(repo_path),
                    repo_url=safe_url,
                    error=error_text[:400],
                )
            return str(repo_path)

        audit_log.append(
            self._audit(
                tool_name="git_repo_search",
                action="http_request",
                status="started",
                detail={
                    "operation": "git_clone",
                    "repo_url": safe_url,
                    "branch": safe_branch,
                },
            )
        )
        if repo_path.exists() and not (repo_path / ".git").exists():
            shutil.rmtree(repo_path, ignore_errors=True)
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="repo_path_cleanup",
                    status="ok",
                    detail={
                        "reason": "清理不完整的历史 clone 目录",
                        "repo_path": str(repo_path),
                    },
                )
            )
        self._run_git_with_retry(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--single-branch",
                "--branch",
                safe_branch,
                auth_url,
                str(repo_path),
            ],
            cwd=cache_root,
            audit_log=audit_log,
            action="git_clone",
            repo_url=safe_url,
            timeout_plan=GIT_CLONE_TIMEOUTS,
        )
        return str(repo_path)

    def _run_git(
        self,
        cmd: List[str],
        cwd: Path,
        *,
        audit_log: List[Dict[str, Any]],
        action: str,
        repo_url: str,
        timeout_seconds: int,
    ) -> None:
        started = datetime.utcnow()
        safe_cmd = [self._sanitize_command_part(item) for item in cmd]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=max(10, int(timeout_seconds)),
                check=False,
                env=self._git_env(),
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            audit_log.append(
                self._audit(
                    tool_name="git_repo_search",
                    action="git_command",
                    status="timeout",
                    detail={
                        "action": action,
                        "cwd": str(cwd),
                        "command": " ".join(safe_cmd),
                        "repo_url": repo_url,
                        "timeout_seconds": int(timeout_seconds),
                        "duration_ms": duration_ms,
                    },
                )
            )
            logger.warning(
                "tool_git_command_timeout",
                action=action,
                cwd=str(cwd),
                command=" ".join(safe_cmd),
                repo_url=repo_url,
                timeout_seconds=int(timeout_seconds),
                duration_ms=duration_ms,
            )
            raise RuntimeError(
                f"git 命令超时({int(timeout_seconds)}s): {' '.join(safe_cmd)}"
            ) from exc

        duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
        detail = {
            "action": action,
            "cwd": str(cwd),
            "command": " ".join(safe_cmd),
            "repo_url": repo_url,
            "return_code": proc.returncode,
            "duration_ms": duration_ms,
            "stdout_preview": str(proc.stdout or "").strip()[:300],
            "stderr_preview": str(proc.stderr or "").strip()[:300],
        }
        audit_log.append(
            self._audit(
                tool_name="git_repo_search",
                action="git_command",
                status="ok" if proc.returncode == 0 else "error",
                detail=detail,
            )
        )
        logger.info(
            "tool_git_command",
            action=action,
            cwd=str(cwd),
            command=" ".join(safe_cmd),
            repo_url=repo_url,
            return_code=proc.returncode,
            duration_ms=duration_ms,
            stdout_preview=str(proc.stdout or "").strip()[:120],
            stderr_preview=str(proc.stderr or "").strip()[:120],
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git command failed")

    def _run_git_with_retry(
        self,
        cmd: List[str],
        *,
        cwd: Path,
        audit_log: List[Dict[str, Any]],
        action: str,
        repo_url: str,
        timeout_plan: tuple[int, ...],
    ) -> None:
        last_error: Optional[Exception] = None
        for index, timeout_seconds in enumerate(timeout_plan, start=1):
            try:
                self._run_git(
                    cmd,
                    cwd=cwd,
                    audit_log=audit_log,
                    action=action,
                    repo_url=repo_url,
                    timeout_seconds=int(timeout_seconds),
                )
                return
            except Exception as exc:
                last_error = exc
                audit_log.append(
                    self._audit(
                        tool_name="git_repo_search",
                        action="git_retry",
                        status="retrying" if index < len(timeout_plan) else "failed",
                        detail={
                            "operation": action,
                            "attempt": index,
                            "max_attempts": len(timeout_plan),
                            "timeout_seconds": int(timeout_seconds),
                            "error": str(exc)[:400],
                        },
                    )
                )
                if index < len(timeout_plan):
                    continue
        raise RuntimeError(str(last_error) if last_error else f"{action} failed")

    def _git_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env.setdefault("GIT_ASKPASS", "echo")
        return env

    def _inject_token(self, repo_url: str, token: str) -> str:
        raw = str(repo_url or "").strip()
        tk = str(token or "").strip()
        if not tk:
            return raw
        parts = urlsplit(raw)
        if parts.scheme not in {"http", "https"}:
            return raw
        if "@" in parts.netloc:
            return raw
        netloc = f"oauth2:{tk}@{parts.netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def _decide_tool_invocation(
        self,
        *,
        agent_name: str,
        assigned_command: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        command = dict(assigned_command or {})
        text_fields = [
            str(command.get("task") or "").strip(),
            str(command.get("focus") or "").strip(),
            str(command.get("expected_output") or "").strip(),
        ]
        has_command = bool(any(text_fields)) or ("use_tool" in command)
        if not has_command:
            return {
                "agent_name": agent_name,
                "has_command": False,
                "allow_tool": False,
                "reason": "未收到主Agent命令",
                "decision_source": "no_command",
            }

        use_tool_raw = command.get("use_tool")
        if isinstance(use_tool_raw, bool):
            return {
                "agent_name": agent_name,
                "has_command": True,
                "allow_tool": use_tool_raw,
                "reason": "主Agent命令显式指定工具开关",
                "decision_source": "explicit_boolean",
            }

        merged = " ".join(text_fields).lower()
        disable_terms = ("无需工具", "不要调用工具", "禁止调用工具", "仅基于现有信息", "不查日志", "不查代码", "不查责任田")
        if any(term in merged for term in disable_terms):
            return {
                "agent_name": agent_name,
                "has_command": True,
                "allow_tool": False,
                "reason": "主Agent命令要求不调用工具",
                "decision_source": "command_text_negative",
            }

        enable_terms = ("读取日志", "查询日志", "检索代码", "搜索仓库", "查责任田", "excel", "csv", "git", "repo")
        if any(term in merged for term in enable_terms):
            return {
                "agent_name": agent_name,
                "has_command": True,
                "allow_tool": True,
                "reason": "主Agent命令要求外部证据检索",
                "decision_source": "command_text_positive",
            }

        return {
            "agent_name": agent_name,
            "has_command": True,
            "allow_tool": True,
            "reason": "收到主Agent命令，按Agent默认工具策略执行",
            "decision_source": "command_default",
        }

    def _command_preview(self, assigned_command: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        command = dict(assigned_command or {})
        return {
            "task": str(command.get("task") or "")[:240],
            "focus": str(command.get("focus") or "")[:240],
            "expected_output": str(command.get("expected_output") or "")[:240],
            "use_tool": command.get("use_tool"),
        }

    def _audit(
        self,
        *,
        tool_name: str,
        action: str,
        status: str,
        detail: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "tool_name": tool_name,
            "action": action,
            "status": status,
            "detail": detail,
        }

    def _sanitize_command_part(self, item: str) -> str:
        text = str(item or "")
        masked = self._mask_url_secret(text)
        return re.sub(r"(?i)(token|apikey|api_key|access_token)=([^&\s]+)", r"\1=***", masked)

    def _mask_url_secret(self, raw_url: str) -> str:
        raw = str(raw_url or "").strip()
        if not raw:
            return raw
        try:
            parts = urlsplit(raw)
        except Exception:
            return raw
        if not parts.scheme or not parts.netloc:
            return raw
        netloc = parts.netloc
        if "@" in netloc:
            userinfo, host = netloc.rsplit("@", 1)
            username = userinfo.split(":", 1)[0] if userinfo else "user"
            netloc = f"{username}:***@{host}"
        safe_query = re.sub(r"(?i)(token|apikey|api_key|access_token)=([^&]+)", r"\1=***", parts.query or "")
        return urlunsplit((parts.scheme, netloc, parts.path, safe_query, parts.fragment))

    def _extract_keywords(
        self,
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
        assigned_command: Optional[Dict[str, Any]],
    ) -> List[str]:
        bucket: List[str] = []
        endpoint = (((compact_context.get("interface_mapping") or {}).get("endpoint") or {}) if isinstance(compact_context.get("interface_mapping"), dict) else {})
        for key in ("path", "service", "interface", "method"):
            value = str(endpoint.get(key) or "").strip()
            if value:
                bucket.append(value)
        parsed = compact_context.get("parsed_data") or {}
        if isinstance(parsed, dict):
            for key in ("error_type", "error_message", "exception_class", "trace_id"):
                value = str(parsed.get(key) or "").strip()
                if value:
                    bucket.append(value)
        log_excerpt = str(compact_context.get("log_excerpt") or "")
        if log_excerpt:
            bucket.append(log_excerpt[:300])
        for key in ("task", "focus", "expected_output"):
            value = str((assigned_command or {}).get(key) or "").strip()
            if value:
                bucket.append(value)
        full_log = str(incident_context.get("log_content") or "")
        if full_log:
            bucket.append(full_log[:500])

        tokens: List[str] = []
        for raw in bucket:
            for token in re.split(r"[\s,;:|/\\\[\]\(\)\{\}\"'`]+", raw):
                tk = token.strip().lower()
                if len(tk) < 3:
                    continue
                if tk.isdigit():
                    continue
                if tk in {"http", "https", "error", "warn", "info", "debug"}:
                    continue
                tokens.append(tk[:80])
        deduped = list(dict.fromkeys(tokens))
        return deduped[:12]

    def _search_repo(
        self,
        repo_path: str,
        keywords: List[str],
        max_hits: int,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        path = Path(repo_path)
        if not path.exists():
            return [], {"repo_path": repo_path, "files_scanned": 0, "hits": 0}
        hits: List[Dict[str, Any]] = []
        scanned_files = 0
        matched_files = 0
        lowered_keywords = [k.lower() for k in keywords if k]
        if not lowered_keywords:
            lowered_keywords = ["exception", "error", "timeout", "order"]

        for file in path.rglob("*"):
            if len(hits) >= max_hits:
                break
            if not file.is_file():
                continue
            if any(part in {".git", "node_modules", "dist", "build", "__pycache__"} for part in file.parts):
                continue
            if file.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            scanned_files += 1
            try:
                content = file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            file_hit = False
            for index, line in enumerate(content.splitlines(), start=1):
                line_low = line.lower()
                keyword = next((kw for kw in lowered_keywords if kw in line_low), "")
                if not keyword:
                    continue
                file_hit = True
                hits.append(
                    {
                        "file": str(file.relative_to(path)),
                        "line": index,
                        "keyword": keyword,
                        "snippet": line.strip()[:220],
                    }
                )
                if len(hits) >= max_hits:
                    break
            if file_hit:
                matched_files += 1
        return hits, {
            "repo_path": str(path),
            "files_scanned": scanned_files,
            "files_with_hits": matched_files,
            "hits": len(hits),
            "keywords": lowered_keywords[:8],
        }

    def _read_log_excerpt(
        self,
        path: Path,
        max_lines: int,
        keywords: Iterable[str],
    ) -> tuple[str, int, Dict[str, Any]]:
        kw = [k.lower() for k in keywords if k]
        window = deque(maxlen=max(50, max_lines))
        scanned_lines = 0
        matched_lines = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                scanned_lines += 1
                text = line.rstrip("\n")
                if not kw or any(item in text.lower() for item in kw):
                    matched_lines += 1
                    window.append(text)
        if not window:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    window.append(line.rstrip("\n"))
        lines = list(window)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return (
            "\n".join(lines),
            len(lines),
            {
                "file_path": str(path),
                "scanned_lines": scanned_lines,
                "matched_lines": matched_lines,
                "returned_lines": len(lines),
                "keywords": kw[:10],
            },
        )

    def _lookup_domain_file(
        self,
        path: Path,
        sheet_name: str,
        max_rows: int,
        max_matches: int,
        keywords: List[str],
    ) -> Dict[str, Any]:
        suffix = path.suffix.lower()
        sheet_used = ""
        if suffix == ".csv":
            rows = self._read_csv_rows(path, max_rows=max_rows)
        elif suffix in {".xlsx", ".xlsm"}:
            rows, sheet_used = self._read_xlsx_rows(path, sheet_name=sheet_name, max_rows=max_rows)
        else:
            raise RuntimeError("仅支持 .csv/.xlsx/.xlsm")

        lowered = [k.lower() for k in keywords if k]
        matches: List[Dict[str, Any]] = []
        for row in rows:
            merged = " | ".join(str(v) for v in row.values()).lower()
            if lowered and not any(k in merged for k in lowered):
                continue
            matches.append(row)
            if len(matches) >= max_matches:
                break
        if not lowered:
            matches = rows[:max_matches]
        return {
            "format": suffix,
            "sheet_used": sheet_used,
            "row_count": len(rows),
            "matches": matches,
        }

    def _read_csv_rows(self, path: Path, max_rows: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for idx, row in enumerate(reader, start=1):
                rows.append({str(k): str(v) for k, v in (row or {}).items()})
                if idx >= max_rows:
                    break
        return rows

    def _read_xlsx_rows(self, path: Path, sheet_name: str, max_rows: int) -> tuple[List[Dict[str, Any]], str]:
        try:
            from openpyxl import load_workbook  # type: ignore
        except Exception as exc:
            raise RuntimeError("读取 xlsx 需要安装 openpyxl") from exc
        wb = load_workbook(filename=str(path), read_only=True, data_only=True)
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb[wb.sheetnames[0]]
        rows_iter = ws.iter_rows(values_only=True)
        headers_raw = next(rows_iter, None) or []
        headers = [str(h or f"col_{i+1}") for i, h in enumerate(headers_raw)]
        rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows_iter, start=1):
            rows.append({headers[i]: str(value or "") for i, value in enumerate(row or []) if i < len(headers)})
            if idx >= max_rows:
                break
        wb.close()
        return rows, str(ws.title or "")


agent_tool_context_service = AgentToolContextService()
