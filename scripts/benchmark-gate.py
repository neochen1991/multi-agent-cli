#!/usr/bin/env python3
"""Benchmark quality gate based on latest baseline report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def latest_baseline(metrics_dir: Path) -> Path | None:
    files = sorted(metrics_dir.glob("baseline-*.json"), reverse=True)
    return files[0] if files else None


def load_summary(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark quality gate")
    parser.add_argument("--metrics-dir", default="docs/metrics", help="baseline report directory")
    parser.add_argument("--min-top1", type=float, default=0.30, help="minimum top1_rate")
    parser.add_argument("--max-failure", type=float, default=0.60, help="maximum failure_rate")
    parser.add_argument("--max-timeout", type=float, default=0.50, help="maximum timeout_rate")
    parser.add_argument("--max-empty", type=float, default=0.40, help="maximum empty_conclusion_rate")
    args = parser.parse_args()

    metrics_dir = Path(args.metrics_dir)
    baseline = latest_baseline(metrics_dir)
    if baseline is None:
        print(f"[benchmark-gate] FAIL: no baseline found in {metrics_dir}")
        return 2

    summary = load_summary(baseline)
    top1 = float(summary.get("top1_rate") or 0.0)
    failure = float(summary.get("failure_rate") or 1.0)
    timeout = float(summary.get("timeout_rate") or 1.0)
    empty = float(summary.get("empty_conclusion_rate") or 1.0)

    violations = []
    if top1 < float(args.min_top1):
        violations.append(f"top1_rate={top1:.3f} < min_top1={args.min_top1:.3f}")
    if failure > float(args.max_failure):
        violations.append(f"failure_rate={failure:.3f} > max_failure={args.max_failure:.3f}")
    if timeout > float(args.max_timeout):
        violations.append(f"timeout_rate={timeout:.3f} > max_timeout={args.max_timeout:.3f}")
    if empty > float(args.max_empty):
        violations.append(f"empty_conclusion_rate={empty:.3f} > max_empty={args.max_empty:.3f}")

    print(f"[benchmark-gate] baseline={baseline}")
    print(
        "[benchmark-gate] summary:",
        json.dumps(
            {
                "top1_rate": top1,
                "failure_rate": failure,
                "timeout_rate": timeout,
                "empty_conclusion_rate": empty,
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

