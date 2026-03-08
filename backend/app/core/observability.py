"""
可观测性组件模块

本模块提供系统的可观测性功能，包括：
1. 指标收集和存储
2. HTTP 请求监控中间件
3. 告警管理

核心组件：
- MetricsStore: 指标存储，记录请求、延迟、错误等
- MetricsMiddleware: 指标收集中间件
- AlertManager: 告警管理器

指标类型：
- 请求指标：总数、错误数、延迟
- 辩论指标：成功率、超时率、重试率、P95 延迟

使用场景：
- API 性能监控
- 辩论质量监控
- 系统健康告警

Observability Components
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = structlog.get_logger()

# 北京时区，用于统一时间显示
_BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_timestamp_processor(_, __, event_dict):
    """
    北京时间戳处理器

    为日志事件添加北京时间戳，便于跨系统时间对齐。

    Args:
        _: logger 实例（未使用）
        __: 日志级别（未使用）
        event_dict: 日志事件字典

    Returns:
        dict: 添加了 timestamp_bj 字段的日志事件
    """
    event_dict.setdefault("timestamp_bj", datetime.now(_BEIJING_TZ).isoformat())
    return event_dict


class MetricsStore:
    """
    指标存储器

    存储和聚合系统指标，支持：
    - HTTP 请求统计
    - 辩论执行统计
    - 延迟分布计算

    指标分类：
    1. 请求指标
       - request_total: 总请求数
       - error_total: 错误请求数
       - path_counts: 按路径统计
       - path_latency_ms: 按路径延迟累计

    2. 辩论指标
       - debate_total: 辩论总数
       - debate_success_total: 成功数
       - debate_timeout_total: 超时数
       - debate_retry_total: 重试数
       - debate_invalid_conclusion_total: 无效结论数

    属性：
    - request_total: 请求总数
    - error_total: 错误总数
    - path_counts: 路径请求计数
    - path_latency_ms: 路径延迟累计
    - debate_*: 辩论相关指标
    """

    def __init__(self):
        """
        初始化指标存储器

        所有指标初始化为零值。
        """
        # 请求指标
        self.request_total = 0
        self.error_total = 0
        self.path_counts: Dict[str, int] = defaultdict(int)
        self.path_latency_ms: Dict[str, float] = defaultdict(float)

        # 辩论指标
        self.debate_total = 0
        self.debate_success_total = 0
        self.debate_timeout_total = 0
        self.debate_retry_total = 0
        self.debate_invalid_conclusion_total = 0
        self._debate_latencies_ms: List[int] = []

        # 更新时间
        self.updated_at = datetime.utcnow().isoformat()

    def record(self, path: str, latency_ms: float, status_code: int):
        """
        记录 HTTP 请求

        更新请求相关指标，包括：
        - 请求计数
        - 路径计数
        - 路径延迟
        - 错误计数（状态码 >= 500）

        Args:
            path: 请求路径
            latency_ms: 响应延迟（毫秒）
            status_code: HTTP 状态码
        """
        self.request_total += 1
        self.path_counts[path] += 1
        self.path_latency_ms[path] += latency_ms

        # 5xx 错误计入错误总数
        if status_code >= 500:
            self.error_total += 1

        self.updated_at = datetime.utcnow().isoformat()

    def snapshot(self):
        """
        生成指标快照

        计算并返回当前指标的聚合视图，包括：
        - 请求统计（总数、错误率、平均延迟）
        - 辩论 SLO（成功率、超时率、P95 延迟）

        Returns:
            dict: 指标快照字典
        """
        # 计算各路径平均延迟
        avg_latency = {
            p: (self.path_latency_ms[p] / self.path_counts[p])
            for p in self.path_counts
            if self.path_counts[p] > 0
        }

        # 计算错误率
        error_rate = (self.error_total / self.request_total) if self.request_total else 0.0

        # 计算辩论相关比率
        debate_success_rate = (self.debate_success_total / self.debate_total) if self.debate_total else 0.0
        debate_timeout_rate = (self.debate_timeout_total / self.debate_total) if self.debate_total else 0.0
        debate_retry_rate = (self.debate_retry_total / self.debate_total) if self.debate_total else 0.0
        debate_invalid_conclusion_rate = (
            self.debate_invalid_conclusion_total / self.debate_total
            if self.debate_total
            else 0.0
        )

        # 计算 P95 延迟
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
        """
        记录辩论执行结果

        更新辩论相关指标，用于计算辩论质量 SLO。

        Args:
            status: 辩论状态（"completed" 表示成功）
            latency_ms: 执行延迟（毫秒）
            retried: 是否发生过重试
            timeout: 是否超时
            invalid_conclusion: 结论是否无效
        """
        self.debate_total += 1

        # 成功计数
        if str(status).lower() == "completed":
            self.debate_success_total += 1

        # 重试计数
        if retried:
            self.debate_retry_total += 1

        # 超时计数
        if timeout:
            self.debate_timeout_total += 1

        # 无效结论计数
        if invalid_conclusion:
            self.debate_invalid_conclusion_total += 1

        # 记录延迟（用于计算 P95）
        latency_value = max(0, int(latency_ms or 0))
        self._debate_latencies_ms.append(latency_value)

        # 限制延迟列表大小，防止内存膨胀
        if len(self._debate_latencies_ms) > 5000:
            self._debate_latencies_ms = self._debate_latencies_ms[-5000:]

        self.updated_at = datetime.utcnow().isoformat()

    @staticmethod
    def _percentile(values: List[int], percentile: int) -> float:
        """
        计算分位数

        使用线性插值法计算分位数值。

        Args:
            values: 数值列表
            percentile: 分位数（0-100）

        Returns:
            float: 分位数值
        """
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


# 全局指标存储实例
metrics_store = MetricsStore()


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    指标收集中间件

    拦截所有 HTTP 请求，收集指标数据。

    工作流程：
    1. 记录请求开始时间
    2. 执行请求
    3. 计算延迟
    4. 记录指标
    5. 检查告警条件
    """

    async def dispatch(self, request, call_next):
        """
        请求分发处理

        收集请求指标并检查告警条件。

        Args:
            request: 请求对象
            call_next: 下一个中间件或路由处理函数

        Returns:
            Response: 正常响应
        """
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000

        # 记录指标
        metrics_store.record(request.url.path, elapsed, response.status_code)

        # 检查告警条件
        alert_manager.check_and_alert()

        return response


class AlertManager:
    """
    告警管理器

    基于指标快照检查告警条件。

    当前告警规则：
    - 错误率 >= 阈值 且 请求数 >= 20 -> 发出告警日志
    """

    def check_and_alert(self):
        """
        检查告警条件

        基于当前指标快照检查是否需要触发告警。
        如果错误率超过阈值，记录告警日志。
        """
        snapshot = metrics_store.snapshot()
        error_rate = snapshot["error_rate"]

        # 检查错误率告警条件
        if error_rate >= settings.ALERT_ERROR_RATE_THRESHOLD and snapshot["request_total"] >= 20:
            logger.warning(
                "high_error_rate_detected",
                error_rate=error_rate,
                threshold=settings.ALERT_ERROR_RATE_THRESHOLD,
                request_total=snapshot["request_total"],
            )


# 全局告警管理器实例
alert_manager = AlertManager()