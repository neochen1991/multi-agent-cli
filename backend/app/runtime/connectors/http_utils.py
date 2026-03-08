"""
HTTP 工具模块

本模块提供连接器使用的共享 HTTP 辅助函数。

核心功能：
1. HTTP GET 请求
2. JSON 响应解析
3. 错误处理
4. 请求元数据返回

使用场景：
- 各连接器调用外部 API
- 获取监控数据
- 查询日志平台

特点：
- 异步执行（使用 asyncio.to_thread）
- 超时控制
- 认证支持
- 元数据可选返回

Shared HTTP helpers for connector stubs.
"""

from __future__ import annotations

import asyncio
import json
from time import perf_counter
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


async def http_get_json(
    *,
    url: str,
    token: str = "",
    timeout_seconds: int = 8,
    include_meta: bool = False,
) -> Dict[str, Any]:
    """
    异步 HTTP GET 请求获取 JSON

    执行 HTTP GET 请求并解析 JSON 响应。

    流程：
    1. 构建请求头（认证、User-Agent）
    2. 发送请求（带超时）
    3. 解析响应
    4. 可选返回元数据

    Args:
        url: 请求 URL
        token: 认证令牌（Bearer Token）
        timeout_seconds: 超时时间（秒）
        include_meta: 是否包含请求元数据

    Returns:
        Dict[str, Any]: 响应数据（或包含元数据的字典）

    Raises:
        RuntimeError: HTTP 错误或 URL 错误

    Example:
        >>> data = await http_get_json(
        ...     url="https://api.example.com/data",
        ...     token="secret",
        ...     include_meta=True
        ... )
        >>> print(data["request_meta"]["latency_ms"])
    """
    def _request() -> Dict[str, Any]:
        """
        同步执行 HTTP 请求

        内部函数，在独立线程中执行。

        Returns:
            Dict[str, Any]: 响应数据
        """
        # 构建请求头
        headers = {
            "Accept": "application/json",
            "User-Agent": "sre-debate-connector/1.0",
        }
        tk = str(token or "").strip()
        if tk:
            headers["Authorization"] = f"Bearer {tk}"

        started = perf_counter()
        req = Request(url=str(url), method="GET", headers=headers)

        # 发送请求
        with urlopen(req, timeout=max(1, int(timeout_seconds))) as resp:  # nosec B310
            status_code = int(getattr(resp, "status", 200) or 200)
            raw = resp.read().decode("utf-8", errors="ignore")

            # 解析响应
            if not raw.strip():
                payload: Dict[str, Any] = {}
            else:
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = {"raw_text": raw[:4000]}
                payload = parsed if isinstance(parsed, dict) else {"data": parsed}

            # 是否包含元数据
            if not include_meta:
                return payload

            return {
                "data": payload,
                "request_meta": {
                    "url": str(url),
                    "method": "GET",
                    "status_code": status_code,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                    "retry_count": 0,
                    "status": "ok",
                },
            }

    try:
        return await asyncio.to_thread(_request)
    except HTTPError as exc:
        raise RuntimeError(f"http_error:{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"url_error:{str(exc.reason)}") from exc