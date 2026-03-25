"""Agent Skill 路由服务。

负责从本地 `SKILL.md` 文档中加载可用 Skill，并根据 Agent 名称、命令内容和上下文选择应注入的 Skill。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.models.tooling import AgentSkillConfig


@dataclass
class SkillDoc:
    """单个 Skill 文档的结构化表示。"""

    name: str
    description: str
    path: str
    triggers: List[str]
    allowed_agents: List[str]
    required_tools: List[str]
    content: str


class AgentSkillService:
    """加载本地 Skill 文档并匹配到具体 Agent 命令。"""

    SKILL_SUFFIX = "SKILL.md"

    def select_skills(
        self,
        *,
        agent_name: str,
        cfg: AgentSkillConfig,
        assigned_command: Optional[Dict[str, Any]],
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """为当前 Agent 选择应注入的 Skill。

        选择顺序是：先看全局开关和 Agent 白名单，再尝试命令中的 `skill_hints`，最后回退到基于文本相关度的匹配。
        """
        if not bool(cfg.enabled):
            return {
                "enabled": False,
                "used": False,
                "status": "disabled",
                "summary": "Skill 开关关闭。",
                "skills": [],
                "audit_log": [],
            }

        allowed_agents = [str(item or "").strip() for item in (cfg.allowed_agents or []) if str(item or "").strip()]
        if allowed_agents and agent_name not in allowed_agents:
            return {
                "enabled": True,
                "used": False,
                "status": "skipped_by_agent",
                "summary": f"{agent_name} 不在 Skill 允许列表中。",
                "skills": [],
                "audit_log": [],
            }

        primary_dir = self._resolve_skills_dir(str(cfg.skills_dir or "").strip())
        extension_dir = self._resolve_skills_dir(str(cfg.extensions_dir or "").strip())
        scanned_dirs: List[Path] = []
        if primary_dir.exists() and primary_dir.is_dir():
            scanned_dirs.append(primary_dir)
        if bool(getattr(cfg, "extensions_enabled", False)) and extension_dir.exists() and extension_dir.is_dir():
            if extension_dir.resolve() != primary_dir.resolve():
                scanned_dirs.append(extension_dir)
        if not scanned_dirs:
            return {
                "enabled": True,
                "used": False,
                "status": "unavailable",
                "summary": f"Skill 目录不可用: {primary_dir}",
                "skills": [],
                "audit_log": [],
            }

        docs: List[SkillDoc] = []
        for scan_dir in scanned_dirs:
            docs.extend(self._load_skill_docs(skills_dir=scan_dir, max_chars=int(cfg.max_skill_chars)))
        if not docs:
            return {
                "enabled": True,
                "used": False,
                "status": "empty",
                "summary": "未发现可用 Skill 文档。",
                "skills": [],
                "audit_log": [],
            }

        explicit_hints = self._extract_skill_hints(assigned_command)
        if explicit_hints:
            explicit_selected = self._select_by_explicit_hints(
                agent_name=agent_name,
                docs=docs,
                hints=explicit_hints,
            )
            if explicit_selected:
                skills = [
                    {
                        "name": doc.name,
                        "description": doc.description,
                        "path": doc.path,
                        "triggers": doc.triggers[:10],
                        "required_tools": doc.required_tools[:8],
                        "content": doc.content,
                        "score": 9.999,
                    }
                    for doc in explicit_selected[: max(1, int(cfg.max_skills or 1))]
                ]
                return {
                    "enabled": True,
                    "used": True,
                    "status": "ok",
                    "summary": f"按命令 skill_hints 命中 {len(skills)} 个 Skill：{', '.join(item['name'] for item in skills)}",
                    "skills": skills,
                    "audit_log": [
                        {
                            "action": "skill_select",
                            "status": "ok",
                            "detail": {
                                "agent_name": agent_name,
                                "skills_dir": [str(item) for item in scanned_dirs],
                                "mode": "explicit_hints",
                                "hints": explicit_hints,
                                "selected": [item["name"] for item in skills],
                            },
                        }
                    ],
                }

        query_text = self._build_query_text(
            assigned_command=assigned_command,
            compact_context=compact_context,
            incident_context=incident_context,
        )
        ranked = self._rank_skills(agent_name=agent_name, query_text=query_text, docs=docs)
        selected = ranked[: max(1, int(cfg.max_skills or 1))]

        if not selected:
            return {
                "enabled": True,
                "used": False,
                "status": "no_match",
                "summary": "当前命令未匹配到合适 Skill。",
                "skills": [],
                "audit_log": [],
            }

        skills = [
            {
                "name": doc.name,
                "description": doc.description,
                "path": doc.path,
                "triggers": doc.triggers[:10],
                "required_tools": doc.required_tools[:8],
                "content": doc.content,
                "score": round(score, 4),
            }
            for doc, score in selected
        ]
        return {
            "enabled": True,
            "used": True,
            "status": "ok",
            "summary": f"命中 {len(skills)} 个 Skill：{', '.join(item['name'] for item in skills)}",
            "skills": skills,
            "audit_log": [
                {
                    "action": "skill_select",
                    "status": "ok",
                    "detail": {
                        "agent_name": agent_name,
                        "skills_dir": [str(item) for item in scanned_dirs],
                        "selected": [item["name"] for item in skills],
                    },
                }
            ],
        }

    @staticmethod
    def _extract_skill_hints(assigned_command: Optional[Dict[str, Any]]) -> List[str]:
        """对输入执行提取Skillhints，将原始数据整理为稳定的内部结构。"""
        command = dict(assigned_command or {})
        raw = command.get("skill_hints")
        if not isinstance(raw, list):
            return []
        picks: List[str] = []
        for item in raw:
            text = str(item or "").strip().lower()
            if not text:
                continue
            picks.append(text[:80])
        return list(dict.fromkeys(picks))[:8]

    @staticmethod
    def _select_by_explicit_hints(*, agent_name: str, docs: List[SkillDoc], hints: List[str]) -> List[SkillDoc]:
        """执行选择byexplicithints，用于驱动当前阶段的策略选择或状态流转。"""
        selected: List[SkillDoc] = []
        for hint in hints:
            for doc in docs:
                if doc.allowed_agents and agent_name not in doc.allowed_agents:
                    continue
                if doc in selected:
                    continue
                doc_name = str(doc.name or "").strip().lower()
                folder_name = Path(doc.path).parent.name.strip().lower()
                if hint in {doc_name, folder_name}:
                    selected.append(doc)
        return selected

    def _resolve_skills_dir(self, raw: str) -> Path:
        """解析 Skill 目录；相对路径按仓库根目录展开。"""
        if not raw:
            return Path.cwd() / "backend" / "skills"
        path = Path(raw)
        if path.is_absolute():
            return path
        return (Path.cwd() / path).resolve()

    def _load_skill_docs(self, *, skills_dir: Path, max_chars: int) -> List[SkillDoc]:
        """递归读取 Skill 文档并解析基础元信息。"""
        docs: List[SkillDoc] = []
        for file in sorted(skills_dir.rglob(f"*{self.SKILL_SUFFIX}")):
            try:
                raw = file.read_text(encoding="utf-8")
            except Exception:
                continue
            meta, content = self._parse_skill(raw)
            metadata = self._load_metadata(file.parent)
            name = str(meta.get("name") or file.parent.name or file.stem).strip()
            description = str(meta.get("description") or metadata.get("description") or "").strip()
            trigger_text = str(meta.get("triggers") or "").strip()
            activation_hint_text = self._csv_join(metadata.get("activation_hints"))
            triggers = [
                item.strip().lower()
                for item in re.split(r"[,\n|]+", f"{trigger_text}\n{activation_hint_text}")
                if item.strip()
            ]
            allowed_text = str(meta.get("agents") or "").strip()
            metadata_agents = self._csv_join(metadata.get("applicable_experts"), metadata.get("bound_experts"))
            allowed_agents = [
                item.strip()
                for item in re.split(r"[,\n|]+", f"{allowed_text}\n{metadata_agents}")
                if item.strip()
            ]
            required_tools = self._normalize_list(metadata.get("required_tools"))
            docs.append(
                SkillDoc(
                    name=name,
                    description=description,
                    path=str(file),
                    triggers=triggers,
                    allowed_agents=allowed_agents,
                    required_tools=required_tools,
                    content=content[: max(200, int(max_chars))].strip(),
                )
            )
        return docs

    @staticmethod
    def _load_metadata(skill_dir: Path) -> Dict[str, Any]:
        """读取可选 metadata.json；缺失或异常时回退空对象。"""
        metadata_file = skill_dir / "metadata.json"
        if not metadata_file.exists():
            return {}
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _normalize_list(value: Any) -> List[str]:
        items = value if isinstance(value, list) else []
        picks: List[str] = []
        for item in items:
            text = str(item or "").strip()
            if text:
                picks.append(text)
        return list(dict.fromkeys(picks))

    def _csv_join(self, *values: Any) -> str:
        picks: List[str] = []
        for value in values:
            if isinstance(value, list):
                picks.extend([str(item or "").strip() for item in value if str(item or "").strip()])
            elif isinstance(value, str) and value.strip():
                picks.append(value.strip())
        return ",".join(picks)

    def _parse_skill(self, text: str) -> Tuple[Dict[str, str], str]:
        """解析 Skill 文档 front matter 和正文。"""
        raw = str(text or "")
        if raw.startswith("---\n"):
            end_idx = raw.find("\n---", 4)
            if end_idx > 0:
                head = raw[4:end_idx]
                body = raw[end_idx + 4 :].strip()
                meta = self._parse_front_matter(head)
                return meta, body
        return {}, raw.strip()

    @staticmethod
    def _parse_front_matter(head: str) -> Dict[str, str]:
        """对输入执行解析frontmatter，将原始数据整理为稳定的内部结构。"""
        meta: Dict[str, str] = {}
        for line in str(head or "").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[str(key).strip().lower()] = str(value).strip()
        return meta

    def _rank_skills(self, *, agent_name: str, query_text: str, docs: List[SkillDoc]) -> List[Tuple[SkillDoc, float]]:
        """按文本相关度给 Skill 打分，并过滤掉不适用的 Agent。"""
        query_tokens = self._tokenize(query_text)
        ranked: List[Tuple[SkillDoc, float]] = []
        for doc in docs:
            if doc.allowed_agents and agent_name not in doc.allowed_agents:
                continue
            score = 0.0
            doc_text = f"{doc.name}\n{doc.description}\n{' '.join(doc.triggers)}".lower()
            doc_tokens = self._tokenize(doc_text)
            if doc.name.lower() in query_text:
                score += 1.8
            overlap = len(query_tokens.intersection(doc_tokens))
            score += overlap * 0.35
            if any(trigger in query_text for trigger in doc.triggers):
                score += 1.2
            if score > 0:
                ranked.append((doc, score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    @staticmethod
    def _build_query_text(
        *,
        assigned_command: Optional[Dict[str, Any]],
        compact_context: Dict[str, Any],
        incident_context: Dict[str, Any],
    ) -> str:
        """构建构建query文本，供后续节点或调用方直接使用。"""
        command = dict(assigned_command or {})
        fields = [
            str(command.get("task") or ""),
            str(command.get("focus") or ""),
            str(command.get("expected_output") or ""),
            str(compact_context.get("log_excerpt") or ""),
            str((compact_context.get("interface_mapping") or {}).get("domain") or ""),
            str((incident_context.get("incident") or {}).get("service_name") or ""),
            str((incident_context.get("incident") or {}).get("description") or ""),
        ]
        return " ".join(item for item in fields if item).strip().lower()

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """执行分词相关逻辑，并为当前模块提供可复用的处理能力。"""
        return {item for item in re.split(r"[^a-z0-9_\u4e00-\u9fff]+", str(text or "").lower()) if len(item) >= 2}


agent_skill_service = AgentSkillService()
