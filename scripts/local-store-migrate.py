#!/usr/bin/env python3
"""
本地文件仓储迁移脚本

用途：
1. 为历史文件补充 schema_version
2. 自动创建 .bak 备份
"""

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_STORE_DIR = "/tmp/sre_debate_store"
TARGET_FILES = ["incidents.json", "debates.json", "reports.json"]
TARGET_SCHEMA_VERSION = 1


def migrate_file(path: Path) -> None:
    if not path.exists():
        print(f"[skip] {path} not found")
        return
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except Exception as exc:
        print(f"[error] {path} invalid json: {exc}")
        return

    if not isinstance(payload, dict):
        print(f"[error] {path} payload is not object")
        return

    current = payload.get("schema_version")
    if current == TARGET_SCHEMA_VERSION:
        print(f"[ok] {path} already schema_version={TARGET_SCHEMA_VERSION}")
        return

    backup = path.with_suffix(path.suffix + ".bak")
    backup.write_text(raw, encoding="utf-8")
    payload["schema_version"] = TARGET_SCHEMA_VERSION
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[migrated] {path} schema_version={TARGET_SCHEMA_VERSION} (backup={backup})")


def main() -> None:
    store_dir = Path(os.getenv("LOCAL_STORE_DIR", DEFAULT_STORE_DIR))
    print(f"[info] migrate local store dir={store_dir}")
    store_dir.mkdir(parents=True, exist_ok=True)
    for name in TARGET_FILES:
        migrate_file(store_dir / name)


if __name__ == "__main__":
    main()
