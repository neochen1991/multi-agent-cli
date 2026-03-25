"""upstream_timeout_chain 插件入口。

中文注释：该插件用于在“上游超时级联”场景下做轻量结构化抽取，
输出可审计的候选链路与置信度，供专家 Agent 与 JudgeAgent 进一步裁决。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


TIMEOUT_PATTERN = re.compile(
    r"(timeout|timed out|deadline exceeded|504|upstream request timeout|read timeout)",
    re.IGNORECASE,
)
SERVICE_PATTERN = re.compile(
    r"(?:service|svc|upstream|downstream|callee|caller)\s*[:=]\s*([A-Za-z0-9._-]{2,64})",
    re.IGNORECASE,
)
HOST_PATTERN = re.compile(r"https?://([A-Za-z0-9.-]{3,120})")
ARROW_CHAIN_PATTERN = re.compile(r"([A-Za-z0-9._-]{2,64})\s*(?:->|=>|→)\s*([A-Za-z0-9._-]{2,64})")
FROM_TO_PATTERN = re.compile(r"\bfrom\s+([A-Za-z0-9._-]{2,64})\s+to\s+([A-Za-z0-9._-]{2,64})\b", re.IGNORECASE)


def _collect_lines(payload: Dict[str, Any]) -> List[str]:
    incident = payload.get("incident_context") if isinstance(payload.get("incident_context"), dict) else {}
    compact = payload.get("compact_context") if isinstance(payload.get("compact_context"), dict) else {}
    command = payload.get("assigned_command") if isinstance(payload.get("assigned_command"), dict) else {}
    chunks = [
        str((incident or {}).get("description") or ""),
        str((incident or {}).get("title") or ""),
        str((compact or {}).get("log_excerpt") or ""),
        str((compact or {}).get("metrics_excerpt") or ""),
        str((command or {}).get("focus") or ""),
        str((command or {}).get("task") or ""),
    ]
    lines: List[str] = []
    for chunk in chunks:
        for raw in chunk.splitlines():
            line = raw.strip()
            if line:
                lines.append(line[:220])
    return lines


def _extract_timeout_signals(lines: List[str]) -> List[str]:
    picks: List[str] = []
    for line in lines:
        if TIMEOUT_PATTERN.search(line):
            picks.append(line)
            if len(picks) >= 10:
                break
    return picks


def _extract_services(lines: List[str]) -> List[str]:
    services: List[str] = []
    for line in lines:
        for match in SERVICE_PATTERN.findall(line):
            value = str(match or "").strip()
            if value:
                services.append(value)
        for host in HOST_PATTERN.findall(line):
            value = str(host or "").split(".")[0].strip()
            if value:
                services.append(value)
    return list(dict.fromkeys(services))[:12]


def _extract_cascade_chain(lines: List[str], services: List[str]) -> List[str]:
    chain: List[str] = []
    for line in lines:
        for left, right in ARROW_CHAIN_PATTERN.findall(line):
            chain.append(f"{left}->{right}")
        for left, right in FROM_TO_PATTERN.findall(line):
            chain.append(f"{left}->{right}")
    # 中文注释：如果日志里没有显式链路箭头，就按服务出现顺序做保守近似。
    if not chain and len(services) >= 2:
        for idx in range(len(services) - 1):
            chain.append(f"{services[idx]}->{services[idx + 1]}")
            if len(chain) >= 5:
                break
    return list(dict.fromkeys(chain))[:8]


def _derive_upstream_candidates(timeout_signals: List[str], services: List[str], chain: List[str]) -> List[str]:
    picks: List[str] = []
    for line in timeout_signals:
        for match in SERVICE_PATTERN.findall(line):
            value = str(match or "").strip()
            if value:
                picks.append(value)
    for item in chain:
        left = item.split("->", 1)[0].strip()
        if left:
            picks.append(left)
    picks.extend(services[:2])
    return list(dict.fromkeys(picks))[:6]


def _score(timeout_signals: List[str], chain: List[str], upstreams: List[str]) -> float:
    score = 0.22
    if timeout_signals:
        score += 0.28
    if len(timeout_signals) >= 3:
        score += 0.1
    if chain:
        score += 0.24
    if upstreams:
        score += 0.16
    return round(min(0.95, score), 2)


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    lines = _collect_lines(payload)
    timeout_signals = _extract_timeout_signals(lines)
    services = _extract_services(lines)
    chain = _extract_cascade_chain(lines, services)
    upstreams = _derive_upstream_candidates(timeout_signals, services, chain)
    confidence = _score(timeout_signals, chain, upstreams)
    summary = (
        f"识别到 {len(timeout_signals)} 条超时信号，"
        f"{len(chain)} 段级联链路，候选上游服务 {len(upstreams)} 个。"
    )
    print(
        json.dumps(
            {
                "success": True,
                "status": "ok",
                "summary": summary,
                "suspected_upstream_services": upstreams,
                "cascade_chain": chain,
                "timeout_signals": timeout_signals[:8],
                "confidence": confidence,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
