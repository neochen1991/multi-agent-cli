"""Helpers for loading and parsing source files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_repo_focus_windows(
    *,
    repo_path: str,
    candidate_files: List[str],
    max_files: int,
    max_chars: int,
) -> List[Dict[str, Any]]:
    root = Path(str(repo_path or "").strip())
    if not root.exists() or not root.is_dir():
        return []
    windows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw_name in candidate_files:
        name = str(raw_name or "").strip()
        if not name:
            continue
        normalized = name.lstrip("./")
        if normalized in seen:
            continue
        seen.add(normalized)
        file_path = resolve_repo_file(root, normalized)
        if file_path is None:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        windows.append(
            {
                "file": str(file_path.relative_to(root)),
                "excerpt": text[:max_chars],
            }
        )
        if len(windows) >= max_files:
            break
    return windows


def resolve_repo_file(root: Path, raw_name: str) -> Optional[Path]:
    normalized = str(raw_name or "").strip().lstrip("./")
    if not normalized:
        return None
    direct = root / normalized
    if direct.exists() and direct.is_file():
        return direct
    for item in root.rglob(Path(normalized).name):
        if item.is_file():
            try:
                rel = str(item.relative_to(root))
            except Exception:
                rel = str(item)
            if rel.endswith(normalized) or item.name == Path(normalized).name:
                return item
    return None


def load_source_units(root: Path, files: List[str]) -> List[Dict[str, Any]]:
    units: List[Dict[str, Any]] = []
    for raw_file in files:
        file_path = resolve_repo_file(root, raw_file)
        if file_path is None:
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        units.append(parse_source_unit(root=root, file_path=file_path, text=text))
    return units


def parse_source_unit(*, root: Path, file_path: Path, text: str) -> Dict[str, Any]:
    symbol_match = re.search(r"\bclass\s+([A-Z][A-Za-z0-9_]*)\b", text)
    symbol = str(symbol_match.group(1) if symbol_match else file_path.stem)
    fields = extract_field_types(text)
    methods = extract_methods(text)
    try:
        rel = str(file_path.relative_to(root))
    except Exception:
        rel = str(file_path)
    return {
        "symbol": symbol,
        "file": rel,
        "fields": fields,
        "methods": methods,
    }


def extract_field_types(text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for match in re.finditer(
        r"\b(?:private|protected|public)?\s*(?:final\s+)?([A-Z][A-Za-z0-9_<>]*)\s+([a-z][A-Za-z0-9_]*)\s*(?:[;=])",
        text,
    ):
        field_type = str(match.group(1) or "").split("<", 1)[0].strip()
        field_name = str(match.group(2) or "").strip()
        if field_name and field_type:
            fields[field_name] = field_type
    return fields


def extract_methods(text: str) -> Dict[str, Dict[str, Any]]:
    methods: Dict[str, Dict[str, Any]] = {}
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        match = re.search(
            r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:[\w<>\[\],?]+\s+)+([a-zA-Z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{?",
            line,
        )
        if not match:
            continue
        method_name = str(match.group(1) or "").strip()
        if method_name in {"if", "for", "while", "switch", "catch", "return", "new"}:
            continue
        body_lines = lines[idx - 1 : min(len(lines), idx + 8)]
        methods[method_name] = {
            "line": idx,
            "snippet": "\n".join(body_lines),
        }
    return methods


def guess_entry_method(source_units: List[Dict[str, Any]], hit_snippets: List[str]) -> str:
    for snippet in hit_snippets:
        match = re.search(r"\.\s*([a-zA-Z_][A-Za-z0-9_]*)\s*\(", str(snippet or ""))
        if match:
            return str(match.group(1) or "").strip()
    for unit in source_units:
        methods = unit.get("methods") if isinstance(unit.get("methods"), dict) else {}
        for name in methods:
            if name.lower().startswith(("create", "submit", "save", "update", "handle")):
                return str(name)
    if source_units:
        methods = source_units[0].get("methods") if isinstance(source_units[0].get("methods"), dict) else {}
        if methods:
            return str(next(iter(methods.keys())))
    return ""


def find_source_unit(
    source_units: List[Dict[str, Any]],
    symbol: str,
    *,
    preferred_file: str = "",
) -> Optional[Dict[str, Any]]:
    normalized_symbol = str(symbol or "").strip()
    normalized_file = str(preferred_file or "").strip()
    for unit in source_units:
        if normalized_file and str(unit.get("file") or "").strip() == normalized_file:
            return unit
    for unit in source_units:
        if str(unit.get("symbol") or "").strip() == normalized_symbol:
            return unit
    return None
