"""Build lightweight domain invariants and constraint checks."""

from __future__ import annotations

from typing import Any, Dict, List


def build_aggregate_invariants(*, mapping: Dict[str, Any], endpoint: Dict[str, Any]) -> List[str]:
    aggregate = str(mapping.get("aggregate") or "").strip()
    feature = str(mapping.get("feature") or "").strip()
    invariants: List[str] = []
    if aggregate:
        invariants.append(f"{aggregate} 需要保持聚合内状态一致")
    if feature:
        invariants.append(f"{feature} 过程中需要保证核心领域动作原子化")
    if str(endpoint.get("method") or "").upper() in {"POST", "PUT"}:
        invariants.append("写接口需要保证事务边界与幂等/重试策略一致")
    return invariants[:6]


def build_domain_constraint_checks(
    *,
    mapping: Dict[str, Any],
    endpoint: Dict[str, Any],
    matches: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    if mapping.get("matched"):
        checks.append(
            {
                "name": "owner_mapping",
                "status": "ok",
                "rationale": f"责任团队已映射到 {str(mapping.get('owner_team') or '-')}",
            }
        )
    if list(mapping.get("database_tables") or mapping.get("db_tables") or []):
        checks.append(
            {
                "name": "aggregate_data_boundary",
                "status": "ok",
                "rationale": "已识别聚合相关数据库表，可继续检查事务顺序和聚合边界。",
            }
        )
    if list(mapping.get("dependency_services") or []):
        checks.append(
            {
                "name": "downstream_dependency",
                "status": "review",
                "rationale": "聚合依赖下游服务，需要校验调用顺序、超时与补偿策略。",
            }
        )
    if matches:
        checks.append(
            {
                "name": "knowledge_match",
                "status": "ok",
                "rationale": f"命中 {len(matches[:8])} 条责任田/知识线索，可辅助领域归因。",
            }
        )
    if str(endpoint.get("method") or "").upper() == "POST":
        checks.append(
            {
                "name": "transaction_order",
                "status": "review",
                "rationale": "创建类接口需要确认聚合写入、库存扣减、消息发送等顺序是否满足领域约束。",
            }
        )
    return checks[:8]
