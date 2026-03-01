"""
可观测性组件
Observability Components
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

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
        self.debate_total = 0
        self.debate_success_total = 0
        self.debate_timeout_total = 0
        self.debate_retry_total = 0
        self.debate_invalid_conclusion_total = 0
        self._debate_latencies_ms: List[int] = []
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
        debate_success_rate = (self.debate_success_total / self.debate_total) if self.debate_total else 0.0
        debate_timeout_rate = (self.debate_timeout_total / self.debate_total) if self.debate_total else 0.0
        debate_retry_rate = (self.debate_retry_total / self.debate_total) if self.debate_total else 0.0
        debate_invalid_conclusion_rate = (
            self.debate_invalid_conclusion_total / self.debate_total
            if self.debate_total
            else 0.0
        )
        p95_latency = self._percentile(self._debate_latencies_ms, 95)
        return {
            "request_total": self.request_total,
            "error_total": self.error_total,
            "error_rate": error_rate,
            "avg_latency_ms": avg_latency,
            "debate_slo": {
                "debate_total": self.debate_total,
                "success_total": self.debate_success_total,
                "success_rate": debate_success_rate,
                "p95_latency_ms": p95_latency,
                "timeout_total": self.debate_timeout_total,
                "timeout_rate": debate_timeout_rate,
                "retry_total": self.debate_retry_total,
                "retry_rate": debate_retry_rate,
                "invalid_conclusion_total": self.debate_invalid_conclusion_total,
                "invalid_conclusion_rate": debate_invalid_conclusion_rate,
            },
            "updated_at": self.updated_at,
        }

    def record_debate_result(
        self,
        *,
        status: str,
        latency_ms: int,
        retried: bool,
        timeout: bool,
        invalid_conclusion: bool,
    ) -> None:
        self.debate_total += 1
        if str(status).lower() == "completed":
            self.debate_success_total += 1
        if retried:
            self.debate_retry_total += 1
        if timeout:
            self.debate_timeout_total += 1
        if invalid_conclusion:
            self.debate_invalid_conclusion_total += 1
        latency_value = max(0, int(latency_ms or 0))
        self._debate_latencies_ms.append(latency_value)
        if len(self._debate_latencies_ms) > 5000:
            self._debate_latencies_ms = self._debate_latencies_ms[-5000:]
        self.updated_at = datetime.utcnow().isoformat()

    @staticmethod
    def _percentile(values: List[int], percentile: int) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        rank = (max(0, min(percentile, 100)) / 100) * (len(sorted_values) - 1)
        low = int(rank)
        high = min(low + 1, len(sorted_values) - 1)
        if low == high:
            return float(sorted_values[low])
        weight = rank - low
        return float(sorted_values[low] * (1 - weight) + sorted_values[high] * weight)


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
