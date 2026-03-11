"""Helpers for expanding symbol references across the repo."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Set

from app.services.code_analysis.source_loader import resolve_repo_file


def find_symbol_file(root: Path, symbol: str, *, source_suffixes: Set[str]) -> Optional[Path]:
    for suffix in source_suffixes:
        candidate = list(root.rglob(f"{symbol}{suffix}"))
        for item in candidate:
            if item.is_file():
                return item
    return None


def extract_related_code_symbols(text: str) -> List[str]:
    symbols: List[str] = []
    for match in re.finditer(
        r"\b([A-Z][A-Za-z0-9_]{2,}(?:Controller|Service|AppService|Repository|Repo|Mapper|Dao|Client|Gateway|Manager))\b",
        text,
    ):
        symbol = str(match.group(1) or "").strip()
        if symbol:
            symbols.append(symbol)
    return list(dict.fromkeys(symbols))[:24]


def expand_related_code_files(
    *,
    repo_path: str,
    seed_files: List[str],
    class_hints: List[str],
    depth: int,
    per_hop_limit: int,
    source_suffixes: Set[str],
) -> List[str]:
    root = Path(str(repo_path or "").strip())
    if not root.exists() or not root.is_dir():
        return []
    queue: List[str] = [str(item or "").strip() for item in seed_files if str(item or "").strip()]
    related: List[str] = []
    seen_files = set(queue)
    seen_symbols: set[str] = set()
    explicit_symbols = [str(item or "").strip() for item in class_hints if str(item or "").strip()]
    for symbol in explicit_symbols:
        symbol_file = find_symbol_file(root, symbol, source_suffixes=source_suffixes)
        if symbol_file is None:
            continue
        try:
            rel = str(symbol_file.relative_to(root))
        except Exception:
            rel = str(symbol_file)
        seen_symbols.add(symbol)
        if rel in seen_files:
            continue
        seen_files.add(rel)
        related.append(rel)
        queue.append(rel)
    for _ in range(max(1, depth)):
        if not queue:
            break
        next_queue: List[str] = []
        hop_found = 0
        for item in list(queue):
            file_path = resolve_repo_file(root, item)
            if file_path is None:
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for symbol in extract_related_code_symbols(text):
                if symbol in seen_symbols:
                    continue
                seen_symbols.add(symbol)
                symbol_file = find_symbol_file(root, symbol, source_suffixes=source_suffixes)
                if symbol_file is None:
                    continue
                try:
                    rel = str(symbol_file.relative_to(root))
                except Exception:
                    rel = str(symbol_file)
                if rel in seen_files:
                    continue
                seen_files.add(rel)
                related.append(rel)
                next_queue.append(rel)
                hop_found += 1
                if hop_found >= per_hop_limit:
                    break
            if hop_found >= per_hop_limit:
                break
        queue = next_queue
    return related
