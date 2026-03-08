#!/usr/bin/env python3
"""评测门禁脚本。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def latest_baseline(metrics_dir: Path) -> Path | None:
    """返回最新的 baseline 报告路径。"""
    
    files = sorted(metrics_dir.glob("baseline-*.json"), reverse=True)
    return files[0] if files else None


def previous_baseline(metrics_dir: Path) -> Path | None:
    """返回上一份 baseline 报告路径，用于做回归对比。"""
    
    files = sorted(metrics_dir.glob("baseline-*.json"), reverse=True)
    return files[1] if len(files) > 1 else None


def load_summary(path: Path) -> Dict[str, Any]:
    """读取 baseline 文件中的 summary 段，供质量门禁判断使用。"""
    
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def main() -> int:
    """执行脚本主流程，串联参数解析、内容生成与结果输出。"""
    
    parser = argparse.ArgumentParser(description="Benchmark quality gate")
    parser.add_argument("--metrics-dir", default="docs/metrics", help="baseline report directory")
    parser.add_argument("--min-top1", type=float, default=0.30, help="minimum top1_rate")
    parser.add_argument("--min-top3", type=float, default=0.45, help="minimum top3_rate")
    parser.add_argument("--min-cross-source", type=float, default=0.30, help="minimum cross_source_evidence_rate")
    parser.add_argument("--max-failure", type=float, default=0.60, help="maximum failure_rate")
    parser.add_argument("--max-timeout", type=float, default=0.50, help="maximum timeout_rate")
    parser.add_argument("--max-empty", type=float, default=0.40, help="maximum empty_conclusion_rate")
    parser.add_argument(
        "--max-first-evidence-p95-ms",
        type=float,
        default=10000,
        help="maximum p95_first_evidence_latency_ms",
    )
    parser.add_argument(
        "--max-top1-drop",
        type=float,
        default=0.03,
        help="maximum allowed top1_rate regression vs previous baseline",
    )
    parser.add_argument(
        "--max-timeout-increase",
        type=float,
        default=0.05,
        help="maximum allowed timeout_rate increase vs previous baseline",
    )
    args = parser.parse_args()

    metrics_dir = Path(args.metrics_dir)
    baseline = latest_baseline(metrics_dir)
    if baseline is None:
        print(f"[benchmark-gate] FAIL: no baseline found in {metrics_dir}")
        return 2

    summary = load_summary(baseline)
    prev_baseline = previous_baseline(metrics_dir)
    prev_summary = load_summary(prev_baseline) if prev_baseline else {}
    top1 = float(summary.get("top1_rate") or 0.0)
    top3 = float(summary.get("top3_rate") or 0.0)
    cross_source = float(summary.get("cross_source_evidence_rate") or 0.0)
    failure = float(summary.get("failure_rate") or 1.0)
    timeout = float(summary.get("timeout_rate") or 1.0)
    empty = float(summary.get("empty_conclusion_rate") or 1.0)
    first_evidence_p95 = float(summary.get("p95_first_evidence_latency_ms") or 0.0)

    violations = []
    if top1 < float(args.min_top1):
        violations.append(f"top1_rate={top1:.3f} < min_top1={args.min_top1:.3f}")
    if top3 < float(args.min_top3):
        violations.append(f"top3_rate={top3:.3f} < min_top3={args.min_top3:.3f}")
    if cross_source < float(args.min_cross_source):
        violations.append(
            f"cross_source_evidence_rate={cross_source:.3f} < min_cross_source={args.min_cross_source:.3f}"
        )
    if failure > float(args.max_failure):
        violations.append(f"failure_rate={failure:.3f} > max_failure={args.max_failure:.3f}")
    if timeout > float(args.max_timeout):
        violations.append(f"timeout_rate={timeout:.3f} > max_timeout={args.max_timeout:.3f}")
    if empty > float(args.max_empty):
        violations.append(f"empty_conclusion_rate={empty:.3f} > max_empty={args.max_empty:.3f}")
    if first_evidence_p95 > float(args.max_first_evidence_p95_ms):
        violations.append(
            "p95_first_evidence_latency_ms="
            f"{first_evidence_p95:.2f} > max_first_evidence_p95_ms={args.max_first_evidence_p95_ms:.2f}"
        )

    top1_delta = 0.0
    timeout_delta = 0.0
    if prev_summary:
        prev_top1 = float(prev_summary.get("top1_rate") or 0.0)
        prev_timeout = float(prev_summary.get("timeout_rate") or 0.0)
        top1_delta = round(top1 - prev_top1, 3)
        timeout_delta = round(timeout - prev_timeout, 3)
        if top1_delta < -abs(float(args.max_top1_drop)):
            violations.append(
                f"top1_rate_delta={top1_delta:.3f} < -max_top1_drop={-abs(float(args.max_top1_drop)):.3f}"
            )
        if timeout_delta > abs(float(args.max_timeout_increase)):
            violations.append(
                f"timeout_rate_delta={timeout_delta:.3f} > max_timeout_increase={abs(float(args.max_timeout_increase)):.3f}"
            )

    print(f"[benchmark-gate] baseline={baseline}")
    print(
        "[benchmark-gate] summary:",
        json.dumps(
            {
                "top1_rate": top1,
                "top3_rate": top3,
                "cross_source_evidence_rate": cross_source,
                "failure_rate": failure,
                "timeout_rate": timeout,
                "empty_conclusion_rate": empty,
                "p95_first_evidence_latency_ms": first_evidence_p95,
                "top1_rate_delta_vs_prev": top1_delta,
                "timeout_rate_delta_vs_prev": timeout_delta,
            },
            ensure_ascii=False,
        ),
    )
    if violations:
        print("[benchmark-gate] FAIL")
        for item in violations:
            print(f" - {item}")
        return 1

    print("[benchmark-gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
