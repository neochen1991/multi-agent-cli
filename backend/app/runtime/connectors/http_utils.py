"""Shared HTTP helpers for connector stubs."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


async def http_get_json(
    *,
    url: str,
    token: str = "",
    timeout_seconds: int = 8,
) -> Dict[str, Any]:
    def _request() -> Dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "sre-debate-connector/1.0",
        }
        tk = str(token or "").strip()
        if tk:
            headers["Authorization"] = f"Bearer {tk}"
        req = Request(url=str(url), method="GET", headers=headers)
        with urlopen(req, timeout=max(1, int(timeout_seconds))) as resp:  # nosec B310
            raw = resp.read().decode("utf-8", errors="ignore")
            if not raw.strip():
                return {}
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"raw_text": raw[:4000]}
            return payload if isinstance(payload, dict) else {"data": payload}

    try:
        return await asyncio.to_thread(_request)
    except HTTPError as exc:
        raise RuntimeError(f"http_error:{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"url_error:{str(exc.reason)}") from exc
