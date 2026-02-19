"""
资产知识库服务
Asset Knowledge Service

从本地 Markdown 示例中加载领域-聚合根责任映射，
支持按接口 URL 从日志定位领域、聚合根、代码、数据库表与设计文档。
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.models.asset import CaseLibrary, DomainModel

logger = structlog.get_logger()


class AssetKnowledgeService:
    """基于本地 Markdown 的资产知识库"""

    DESIGN_FILE = "domain-aggregate-design.md"
    RESPONSIBILITY_FILE = "domain-aggregate-responsibility.md"
    CASE_FILE = "operations-case-library.md"

    def __init__(self, base_dir: Optional[Path] = None):
        default_dir = Path(__file__).resolve().parents[2] / "examples" / "assets"
        self._base_dir = base_dir or Path(os.getenv("ASSET_SAMPLE_DIR", str(default_dir)))
        self._cache: Optional[Dict[str, Any]] = None
        self._mtime_cache: Dict[str, float] = {}

    def load_catalog(self) -> Dict[str, Any]:
        """加载并缓存知识库。"""
        files = {
            "design": self._base_dir / self.DESIGN_FILE,
            "responsibility": self._base_dir / self.RESPONSIBILITY_FILE,
            "cases": self._base_dir / self.CASE_FILE,
        }

        if self._cache is not None and not self._is_changed(files):
            return self._cache

        catalog = {
            "design": self._read_frontmatter_json(files["design"]),
            "responsibility": self._read_frontmatter_json(files["responsibility"]),
            "cases": self._read_frontmatter_json(files["cases"]),
            "base_dir": str(self._base_dir),
        }

        self._cache = catalog
        self._mtime_cache = {
            str(path): path.stat().st_mtime for path in files.values() if path.exists()
        }

        logger.info(
            "asset_knowledge_loaded",
            base_dir=str(self._base_dir),
            domains=len(catalog["design"].get("domains", [])),
            mappings=len(catalog["responsibility"].get("mappings", [])),
            cases=len(catalog["cases"].get("cases", [])),
        )
        return catalog

    def locate_by_log(
        self,
        log_content: str,
        symptom: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        根据日志和现象定位领域-聚合根责任田。

        返回：领域、聚合根、代码资产、接口、数据库表、设计文档、运维案例。
        """
        catalog = self.load_catalog()
        mappings = catalog.get("responsibility", {}).get("mappings", [])
        design_domains = catalog.get("design", {}).get("domains", [])
        cases = catalog.get("cases", {}).get("cases", [])

        corpus = "\n".join(x for x in [log_content, symptom or ""] if x)
        interface_hints = self._extract_interface_hints(corpus)

        ranked: List[Tuple[int, Dict[str, Any], Optional[Dict[str, Any]]]] = []
        for mapping in mappings:
            score, endpoint = self._score_mapping(mapping, interface_hints, corpus)
            if score > 0:
                ranked.append((score, mapping, endpoint))

        ranked.sort(key=lambda x: x[0], reverse=True)

        if not ranked:
            return {
                "matched": False,
                "confidence": 0.0,
                "reason": "未命中责任田映射，请补充接口 URL 或方法名",
                "interface_hints": interface_hints,
                "domain": None,
                "aggregate": None,
                "owner_team": None,
                "owner": None,
                "matched_endpoint": None,
                "code_artifacts": [],
                "db_tables": [],
                "design_ref": None,
                "design_details": None,
                "similar_cases": [],
            }

        best_score, mapping, matched_endpoint = ranked[0]
        domain = mapping.get("domain")
        aggregate = mapping.get("aggregate")
        design_detail = self._find_design_detail(design_domains, domain, aggregate)
        similar_cases = self._find_similar_cases(cases, mapping, matched_endpoint, corpus)

        confidence = min(0.99, 0.35 + best_score * 0.06)

        return {
            "matched": True,
            "confidence": round(confidence, 3),
            "reason": "已根据接口 URL 命中责任田映射",
            "interface_hints": interface_hints,
            "domain": domain,
            "aggregate": aggregate,
            "owner_team": mapping.get("owner_team"),
            "owner": mapping.get("owner"),
            "matched_endpoint": matched_endpoint,
            "code_artifacts": mapping.get("code_artifacts", []),
            "db_tables": mapping.get("db_tables", []),
            "design_ref": (mapping.get("design_refs") or [None])[0],
            "design_details": design_detail,
            "similar_cases": similar_cases,
        }

    def build_bootstrap_models(self) -> Dict[str, List[Any]]:
        """将 Markdown 示例转换为 DomainModel / CaseLibrary。"""
        catalog = self.load_catalog()
        mappings = catalog.get("responsibility", {}).get("mappings", [])

        domain_models: List[DomainModel] = []
        for domain in catalog.get("design", {}).get("domains", []):
            domain_key = domain.get("domain", "")
            aggregates = domain.get("aggregates", [])

            entities: List[str] = []
            value_objects: List[str] = []
            domain_services: List[str] = []
            aggregate_names: List[str] = []

            for agg in aggregates:
                aggregate_names.append(agg.get("name", ""))
                entities.extend(agg.get("entities", []))
                value_objects.extend(agg.get("value_objects", []))
                domain_services.extend(agg.get("domain_services", []))

            mapping_hits = [m for m in mappings if m.get("domain") == domain_key]
            interfaces: List[Dict[str, Any]] = []
            db_tables: List[str] = []
            owner_team = None
            owner = None
            for hit in mapping_hits:
                interfaces.extend(hit.get("api_endpoints", []))
                db_tables.extend(hit.get("db_tables", []))
                owner_team = owner_team or hit.get("owner_team")
                owner = owner or hit.get("owner")

            model = DomainModel(
                name=domain_key,
                description=domain.get("description"),
                aggregates=[x for x in aggregate_names if x],
                entities=sorted(set(entities)),
                value_objects=sorted(set(value_objects)),
                domain_services=sorted(set(domain_services)),
                interfaces=interfaces,
                db_tables=sorted(set(db_tables)),
                owner_team=owner_team,
                owner=owner,
            )
            domain_models.append(model)

        cases: List[CaseLibrary] = []
        for raw in catalog.get("cases", {}).get("cases", []):
            try:
                created_at = raw.get("created_at")
                case = CaseLibrary(
                    id=raw["id"],
                    title=raw.get("title", raw["id"]),
                    description=raw.get("description", ""),
                    incident_type=raw.get("incident_type", "application_error"),
                    symptoms=raw.get("symptoms", []),
                    root_cause=raw.get("root_cause", ""),
                    root_cause_category=raw.get("root_cause_category", "unknown"),
                    solution=raw.get("solution", ""),
                    fix_steps=raw.get("fix_steps", []),
                    related_services=raw.get("related_services", []),
                    related_code=raw.get("related_code", []),
                    tags=raw.get("tags", []),
                    created_at=(
                        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if created_at
                        else datetime.utcnow()
                    ),
                )
                cases.append(case)
            except Exception as exc:
                logger.warning("asset_case_parse_failed", case_id=raw.get("id"), error=str(exc))

        return {
            "domain_models": domain_models,
            "cases": cases,
        }

    def _is_changed(self, files: Dict[str, Path]) -> bool:
        for path in files.values():
            if not path.exists():
                return True
            old = self._mtime_cache.get(str(path))
            cur = path.stat().st_mtime
            if old is None or old != cur:
                return True
        return False

    def _read_frontmatter_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            logger.warning("asset_sample_missing", path=str(path))
            return {}

        content = path.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            return {}

        parts = content.split("\n---\n", 1)
        if len(parts) < 2:
            return {}

        meta = parts[0].replace("---\n", "", 1).strip()
        try:
            return json.loads(meta)
        except json.JSONDecodeError as exc:
            logger.error("asset_sample_json_invalid", path=str(path), error=str(exc))
            return {}

    def _extract_interface_hints(self, text: str) -> List[Dict[str, str]]:
        hints: List[Dict[str, str]] = []
        seen = set()

        method_path_pattern = re.compile(
            r"\b(GET|POST|PUT|PATCH|DELETE)\s+((?:https?://[^\s\"']+)?/[A-Za-z0-9_\-./{}]+)",
            flags=re.IGNORECASE,
        )
        for method, raw_path in method_path_pattern.findall(text):
            path = self._normalize_path(raw_path)
            key = f"{method.upper()} {path}"
            if path and key not in seen:
                seen.add(key)
                hints.append({"method": method.upper(), "path": path})

        url_pattern = re.compile(r"https?://[^\s\"']+(/[A-Za-z0-9_\-./{}]+)")
        for raw_path in url_pattern.findall(text):
            path = self._normalize_path(raw_path)
            key = f"ANY {path}"
            if path and key not in seen:
                seen.add(key)
                hints.append({"method": "", "path": path})

        path_pattern = re.compile(r"(/api/[A-Za-z0-9_\-./{}]+)")
        for raw_path in path_pattern.findall(text):
            path = self._normalize_path(raw_path)
            key = f"ANY {path}"
            if path and key not in seen:
                seen.add(key)
                hints.append({"method": "", "path": path})

        # 兼容短路径输入，例如 "/orders 接口报错 502"
        # 后续在 score 阶段会与全路径（如 /api/v1/orders）做后缀比对。
        generic_path_pattern = re.compile(r"(/(?:[A-Za-z0-9_\-{}]+)(?:/[A-Za-z0-9_\-{}]+)*)")
        for raw_path in generic_path_pattern.findall(text):
            path = self._normalize_path(raw_path)
            key = f"ANY {path}"
            if path and key not in seen:
                seen.add(key)
                hints.append({"method": "", "path": path})

        return hints[:10]

    def _normalize_path(self, raw_path: str) -> str:
        path = raw_path.strip().rstrip('.,;:)')
        if "//" in path and path.startswith("http"):
            match = re.match(r"https?://[^/]+(/.*)", path)
            if match:
                path = match.group(1)
        if "?" in path:
            path = path.split("?", 1)[0]
        if "#" in path:
            path = path.split("#", 1)[0]
        if not path.startswith("/"):
            path = "/" + path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        return path

    def _score_mapping(
        self,
        mapping: Dict[str, Any],
        hints: List[Dict[str, str]],
        corpus: str,
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        best_score = 0
        best_endpoint: Optional[Dict[str, Any]] = None

        for endpoint in mapping.get("api_endpoints", []):
            endpoint_method = (endpoint.get("method") or "").upper()
            endpoint_path = self._normalize_path(endpoint.get("path") or "")
            endpoint_regex = self._path_template_to_regex(endpoint_path)

            for hint in hints:
                hint_method = (hint.get("method") or "").upper()
                hint_path = self._normalize_path(hint.get("path") or "")

                score = 0
                if hint_path and re.match(endpoint_regex, hint_path):
                    score += 8
                    if "{" not in endpoint_path and hint_path == endpoint_path:
                        score += 2
                elif hint_path and endpoint_path and hint_path.startswith(endpoint_path.rstrip("/")):
                    score += 3
                elif hint_path and endpoint_path and (
                    endpoint_path.endswith(hint_path) or hint_path.endswith(endpoint_path)
                ):
                    # 兼容短路径命中，例如 hint=/orders, endpoint=/api/v1/orders
                    score += 6

                if hint_method and endpoint_method and hint_method == endpoint_method:
                    score += 3

                if score > best_score:
                    best_score = score
                    best_endpoint = {
                        "method": endpoint_method,
                        "path": endpoint_path,
                        "service": endpoint.get("service"),
                        "interface": endpoint.get("interface"),
                        "matched_hint": hint,
                    }

        corpus_lower = corpus.lower()
        keyword_bonus = 0
        for kw in mapping.get("keywords", []):
            if kw and kw.lower() in corpus_lower:
                keyword_bonus += 1
                if keyword_bonus >= 3:
                    break

        return best_score + keyword_bonus, best_endpoint

    def _path_template_to_regex(self, template: str) -> str:
        escaped = re.escape(template)
        escaped = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", escaped)
        return f"^{escaped}$"

    def _find_design_detail(
        self,
        domains: List[Dict[str, Any]],
        domain: Optional[str],
        aggregate: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if not domain or not aggregate:
            return None

        for item in domains:
            if item.get("domain") != domain:
                continue
            for agg in item.get("aggregates", []):
                if agg.get("name") == aggregate:
                    return {
                        "domain": item.get("domain"),
                        "domain_name": item.get("name"),
                        "aggregate": agg.get("name"),
                        "description": agg.get("description"),
                        "invariants": agg.get("invariants", []),
                        "entities": agg.get("entities", []),
                        "value_objects": agg.get("value_objects", []),
                        "domain_services": agg.get("domain_services", []),
                        "events": agg.get("events", []),
                    }
        return None

    def _find_similar_cases(
        self,
        cases: List[Dict[str, Any]],
        mapping: Dict[str, Any],
        endpoint: Optional[Dict[str, Any]],
        corpus: str,
    ) -> List[Dict[str, Any]]:
        domain = mapping.get("domain")
        aggregate = mapping.get("aggregate")
        corpus_lower = corpus.lower()

        ranked: List[Tuple[int, Dict[str, Any]]] = []
        for case in cases:
            score = 0
            if case.get("domain") == domain:
                score += 3
            if case.get("aggregate") == aggregate:
                score += 3

            api_endpoint = (case.get("api_endpoint") or "").upper()
            if endpoint:
                expected = f"{endpoint.get('method', '').upper()} {endpoint.get('path', '')}".strip()
                if expected and expected in api_endpoint:
                    score += 4

            for signature in case.get("log_signatures", []):
                if signature and signature.lower() in corpus_lower:
                    score += 2

            if score > 0:
                ranked.append((score, case))

        ranked.sort(key=lambda x: x[0], reverse=True)

        output: List[Dict[str, Any]] = []
        for _, case in ranked[:3]:
            output.append(
                {
                    "id": case.get("id"),
                    "title": case.get("title"),
                    "api_endpoint": case.get("api_endpoint"),
                    "root_cause": case.get("root_cause"),
                    "solution": case.get("solution"),
                    "fix_steps": case.get("fix_steps", []),
                    "tags": case.get("tags", []),
                }
            )
        return output


asset_knowledge_service = AssetKnowledgeService()
