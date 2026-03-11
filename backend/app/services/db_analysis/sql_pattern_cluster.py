"""Cluster SQL statements into lightweight access patterns."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def build_sql_pattern_clusters(*, tool_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    queries: List[str] = []
    for bucket in ("slow_sql", "top_sql", "keyword_hits"):
        for item in list(tool_data.get(bucket) or [])[:12]:
            if isinstance(item, dict) and str(item.get("query") or "").strip():
                queries.append(str(item.get("query") or "").strip())
    clusters: Dict[str, Dict[str, Any]] = {}
    for query in queries:
        lowered = query.lower()
        verb_match = re.match(r"^\s*(select|update|insert|delete)\b", lowered)
        verb = str(verb_match.group(1) or "other") if verb_match else "other"
        table_match = re.search(r"\bfrom\s+([a-zA-Z0-9_.]+)|\bupdate\s+([a-zA-Z0-9_.]+)|\binto\s+([a-zA-Z0-9_.]+)", lowered)
        table = next((group for group in (table_match.groups() if table_match else ()) if group), "unknown")
        key = f"{verb}:{table}"
        bucket = clusters.setdefault(key, {"pattern": key, "samples": [], "count": 0})
        bucket["count"] += 1
        if len(bucket["samples"]) < 3:
            bucket["samples"].append(query[:220])
    return list(clusters.values())[:8]
