"""Database tool-context provider."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.tool_context.result import ToolContextResult

try:
    import asyncpg
except Exception:  # pragma: no cover - optional dependency
    asyncpg = None  # type: ignore[assignment]


async def build_database_context(
    service: Any,
    *,
    cfg: Any,
    compact_context: Dict[str, Any],
    incident_context: Dict[str, Any],
    assigned_command: Optional[Dict[str, Any]],
    command_gate: Dict[str, Any],
) -> ToolContextResult:
    """Build DatabaseAgent tool context from sqlite/postgres snapshot."""
    tool_cfg = getattr(cfg, "database", None)
    audit_log: List[Dict[str, Any]] = [
        service._audit(  # noqa: SLF001
            tool_name="db_snapshot_reader",
            action="command_gate",
            status="ok" if command_gate.get("allow_tool") else "skipped",
            detail={
                "reason": str(command_gate.get("reason") or ""),
                "has_command": bool(command_gate.get("has_command")),
                "decision_source": str(command_gate.get("decision_source") or ""),
                "command_preview": service._command_preview(assigned_command),  # noqa: SLF001
            },
        )
    ]
    if not tool_cfg or not bool(getattr(tool_cfg, "enabled", False)):
        return ToolContextResult(
            name="db_snapshot_reader",
            enabled=False,
            used=False,
            status="disabled",
            summary="DatabaseAgent 数据库工具开关已关闭，使用默认分析逻辑。",
            data={},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="db_snapshot_reader",
                    action="config_check",
                    status="disabled",
                    detail={"enabled": False},
                ),
            ],
        )
    if not bool(command_gate.get("allow_tool")):
        return ToolContextResult(
            name="db_snapshot_reader",
            enabled=True,
            used=False,
            status="skipped_by_command",
            summary=f"主Agent命令未要求 DatabaseAgent 调用数据库工具：{str(command_gate.get('reason') or '未授权工具调用')}",
            data={"command_preview": service._command_preview(assigned_command)},  # noqa: SLF001
            command_gate=command_gate,
            audit_log=audit_log,
        )
    try:
        engine = str(getattr(tool_cfg, "engine", "sqlite") or "sqlite").strip().lower()
        max_rows = int(getattr(tool_cfg, "max_rows", 50) or 50)
        timeout_seconds = int(getattr(tool_cfg, "connect_timeout_seconds", 8) or 8)
        keywords = service._extract_keywords(compact_context, incident_context, assigned_command)  # noqa: SLF001
        mapped_tables = service._extract_database_tables(compact_context, incident_context, assigned_command)  # noqa: SLF001
        if engine in {"postgresql", "postgres", "pg"}:
            dsn = str(getattr(tool_cfg, "postgres_dsn", "") or "").strip()
            schema = str(getattr(tool_cfg, "pg_schema", "public") or "public").strip() or "public"
            if not dsn:
                return ToolContextResult(
                    name="db_snapshot_reader",
                    enabled=True,
                    used=False,
                    status="unavailable",
                    summary="PostgreSQL DSN 未配置，已回退默认分析逻辑。",
                    data={"engine": "postgresql"},
                    command_gate=command_gate,
                    audit_log=[
                        *audit_log,
                        service._audit(  # noqa: SLF001
                            tool_name="db_snapshot_reader",
                            action="config_check",
                            status="unavailable",
                            detail={"engine": "postgresql", "reason": "postgres_dsn empty"},
                        ),
                    ],
                )
            if asyncpg is None:
                return ToolContextResult(
                    name="db_snapshot_reader",
                    enabled=True,
                    used=False,
                    status="error",
                    summary="未安装 asyncpg，无法连接 PostgreSQL，请先安装依赖。",
                    data={"engine": "postgresql", "error": "asyncpg not installed"},
                    command_gate=command_gate,
                    audit_log=[
                        *audit_log,
                        service._audit(  # noqa: SLF001
                            tool_name="db_snapshot_reader",
                            action="dependency_check",
                            status="error",
                            detail={"engine": "postgresql", "reason": "asyncpg missing"},
                        ),
                    ],
                )
            snapshot = await service._collect_postgres_snapshot(  # noqa: SLF001
                dsn=dsn,
                schema=schema,
                max_rows=max_rows,
                keywords=keywords,
                target_tables=mapped_tables,
                timeout_seconds=timeout_seconds,
            )
            query_action = "postgres_query"
            query_detail: Dict[str, Any] = {
                "engine": "postgresql",
                "schema": schema,
                "max_rows": max_rows,
                "requested_tables": mapped_tables[:12],
                "table_count": int(snapshot.get("table_count") or 0),
                "slow_sql_count": len(list(snapshot.get("slow_sql") or [])),
                "top_sql_count": len(list(snapshot.get("top_sql") or [])),
                "session_count": len(list(snapshot.get("session_status") or [])),
            }
        else:
            db_path = Path(str(getattr(tool_cfg, "db_path", "") or "").strip())
            if not db_path.exists() or not db_path.is_file():
                return ToolContextResult(
                    name="db_snapshot_reader",
                    enabled=True,
                    used=False,
                    status="unavailable",
                    summary="SQLite 快照文件路径不可用，已回退默认分析逻辑。",
                    data={"engine": "sqlite", "db_path": str(db_path)},
                    command_gate=command_gate,
                    audit_log=[
                        *audit_log,
                        service._audit(  # noqa: SLF001
                            tool_name="db_snapshot_reader",
                            action="file_check",
                            status="unavailable",
                            detail={"engine": "sqlite", "db_path": str(db_path)},
                        ),
                    ],
                )
            snapshot = await asyncio.to_thread(
                service._collect_database_snapshot,  # noqa: SLF001
                db_path,
                max_rows,
                keywords,
                mapped_tables,
            )
            query_action = "sqlite_query"
            query_detail = {
                "engine": "sqlite",
                "db_path": str(db_path),
                "max_rows": max_rows,
                "requested_tables": mapped_tables[:12],
                "table_count": int(snapshot.get("table_count") or 0),
                "slow_sql_count": len(list(snapshot.get("slow_sql") or [])),
                "top_sql_count": len(list(snapshot.get("top_sql") or [])),
                "session_count": len(list(snapshot.get("session_status") or [])),
            }
        audit_log.append(
            service._audit(  # noqa: SLF001
                tool_name="db_snapshot_reader",
                action=query_action,
                status="ok",
                detail=query_detail,
            )
        )
        return ToolContextResult(
            name="db_snapshot_reader",
            enabled=True,
            used=True,
            status="ok",
            summary=(
                f"数据库快照读取完成，表 {snapshot.get('table_count', 0)} 个，"
                f"慢SQL {len(list(snapshot.get('slow_sql') or []))} 条。"
            ),
            data=snapshot,
            command_gate=command_gate,
            audit_log=audit_log,
        )
    except Exception as exc:
        error_text = str(exc).strip() or exc.__class__.__name__
        return ToolContextResult(
            name="db_snapshot_reader",
            enabled=True,
            used=False,
            status="error",
            summary=f"数据库快照读取失败：{error_text}，已回退默认分析。",
            data={"error": error_text},
            command_gate=command_gate,
            audit_log=[
                *audit_log,
                service._audit(  # noqa: SLF001
                    tool_name="db_snapshot_reader",
                    action="tool_execute",
                    status="error",
                    detail={"error": error_text},
                ),
            ],
        )
