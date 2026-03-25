"""design_spec_alignment 插件入口。

中文注释：该示例插件只做轻量结构化抽取，目的是演示插件协议和返回结构，
不做复杂语义推理，避免给生产链路引入不稳定行为。
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List


def _pick_lines(text: str, limit: int = 6) -> List[str]:
    lines: List[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        lines.append(line[:160])
        if len(lines) >= limit:
            break
    return lines


def _extract_design_candidates(payload: Dict[str, Any]) -> List[str]:
    incident = payload.get("incident_context") if isinstance(payload.get("incident_context"), dict) else {}
    compact = payload.get("compact_context") if isinstance(payload.get("compact_context"), dict) else {}
    command = payload.get("assigned_command") if isinstance(payload.get("assigned_command"), dict) else {}
    picks: List[str] = []
    picks.extend(_pick_lines(str((incident or {}).get("description") or ""), limit=3))
    picks.extend(_pick_lines(str((compact or {}).get("log_excerpt") or ""), limit=2))
    picks.extend(_pick_lines(str((command or {}).get("focus") or ""), limit=1))
    return [item for item in picks if item][:6]


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    candidates = _extract_design_candidates(payload)
    result = {
        "success": True,
        "status": "ok",
        "summary": f"设计一致性插件已提取 {len(candidates)} 条候选设计点",
        "structured_design": {
            "candidate_points": candidates,
            "analysis_scope": "lightweight_demo",
        },
        "matched_implementation_points": candidates[:2],
        "missing_implementation_points": [],
        "extra_implementation_points": [],
        "conflicting_implementation_points": [],
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
