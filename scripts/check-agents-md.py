#!/usr/bin/env python3
"""基础校验 AGENTS.md 约束与关键引用是否可用。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
MAX_LINES = 160
REQUIRED_SNIPPETS = [
    "主 Agent 命令先行",
    "工具调用可审计",
    "Skill 调用可审计",
    "结构化输出优先",
    "有效结论门禁",
    "会话可终止",
    "断点续写",
]


def main() -> int:
    if not AGENTS_PATH.exists():
        print("FAIL: AGENTS.md 不存在")
        return 1

    content = AGENTS_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    failures = []

    if len(lines) > MAX_LINES:
        failures.append(f"AGENTS.md 行数过多: {len(lines)} > {MAX_LINES}")

    for snippet in REQUIRED_SNIPPETS:
        if snippet not in content:
            failures.append(f"缺少必备约束条目: {snippet}")

    linked_paths = re.findall(r"`([^`]+)`", content)
    for linked in linked_paths:
        if not (linked.startswith("docs/") or linked.startswith("backend/") or linked.startswith("frontend/") or linked.startswith("scripts/")):
            continue
        if "*" in linked or "{" in linked or "}" in linked:
            continue
        target = REPO_ROOT / linked
        if not target.exists():
            failures.append(f"引用不存在: {linked}")

    if failures:
        print("FAIL: AGENTS.md 校验失败")
        for item in failures:
            print(f"- {item}")
        return 1

    print("OK: AGENTS.md 校验通过")
    print(f"- 行数: {len(lines)}")
    print(f"- 校验文件: {AGENTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
