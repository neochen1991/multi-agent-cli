"""db_lock_hotspot 插件入口。

中文注释：该插件用于快速抽取数据库锁争用的结构化线索，
输出“热点表 + 锁信号 + 阻塞方候选”，帮助 DatabaseAgent 快速收敛排查方向。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


LOCK_PATTERN = re.compile(
    r"(deadlock|lock wait timeout|waiting for lock|could not obtain lock|for update|row lock)",
    re.IGNORECASE,
)
TABLE_PATTERN = re.compile(
    r"(?:table|relation)\s*[:=]?\s*[\"'`]?([A-Za-z0-9_.-]{2,128})",
    re.IGNORECASE,
)
SQL_TABLE_PATTERN = re.compile(r"\b(?:from|update|into|join)\s+([A-Za-z0-9_.\"`-]{2,128})", re.IGNORECASE)
BLOCKER_PATTERN = re.compile(
    r"(?:blocked by|blocking|pid|session|trx|transaction|thread)\s*[:=]?\s*([A-Za-z0-9_-]{2,64})",
    re.IGNORECASE,
)


def _collect_lines(payload: Dict[str, Any]) -> List[str]:
    incident = payload.get("incident_context") if isinstance(payload.get("incident_context"), dict) else {}
    compact = payload.get("compact_context") if isinstance(payload.get("compact_context"), dict) else {}
    command = payload.get("assigned_command") if isinstance(payload.get("assigned_command"), dict) else {}
    parts = [
        str((incident or {}).get("description") or ""),
        str((incident or {}).get("title") or ""),
        str((compact or {}).get("log_excerpt") or ""),
        str((compact or {}).get("db_excerpt") or ""),
        str((command or {}).get("focus") or ""),
    ]
    lines: List[str] = []
    for text in parts:
        for raw in text.splitlines():
            line = raw.strip()
            if line:
                lines.append(line[:240])
    return lines


def _extract_lock_signals(lines: List[str]) -> List[str]:
    picks: List[str] = []
    for line in lines:
        if LOCK_PATTERN.search(line):
            picks.append(line)
            if len(picks) >= 10:
                break
    return picks


def _normalize_table_name(name: str) -> str:
    return str(name or "").strip().strip("`").strip('"').strip("'")


def _extract_hot_tables(lines: List[str]) -> List[str]:
    tables: List[str] = []
    for line in lines:
        for item in TABLE_PATTERN.findall(line):
            value = _normalize_table_name(item)
            if value:
                tables.append(value)
        for item in SQL_TABLE_PATTERN.findall(line):
            value = _normalize_table_name(item)
            if value:
                tables.append(value)
    return list(dict.fromkeys(tables))[:10]


def _extract_blockers(lines: List[str]) -> List[str]:
    blockers: List[str] = []
    for line in lines:
        for item in BLOCKER_PATTERN.findall(line):
            value = str(item or "").strip()
            if value:
                blockers.append(value)
    return list(dict.fromkeys(blockers))[:10]


def _score(lock_signals: List[str], hot_tables: List[str], blockers: List[str]) -> float:
    score = 0.2
    if lock_signals:
        score += 0.32
    if len(lock_signals) >= 3:
        score += 0.08
    if hot_tables:
        score += 0.24
    if blockers:
        score += 0.16
    return round(min(0.94, score), 2)


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    lines = _collect_lines(payload)
    lock_signals = _extract_lock_signals(lines)
    hot_tables = _extract_hot_tables(lock_signals + lines[:8])
    blockers = _extract_blockers(lock_signals + lines[:8])
    confidence = _score(lock_signals, hot_tables, blockers)
    summary = (
        f"识别到 {len(lock_signals)} 条锁争用信号，"
        f"热点表候选 {len(hot_tables)} 个，阻塞方线索 {len(blockers)} 条。"
    )
    print(
        json.dumps(
            {
                "success": True,
                "status": "ok",
                "summary": summary,
                "suspected_hot_tables": hot_tables,
                "lock_signals": lock_signals[:8],
                "potential_blockers": blockers[:8],
                "confidence": confidence,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
