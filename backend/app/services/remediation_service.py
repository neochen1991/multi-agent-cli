"""
修复工作流服务模块

本模块提供修复动作的状态机管理功能。

核心功能：
1. 修复提案创建
2. 模拟执行
3. 审批流程
4. 执行与验证
5. 回滚支持

状态流转：
PROPOSED -> SIMULATED -> APPROVED -> EXECUTED -> VERIFIED
                    -> ROLLED_BACK

风险控制：
- 高风险操作需要审批
- No-Regression Gate 防止回归
- 变更窗口风险标记

存储路径：
- SQLite.remediation_actions

使用场景：
- 自动修复提案审批
- 变更管理集成
- 修复效果验证

Remediation Service
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.storage import sqlite_store


class RemediationService:
    """
    修复动作状态机服务

    管理修复动作的完整生命周期。

    状态流转：
    - PROPOSED: 已提案
    - SIMULATED: 已模拟
    - APPROVED: 已审批
    - EXECUTED: 已执行
    - VERIFIED: 已验证
    - ROLLED_BACK: 已回滚

    属性：
    - _store: SQLite 存储
    """

    # 状态流转顺序
    _FLOW = ["PROPOSED", "SIMULATED", "APPROVED", "EXECUTED", "VERIFIED"]

    def __init__(self) -> None:
        """
        初始化修复工作流服务

        初始化 SQLite 存储。
        """
        self._store = sqlite_store

    def _now(self) -> str:
        """
        获取当前 UTC 时间字符串

        Returns:
            str: ISO 格式时间字符串
        """
        return datetime.utcnow().isoformat()

    async def _load(self) -> List[Dict[str, Any]]:
        """读取全部修复动作记录。"""
        rows = await self._store.fetchall(
            "SELECT payload_json FROM remediation_actions ORDER BY created_at ASC"
        )
        return [self._store.loads_json(row["payload_json"], {}) for row in rows]

    async def _save_row(self, item: Dict[str, Any]) -> None:
        """保存单条修复动作记录。"""
        await self._store.execute(
            """
            INSERT OR REPLACE INTO remediation_actions (id, created_at, payload_json)
            VALUES (?, ?, ?)
            """,
            (
                str(item.get("id") or ""),
                str(item.get("created_at") or self._now()),
                self._store.dumps_json(item),
            ),
        )

    def _find(self, items: List[Dict[str, Any]], action_id: str) -> Optional[Dict[str, Any]]:
        """
        查找指定 ID 的修复动作

        Args:
            items: 修复动作列表
            action_id: 动作 ID

        Returns:
            Optional[Dict[str, Any]]: 找到的动作，不存在则返回 None
        """
        for row in items:
            if str(row.get("id") or "") == action_id:
                return row
        return None

    def _append_audit(self, row: Dict[str, Any], event: str, payload: Dict[str, Any]) -> None:
        """
        追加审计日志

        Args:
            row: 修复动作记录
            event: 事件名称
            payload: 事件数据
        """
        logs = row.get("audit_logs")
        if not isinstance(logs, list):
            logs = []
        logs.append({"at": self._now(), "event": event, **dict(payload or {})})
        row["audit_logs"] = logs

    @staticmethod
    def _no_regression(pre_slo: Dict[str, Any], post_slo: Dict[str, Any]) -> Dict[str, Any]:
        """
        简化版 No-Regression Gate

        对 error_rate 和 p95_latency 做门禁检查。

        通过条件：
        - error_rate 增量 <= 0.01
        - p95_latency 增量 <= 80ms

        Args:
            pre_slo: 执行前 SLO 指标
            post_slo: 执行后 SLO 指标

        Returns:
            Dict[str, Any]: 门禁检查结果
        """
        pre_error = float(pre_slo.get("error_rate") or 0.0)
        post_error = float(post_slo.get("error_rate") or 0.0)
        pre_latency = float(pre_slo.get("p95_latency_ms") or 0.0)
        post_latency = float(post_slo.get("p95_latency_ms") or 0.0)
        error_delta = post_error - pre_error
        latency_delta = post_latency - pre_latency
        passed = error_delta <= 0.01 and latency_delta <= 80
        return {
            "passed": passed,
            "pre": {"error_rate": pre_error, "p95_latency_ms": pre_latency},
            "post": {"error_rate": post_error, "p95_latency_ms": post_latency},
            "delta": {"error_rate": round(error_delta, 4), "p95_latency_ms": round(latency_delta, 2)},
        }

    async def list_actions(self, limit: int = 200) -> List[Dict[str, Any]]:
        """
        列出最近的修复动作

        Args:
            limit: 最大返回数量

        Returns:
            List[Dict[str, Any]]: 修复动作列表（按时间倒序）
        """
        items = await self._load()
        return list(reversed(items))[: max(1, int(limit or 200))]

    async def get_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单个修复动作详情

        Args:
            action_id: 动作 ID

        Returns:
            Optional[Dict[str, Any]]: 动作详情
        """
        items = await self._load()
        row = self._find(items, action_id)
        return dict(row) if isinstance(row, dict) else None

    async def propose(
        self,
        *,
        incident_id: str,
        session_id: str,
        summary: str,
        steps: List[str],
        risk_level: str,
        pre_slo: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        创建修复提案

        Args:
            incident_id: 关联的故障 ID
            session_id: 会话 ID
            summary: 修复摘要
            steps: 修复步骤列表
            risk_level: 风险级别（low/medium/high/critical）
            pre_slo: 执行前 SLO 指标

        Returns:
            Dict[str, Any]: 创建的修复提案
        """
        record = {
            "id": f"fix_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            "incident_id": incident_id,
            "session_id": session_id,
            "summary": summary,
            "steps": [str(step) for step in (steps or []) if str(step).strip()],
            "risk_level": str(risk_level or "medium").lower(),
            "state": "PROPOSED",
            "pre_slo": dict(pre_slo or {}),
            "post_slo": {},
            "regression_gate": {},
            "approvals": [],
            "rollback_plan": {},
            "change_link": {},
            "audit_logs": [],
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self._append_audit(record, "proposed", {"summary": summary})
        await self._save_row(record)
        return record

    async def simulate(self, action_id: str, simulated_slo: Dict[str, Any]) -> Dict[str, Any]:
        """
        写入模拟结果

        将动作状态推进到 SIMULATED。

        Args:
            action_id: 动作 ID
            simulated_slo: 模拟的 SLO 指标

        Returns:
            Dict[str, Any]: 更新后的动作

        Raises:
            ValueError: 动作不存在
        """
        items = await self._load()
        row = self._find(items, action_id)
        if not row:
            raise ValueError(f"action not found: {action_id}")
        row["state"] = "SIMULATED"
        row["simulated_slo"] = dict(simulated_slo or {})
        row["updated_at"] = self._now()
        self._append_audit(row, "simulated", {"simulated_slo": row["simulated_slo"]})
        await self._save_row(row)
        return dict(row)

    async def approve(self, action_id: str, approver: str, comment: str = "") -> Dict[str, Any]:
        """
        审批修复提案

        将动作状态推进到 APPROVED。

        Args:
            action_id: 动作 ID
            approver: 审批人
            comment: 审批意见

        Returns:
            Dict[str, Any]: 更新后的动作

        Raises:
            ValueError: 动作不存在
        """
        items = await self._load()
        row = self._find(items, action_id)
        if not row:
            raise ValueError(f"action not found: {action_id}")
        approvals = row.get("approvals")
        if not isinstance(approvals, list):
            approvals = []
        approvals.append({"approver": approver, "comment": comment, "at": self._now()})
        row["approvals"] = approvals
        row["state"] = "APPROVED"
        row["updated_at"] = self._now()
        self._append_audit(row, "approved", {"approver": approver, "comment": comment})
        await self._save_row(row)
        return dict(row)

    async def execute(
        self,
        action_id: str,
        *,
        operator: str,
        post_slo: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行修复动作

        通过 No-Regression Gate 后将状态推进到 EXECUTED。

        执行前检查：
        1. 高风险操作需要审批
        2. 状态必须为 APPROVED
        3. No-Regression Gate 必须通过

        Args:
            action_id: 动作 ID
            operator: 执行人
            post_slo: 执行后 SLO 指标

        Returns:
            Dict[str, Any]: 更新后的动作

        Raises:
            ValueError: 动作不存在、未审批、或 Gate 失败
        """
        items = await self._load()
        row = self._find(items, action_id)
        if not row:
            raise ValueError(f"action not found: {action_id}")

        # 检查高风险操作是否已审批
        risk_level = str(row.get("risk_level") or "medium").lower()
        approvals = row.get("approvals") if isinstance(row.get("approvals"), list) else []
        if risk_level in {"high", "critical"} and not approvals:
            raise ValueError("high-risk action requires manual approval before execution")

        # 检查状态
        if str(row.get("state") or "") != "APPROVED":
            raise ValueError("action must be APPROVED before execution")

        # No-Regression Gate 检查
        gate = self._no_regression(dict(row.get("pre_slo") or {}), dict(post_slo or {}))
        row["regression_gate"] = gate
        row["post_slo"] = dict(post_slo or {})

        if not bool(gate.get("passed")):
            row["state"] = "APPROVED"
            row["updated_at"] = self._now()
            self._append_audit(row, "execution_blocked_by_no_regression_gate", {"operator": operator, "gate": gate})
            await self._save_row(row)
            raise ValueError("no-regression gate failed; execution blocked")

        row["state"] = "EXECUTED"
        row["updated_at"] = self._now()
        self._append_audit(row, "executed", {"operator": operator, "post_slo": row["post_slo"]})
        await self._save_row(row)
        return dict(row)

    async def verify(self, action_id: str, verifier: str, verification: Dict[str, Any]) -> Dict[str, Any]:
        """
        提交修复验证结果

        将状态推进到 VERIFIED。

        Args:
            action_id: 动作 ID
            verifier: 验证人
            verification: 验证结果

        Returns:
            Dict[str, Any]: 更新后的动作

        Raises:
            ValueError: 动作不存在或状态不正确
        """
        items = await self._load()
        row = self._find(items, action_id)
        if not row:
            raise ValueError(f"action not found: {action_id}")
        if str(row.get("state") or "") != "EXECUTED":
            raise ValueError("action must be EXECUTED before verification")
        row["state"] = "VERIFIED"
        row["verification"] = dict(verification or {})
        row["updated_at"] = self._now()
        self._append_audit(row, "verified", {"verifier": verifier, "verification": row["verification"]})
        await self._save_row(row)
        return dict(row)

    async def rollback(self, action_id: str, reason: str, execute: bool = False) -> Dict[str, Any]:
        """
        生成或执行回滚计划

        Args:
            action_id: 动作 ID
            reason: 回滚原因
            execute: 是否立即执行回滚

        Returns:
            Dict[str, Any]: 包含动作和回滚计划

        Raises:
            ValueError: 动作不存在
        """
        items = await self._load()
        row = self._find(items, action_id)
        if not row:
            raise ValueError(f"action not found: {action_id}")

        # 生成回滚计划
        plan = {
            "summary": f"回滚 {row.get('id')} 到执行前版本",
            "steps": [
                "恢复上一个稳定版本",
                "恢复配置快照",
                "回放关键业务探针并验证 SLO",
            ],
            "reason": reason,
            "generated_at": self._now(),
        }
        row["rollback_plan"] = plan

        if execute:
            row["state"] = "ROLLED_BACK"
            self._append_audit(row, "rollback_executed", {"reason": reason})
        else:
            self._append_audit(row, "rollback_plan_generated", {"reason": reason})

        row["updated_at"] = self._now()
        await self._save_row(row)
        return {"action": dict(row), "rollback_plan": plan}

    async def link_change_window(
        self,
        action_id: str,
        *,
        change_id: str,
        window: str,
        release_type: str,
    ) -> Dict[str, Any]:
        """
        将修复动作与变更窗口绑定

        根据窗口和发布类型标记风险信号。

        风险信号：
        - high-risk-release-type: schema/infra/major 发布
        - non-business-change-window: 冻结期或夜间变更

        Args:
            action_id: 动作 ID
            change_id: 变更 ID
            window: 变更窗口
            release_type: 发布类型

        Returns:
            Dict[str, Any]: 更新后的动作

        Raises:
            ValueError: 动作不存在
        """
        items = await self._load()
        row = self._find(items, action_id)
        if not row:
            raise ValueError(f"action not found: {action_id}")

        # 检测风险信号
        risk_signals = []
        if str(release_type).lower() in {"schema", "infra", "major"}:
            risk_signals.append("high-risk-release-type")
        if "freeze" in str(window).lower() or "night" in str(window).lower():
            risk_signals.append("non-business-change-window")

        row["change_link"] = {
            "change_id": change_id,
            "window": window,
            "release_type": release_type,
            "risk_signals": risk_signals,
            "high_risk": bool(risk_signals),
        }
        row["updated_at"] = self._now()
        self._append_audit(row, "change_linked", {"change_link": row["change_link"]})
        await self._save_row(row)
        return dict(row)


# 全局实例
remediation_service = RemediationService()
