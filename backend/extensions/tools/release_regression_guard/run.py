"""release_regression_guard 插件入口。

中文注释：该插件聚焦“发布变更是否触发故障”的时间相关性证据抽取，
避免仅凭主观经验判断“像是发布问题”。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


VERSION_PATTERN = re.compile(r"\bv?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?\b", re.IGNORECASE)
COMMIT_PATTERN = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)
RELEASE_TOKEN_PATTERN = re.compile(
    r"(?:release|deploy|build|rollback)\s*[#:：]?\s*([A-Za-z0-9._-]{3,64})",
    re.IGNORECASE,
)
TEMPORAL_PATTERN = re.compile(
    r"(after deploy|after release|post deploy|发布后|上线后|回滚后|before deploy|上线前)",
    re.IGNORECASE,
)
NON_RELEASE_PATTERN = re.compile(
    r"(deadlock|lock wait timeout|network unreachable|dns|db overload|queue backlog|upstream timeout)",
    re.IGNORECASE,
)


def _collect_lines(payload: Dict[str, Any]) -> List[str]:
    incident = payload.get("incident_context") if isinstance(payload.get("incident_context"), dict) else {}
    compact = payload.get("compact_context") if isinstance(payload.get("compact_context"), dict) else {}
    command = payload.get("assigned_command") if isinstance(payload.get("assigned_command"), dict) else {}
    parts = [
        str((incident or {}).get("description") or ""),
        str((incident or {}).get("title") or ""),
        str((incident or {}).get("start_time") or ""),
        str((incident or {}).get("started_at") or ""),
        str((compact or {}).get("change_excerpt") or ""),
        str((compact or {}).get("log_excerpt") or ""),
        str((command or {}).get("focus") or ""),
    ]
    lines: List[str] = []
    for text in parts:
        for raw in text.splitlines():
            line = raw.strip()
            if line:
                lines.append(line[:240])
    return lines


def _extract_release_refs(lines: List[str]) -> List[str]:
    refs: List[str] = []
    for line in lines:
        refs.extend(VERSION_PATTERN.findall(line))
        refs.extend(COMMIT_PATTERN.findall(line))
        refs.extend(RELEASE_TOKEN_PATTERN.findall(line))
    return list(dict.fromkeys(str(item or "").strip() for item in refs if str(item or "").strip()))[:12]


def _extract_temporal_evidence(lines: List[str]) -> List[str]:
    picks: List[str] = []
    for line in lines:
        if TEMPORAL_PATTERN.search(line):
            picks.append(line)
        # 中文注释：补充“同一行同时包含发布词和错误词”作为弱时序证据。
        if re.search(r"(deploy|release|上线|回滚)", line, re.IGNORECASE) and re.search(
            r"(error|exception|5\d\d|告警|故障)",
            line,
            re.IGNORECASE,
        ):
            picks.append(line)
        if len(picks) >= 10:
            break
    return list(dict.fromkeys(picks))


def _extract_non_release_signals(lines: List[str]) -> List[str]:
    picks: List[str] = []
    for line in lines:
        if NON_RELEASE_PATTERN.search(line):
            picks.append(line)
            if len(picks) >= 8:
                break
    return picks


def _score(release_refs: List[str], temporal_evidence: List[str], non_release: List[str]) -> float:
    score = 0.18
    if release_refs:
        score += 0.26
    if temporal_evidence:
        score += 0.3
    if len(release_refs) >= 3:
        score += 0.08
    if non_release:
        score -= 0.08
    return round(max(0.05, min(0.93, score)), 2)


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    lines = _collect_lines(payload)
    release_refs = _extract_release_refs(lines)
    temporal_evidence = _extract_temporal_evidence(lines)
    non_release = _extract_non_release_signals(lines)
    confidence = _score(release_refs, temporal_evidence, non_release)
    summary = (
        f"抽取到 {len(release_refs)} 个发布标识、"
        f"{len(temporal_evidence)} 条时序证据，非发布线索 {len(non_release)} 条。"
    )
    print(
        json.dumps(
            {
                "success": True,
                "status": "ok",
                "summary": summary,
                "suspected_release_refs": release_refs,
                "temporal_evidence": temporal_evidence,
                "non_release_signals": non_release,
                "confidence": confidence,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
