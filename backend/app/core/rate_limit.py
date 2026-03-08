"""
限流中间件模块

本模块实现基于滑动窗口的请求限流功能。

限流策略：
- 基于客户端 IP 和路径的组合键
- 滑动窗口算法，窗口大小 60 秒
- 可配置每分钟最大请求数

工作流程：
1. 请求到达 -> 检查限流
2. 计算窗口内请求数
3. 超过限制返回 429，否则放行

使用场景：
- API 请求限流
- 防止恶意请求
- 保护后端服务

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
    """
    基于滑动窗口的限流中间件

    对每个客户端 IP + 路径组合进行独立限流。
    使用滑动窗口算法，精确控制请求速率。

    属性：
    - _requests: 请求时间戳存储，键为 "{client_ip}:{path}"
    - _limit: 每分钟最大请求数
    - _window_seconds: 滑动窗口大小（秒）

    排除路径：
    - /: 首页
    - /health: 健康检查
    - /docs: API 文档
    - /redoc: ReDoc 文档
    - /openapi.json: OpenAPI 规范
    """

    def __init__(self, app):
        """
        初始化限流中间件

        Args:
            app: FastAPI 应用实例
        """
        super().__init__(app)
        # 请求时间戳队列，按 IP + 路径分组
        self._requests: Dict[str, Deque[float]] = defaultdict(deque)
        # 从配置读取限流参数
        self._limit = settings.RATE_LIMIT_REQUESTS_PER_MINUTE
        self._window_seconds = 60.0

    async def dispatch(self, request, call_next):
        """
        请求分发处理

        执行限流检查：
        1. 检查是否启用限流
        2. 检查是否为排除路径
        3. 清理过期请求
        4. 检查是否超过限制
        5. 记录请求时间戳

        Args:
            request: 请求对象
            call_next: 下一个中间件或路由处理函数

        Returns:
            Response: 限流返回 429，否则返回正常响应
        """
        # 检查是否启用限流
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # 排除不需要限流的路径
        path = request.url.path
        if path in {"/", "/health", "/docs", "/redoc", "/openapi.json"}:
            return await call_next(request)

        # 构建限流键：客户端 IP + 路径
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{path}"
        now = time.time()
        bucket = self._requests[key]

        # 滑动窗口：移除窗口外的过期请求
        while bucket and now - bucket[0] > self._window_seconds:
            bucket.popleft()

        # 检查是否超过限制
        if len(bucket) >= self._limit:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "limit_per_minute": self._limit,
                },
            )

        # 记录当前请求时间戳
        bucket.append(now)
        return await call_next(request)