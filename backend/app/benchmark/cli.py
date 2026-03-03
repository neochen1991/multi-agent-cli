"""CLI entrypoint for benchmark harness."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.benchmark.runner import BenchmarkRunOptions, benchmark_runner


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run RCA benchmark harness")
    parser.add_argument("--limit", type=int, default=3, help="Number of fixtures to run")
    parser.add_argument("--timeout", type=int, default=240, help="Timeout per fixture in seconds")
    args = parser.parse_args()
    report = await benchmark_runner.run(
        BenchmarkRunOptions(
            limit=max(1, args.limit),
            timeout_seconds=max(30, args.timeout),
            write_baseline=True,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())

