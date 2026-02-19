#!/usr/bin/env python3
"""
轻量压测脚本（非 pytest）
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def worker(client: httpx.AsyncClient, base_url: str, count: int, latencies: list[float]):
    for _ in range(count):
        start = time.perf_counter()
        resp = await client.get(f"{base_url}/health")
        resp.raise_for_status()
        latencies.append((time.perf_counter() - start) * 1000)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()

    per_worker = max(1, args.requests // args.concurrency)
    latencies: list[float] = []
    async with httpx.AsyncClient(timeout=10) as client:
        await asyncio.gather(
            *[
                worker(client, args.base_url, per_worker, latencies)
                for _ in range(args.concurrency)
            ]
        )

    if not latencies:
        print("No latency samples collected.")
        return

    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]
    print(f"requests={len(latencies)}")
    print(f"avg_ms={statistics.mean(latencies):.2f}")
    print(f"p95_ms={p95:.2f}")
    print(f"max_ms={max(latencies):.2f}")


if __name__ == "__main__":
    asyncio.run(main())

