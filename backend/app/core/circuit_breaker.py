"""
熔断器模块

本模块实现熔断器模式，用于保护系统免受级联故障影响。

熔断器状态机：
- closed（关闭）: 正常状态，允许所有请求
- open（打开）: 熔断状态，拒绝所有请求
- half-open（半开）: 探测状态，允许部分请求测试恢复

工作流程：
1. 正常状态下，请求正常执行
2. 失败次数达到阈值，熔断器打开
3. 经过恢复超时后，进入半开状态
4. 半开状态下请求成功则关闭，失败则重新打开

使用场景：
- LLM 调用保护
- 外部 API 调用保护
- 数据库连接保护

Circuit Breaker
"""

from __future__ import annotations

import time


class CircuitBreaker:
    """
    熔断器

    实现熔断器模式，防止系统在下游服务故障时持续发起请求。

    状态转换：
    closed --[失败次数达到阈值]--> open
    open --[超时后]--> half-open
    half-open --[成功]--> closed
    half-open --[失败]--> open

    属性：
    - failure_threshold: 失败阈值，超过后熔断
    - recovery_timeout: 恢复超时（秒），熔断后等待时间
    - failure_count: 当前失败计数
    - state: 当前状态（closed/open/half-open）
    """

    def __init__(self, failure_threshold: int, recovery_timeout: int):
        """
        初始化熔断器

        Args:
            failure_threshold: 失败阈值，连续失败次数达到此值后熔断
            recovery_timeout: 恢复超时（秒），熔断后等待多久尝试恢复
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "closed"  # closed | open | half-open

    def allow_request(self) -> bool:
        """
        检查是否允许请求

        根据当前状态决定是否允许请求通过：
        - closed: 允许
        - open: 检查是否超时，超时则转为 half-open 并允许
        - half-open: 允许（用于探测）

        Returns:
            bool: True 表示允许请求，False 表示拒绝
        """
        if self.state == "closed":
            return True

        if self.state == "open":
            # 检查是否超过恢复超时
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half-open"
                return True
            return False

        # half-open 状态允许请求通过
        return True

    def record_success(self) -> None:
        """
        记录成功

        请求成功后调用，重置失败计数并将状态设为 closed。
        用于 half-open 状态下的恢复确认。
        """
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        """
        记录失败

        请求失败后调用，增加失败计数。
        如果失败次数达到阈值，将状态设为 open。
        """
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"