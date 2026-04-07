"""本地日志文件 MCP Server（stdio）。

启动方式示例：
python -m app.runtime.mcp.local_log_server

通过环境变量控制：
- MCP_LOG_FILE_PATH: 日志文件路径
- MCP_LOG_MAX_LINES: 默认最大返回行数
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple


def _env_text(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(_env_text(name, str(default))))
    except Exception:
        return default


def _read_lines(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []


def _search_lines(lines: List[str], keyword: str, limit: int) -> List[Tuple[int, str]]:
    key = str(keyword or "").strip().lower()
    if not key:
        return []
    matched: List[Tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        if key in line.lower():
            matched.append((idx, line))
        if len(matched) >= limit:
            break
    return matched


def _build_tools() -> List[Dict[str, Any]]:
    # 中文注释：提供 query_logs 为主工具，兼容 mcp_service 的自动工具选择逻辑（logs/query 关键字）。
    return [
        {
            "name": "query_logs",
            "description": "根据 query 在本地日志文件中检索匹配行并返回尾部上下文。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_lines": {"type": "integer"},
                    "tail_lines": {"type": "integer"},
                },
            },
        },
        {
            "name": "read_log_tail",
            "description": "读取本地日志文件尾部行。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tail_lines": {"type": "integer"},
                },
            },
        },
    ]


def _handle_call(name: str, args: Dict[str, Any], lines: List[str], log_path: str, default_max: int) -> Dict[str, Any]:
    if name == "read_log_tail":
        tail_lines = max(1, int(args.get("tail_lines") or min(default_max, 120)))
        tail = lines[-tail_lines:] if lines else []
        text = "\n".join(tail)
        return {
            "content": [{"type": "text", "text": text[:12000]}],
            "structuredContent": {
                "log_path": log_path,
                "tail_lines": tail_lines,
                "returned_lines": len(tail),
            },
        }

    if name == "query_logs":
        query = str(args.get("query") or "").strip()
        max_lines = max(1, int(args.get("max_lines") or min(default_max, 120)))
        tail_lines = max(1, int(args.get("tail_lines") or min(default_max, 80)))
        hits = _search_lines(lines, query, max_lines)
        tail = lines[-tail_lines:] if lines else []
        hit_text = "\n".join([f"{line_no}: {line}" for line_no, line in hits])[:12000]
        tail_text = "\n".join(tail)[:12000]
        merged = f"[query={query}] 命中 {len(hits)} 行\n\n{hit_text}\n\n[tail]\n{tail_text}".strip()
        return {
            "content": [{"type": "text", "text": merged[:12000]}],
            "structuredContent": {
                "log_path": log_path,
                "query": query,
                "match_count": len(hits),
                "matches": [{"line": line_no, "text": line[:500]} for line_no, line in hits],
                "tail_lines": tail_lines,
            },
        }

    return {
        "isError": True,
        "content": [{"type": "text", "text": f"unknown tool: {name}"}],
    }


def main() -> int:
    log_path = _env_text("MCP_LOG_FILE_PATH")
    max_lines = _env_int("MCP_LOG_MAX_LINES", 300)
    tools = _build_tools()
    for raw in sys.stdin:
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method = str(req.get("method") or "")
        req_id = req.get("id")

        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "local-log-mcp", "version": "0.1.0"},
            }
            print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, ensure_ascii=False), flush=True)
            continue

        if method == "notifications/initialized":
            continue

        if method == "tools/list":
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            continue

        if method == "tools/call":
            params = req.get("params") or {}
            tool_name = str((params or {}).get("name") or "")
            args = (params or {}).get("arguments") or {}
            lines = _read_lines(Path(log_path)) if log_path else []
            result = _handle_call(tool_name, args if isinstance(args, dict) else {}, lines, log_path, max_lines)
            print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, ensure_ascii=False), flush=True)
            continue

        if req_id is not None:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"method not found: {method}"},
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

