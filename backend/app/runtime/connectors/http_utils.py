"""Shared HTTP helpers for connector stubs."""

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
    def _request() -> Dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "sre-debate-connector/1.0",
        }
        tk = str(token or "").strip()
        if tk:
            headers["Authorization"] = f"Bearer {tk}"
        started = perf_counter()
        req = Request(url=str(url), method="GET", headers=headers)
        with urlopen(req, timeout=max(1, int(timeout_seconds))) as resp:  # nosec B310
            status_code = int(getattr(resp, "status", 200) or 200)
            raw = resp.read().decode("utf-8", errors="ignore")
            if not raw.strip():
                payload: Dict[str, Any] = {}
            else:
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = {"raw_text": raw[:4000]}
                payload = parsed if isinstance(parsed, dict) else {"data": parsed}
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
