"""
限流中间件
Rate Limit Middleware
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于滑动窗口的简单限流"""

    def __init__(self, app):
        super().__init__(app)
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)
        self._limit = settings.RATE_LIMIT_REQUESTS_PER_MINUTE
        self._window_seconds = 60.0

    async def dispatch(self, request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        path = request.url.path
        if path in {"/", "/health", "/docs", "/redoc", "/openapi.json"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{path}"
        now = time.time()
        bucket = self._requests[key]

        while bucket and now - bucket[0] > self._window_seconds:
            bucket.popleft()

        if len(bucket) >= self._limit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "limit_per_minute": self._limit,
                },
            )

        bucket.append(now)
        return await call_next(request)

