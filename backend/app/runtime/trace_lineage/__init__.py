"""
审计轨迹追踪模块

本模块提供运行时事件、Agent 执行、工具调用的审计轨迹记录功能。

核心功能：
1. 记录执行轨迹（事件、Agent、工具调用）
2. 支持轨迹回放和审计
3. 提供轨迹摘要统计

记录类型：
- session: 会话级别记录
- event: 事件记录
- agent: Agent 执行记录
- tool: 工具调用记录
- summary: 摘要记录

存储结构：
- SQLite.lineage_events

使用场景：
- 问题排查：追溯执行过程
- 审计合规：记录操作轨迹
- 性能分析：统计执行耗时

Session lineage tracing helpers.
"""

from app.runtime.trace_lineage.recorder import lineage_recorder
from app.runtime.trace_lineage.replay import replay_session_lineage

__all__ = ["lineage_recorder", "replay_session_lineage"]
