"""
可观测性组件
Observability Components
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Dict

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = structlog.get_logger()


class MetricsStore:
    def __init__(self):
        self.request_total = 0
        self.error_total = 0
        self.path_counts: Dict[str, int] = defaultdict(int)
        self.path_latency_ms: Dict[str, float] = defaultdict(float)
        self.updated_at = datetime.utcnow().isoformat()

    def record(self, path: str, latency_ms: float, status_code: int):
        self.request_total += 1
        self.path_counts[path] += 1
        self.path_latency_ms[path] += latency_ms
        if status_code >= 500:
            self.error_total += 1
        self.updated_at = datetime.utcnow().isoformat()

    def snapshot(self):
        avg_latency = {
            p: (self.path_latency_ms[p] / self.path_counts[p])
            for p in self.path_counts
            if self.path_counts[p] > 0
        }
        error_rate = (self.error_total / self.request_total) if self.request_total else 0.0
        return {
            "request_total": self.request_total,
            "error_total": self.error_total,
            "error_rate": error_rate,
            "avg_latency_ms": avg_latency,
            "updated_at": self.updated_at,
        }


metrics_store = MetricsStore()


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        metrics_store.record(request.url.path, elapsed, response.status_code)
        alert_manager.check_and_alert()
        return response


class AlertManager:
    def check_and_alert(self):
        snapshot = metrics_store.snapshot()
        error_rate = snapshot["error_rate"]
        if error_rate >= settings.ALERT_ERROR_RATE_THRESHOLD and snapshot["request_total"] >= 20:
            logger.warning(
                "high_error_rate_detected",
                error_rate=error_rate,
                threshold=settings.ALERT_ERROR_RATE_THRESHOLD,
                request_total=snapshot["request_total"],
            )


alert_manager = AlertManager()
