"""Output parsing and normalization helpers for LangGraph runtime agents."""

from __future__ import annotations

import json
import re
from hashlib import sha1
from typing import Any, Dict, List, Optional

from app.core.json_utils import extract_json_dict


def _strip_code_fence(text: str) -> str:
    """去掉外层 Markdown code fence，便于后续继续抽取结构化字段。"""
    raw = str(text or "").strip()
    if not raw.startswith("```"):
        return raw
    matched = re.match(r"^```(?:json|JSON)?\s*([\s\S]*?)\s*```$", raw)
    if matched:
        return str(matched.group(1) or "").strip()
    return raw


def extract_readable_text(
    value: Any,
    *,
    preferred_keys: Optional[List[str]] = None,
    fallback: str = "",
    max_len: int = 400,
) -> str:
    """从 JSON 片段、代码块或普通字符串里提取适合展示的自然语言文本。"""
    preferred = list(preferred_keys or ["summary", "conclusion", "chat_message", "analysis", "message"])

    def _inner(obj: Any, *, depth: int = 0) -> str:
        if depth > 4:
            return ""
        if isinstance(obj, dict):
            for key in preferred:
                text = _inner(obj.get(key), depth=depth + 1)
                if text:
                    return text
            for nested_key in ("root_cause", "final_judgment", "fix_recommendation"):
                text = _inner(obj.get(nested_key), depth=depth + 1)
                if text:
                    return text
            return ""
        if isinstance(obj, list):
            for item in obj:
                text = _inner(item, depth=depth + 1)
                if text:
                    return text
            return ""
        text = str(obj or "").strip()
        if not text:
            return ""
        raw = _strip_code_fence(text)
        parsed = extract_json_dict(raw)
        if isinstance(parsed, dict) and parsed:
            nested = _inner(parsed, depth=depth + 1)
            if nested:
                return nested
        parsed = extract_largest_json_dict(raw)
        if parsed:
            nested = _inner(parsed, depth=depth + 1)
            if nested:
                return nested
        lowered = raw.lower()
        if lowered.startswith("我的判断是："):
            raw = raw.split("：", 1)[-1].strip()
            reparsed = extract_json_dict(_strip_code_fence(raw)) or extract_largest_json_dict(_strip_code_fence(raw))
            if isinstance(reparsed, dict) and reparsed:
                nested = _inner(reparsed, depth=depth + 1)
                if nested:
                    return nested
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw[:max_len]

    text = _inner(value)
    if text:
        return text[:max_len]
    return str(fallback or "").strip()[:max_len]


def extract_balanced_object(text: str, start_index: int) -> Optional[str]:
    """对输入执行提取balancedobject，将原始数据整理为稳定的内部结构。"""
    if start_index < 0 or start_index >= len(text) or text[start_index] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start_index, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_index : i + 1]
    return None


def extract_object_by_named_key(text: str, key_name: str) -> Optional[Dict[str, Any]]:
    """对输入执行提取objectbynamedkey，将原始数据整理为稳定的内部结构。"""
    marker = f'"{key_name}"'
    search_start = 0
    while True:
        key_index = text.find(marker, search_start)
        if key_index < 0:
            return None
        colon_index = text.find(":", key_index + len(marker))
        if colon_index < 0:
            return None
        brace_index = text.find("{", colon_index + 1)
        if brace_index < 0:
            return None
        candidate_text = extract_balanced_object(text, brace_index)
        search_start = key_index + len(marker)
        if not candidate_text:
            continue
        try:
            parsed = json.loads(candidate_text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed


def extract_top_level_json_with_key(text: str, required_key: str) -> Optional[Dict[str, Any]]:
    """对输入执行提取topleveljsonwithkey，将原始数据整理为稳定的内部结构。"""
    matched_payload: Optional[Dict[str, Any]] = None
    matched_length = 0
    marker = f'"{required_key}"'
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        candidate_text = extract_balanced_object(text, start)
        if not candidate_text or marker not in candidate_text:
            continue
        try:
            parsed = json.loads(candidate_text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and required_key in parsed and len(candidate_text) > matched_length:
            matched_payload = parsed
            matched_length = len(candidate_text)
    return matched_payload


def extract_confidence_hint(text: str, fallback: float = 0.5) -> float:
    """对输入执行提取confidencehint，将原始数据整理为稳定的内部结构。"""
    matches = re.findall(r'"confidence"\s*:\s*(-?\d+(?:\.\d+)?)', text)
    if not matches:
        return fallback
    try:
        value = float(matches[-1])
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, value))


def extract_largest_json_dict(text: str) -> Dict[str, Any]:
    """对输入执行提取largestjsondict，将原始数据整理为稳定的内部结构。"""
    raw = str(text or "")
    if not raw.strip():
        return {}
    best: Dict[str, Any] = {}
    best_len = 0
    for start, ch in enumerate(raw):
        if ch != "{":
            continue
        candidate = extract_balanced_object(raw, start)
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and len(candidate) > best_len:
            best = parsed
            best_len = len(candidate)
    return best


def extract_mixed_json_dict(raw_content: str) -> Dict[str, Any]:
    """对输入执行提取mixedjsondict，将原始数据整理为稳定的内部结构。"""
    raw_text = str(raw_content or "")
    parsed = extract_json_dict(raw_text) or {}
    if isinstance(parsed, dict) and parsed:
        return parsed
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw_text, flags=re.IGNORECASE):
        parsed = extract_json_dict(block) or {}
        if isinstance(parsed, dict) and parsed:
            return parsed
        parsed = extract_largest_json_dict(block)
        if parsed:
            return parsed
    return extract_largest_json_dict(raw_text)


def parse_judge_payload(raw_content: str) -> Dict[str, Any]:
    """对输入执行解析裁决载荷，将原始数据整理为稳定的内部结构。"""
    raw_text = str(raw_content or "")
    if not raw_text.strip():
        return {}

    top_level_payload = extract_top_level_json_with_key(raw_text, "final_judgment")
    if isinstance(top_level_payload, dict):
        return top_level_payload

    final_judgment = extract_object_by_named_key(raw_text, "final_judgment")
    if isinstance(final_judgment, dict) and final_judgment:
        root_cause_hint = final_judgment.get("root_cause")
        root_confidence = 0.5
        if isinstance(root_cause_hint, dict):
            try:
                root_confidence = float(root_cause_hint.get("confidence") or 0.5)
            except (TypeError, ValueError):
                root_confidence = 0.5
        return {
            "final_judgment": final_judgment,
            "confidence": extract_confidence_hint(raw_text, fallback=root_confidence),
        }

    generic_payload = extract_json_dict(raw_text) or {}
    if isinstance(generic_payload, dict) and "final_judgment" in generic_payload:
        return generic_payload

    if isinstance(generic_payload, dict) and any(
        k in generic_payload for k in ("root_cause", "evidence_chain", "fix_recommendation")
    ):
        return {
            "final_judgment": generic_payload,
            "confidence": extract_confidence_hint(raw_text, fallback=0.5),
        }

    return generic_payload if isinstance(generic_payload, dict) else {}


def normalize_normal_output(parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
    """对输入执行归一化normaloutput，将原始数据整理为稳定的内部结构。"""
    chat_message = extract_readable_text(parsed.get("chat_message"), fallback="")
    analysis = extract_readable_text(
        parsed.get("analysis"),
        preferred_keys=["symptom_summary", "summary", "analysis", "chat_message", "conclusion"],
        fallback="",
        max_len=600,
    )
    conclusion = extract_readable_text(
        parsed.get("conclusion") or analysis or "",
        preferred_keys=["summary", "conclusion", "chat_message", "analysis"],
        fallback=analysis,
        max_len=420,
    )
    evidence = _normalize_evidence_items(parsed.get("evidence_chain"), source_hint="analysis", max_items=5)

    confidence = parsed.get("confidence")
    try:
        confidence_value = float(confidence)
    except Exception:
        confidence_value = 0.66 if analysis or conclusion else 0.45
    confidence_value = max(0.0, min(1.0, confidence_value))

    if not analysis and raw_content:
        analysis = extract_readable_text(raw_content, fallback=raw_content[:220], max_len=600)
    if not conclusion:
        conclusion = analysis
    if not chat_message:
        if conclusion and analysis and conclusion != analysis:
            chat_message = f"我的判断是：{conclusion}。依据是：{analysis[:120]}"
        elif conclusion:
            chat_message = f"我的判断是：{conclusion}"
        elif raw_content:
            chat_message = raw_content[:180]

    def _normalize_text_list(value: Any, limit: int = 6) -> List[str]:
        """对输入执行归一化文本列出，将原始数据整理为稳定的内部结构。"""
        if isinstance(value, list):
            items = value
        elif isinstance(value, str) and value.strip():
            items = [value]
        else:
            items = []
        return [str(item).strip()[:220] for item in items if str(item).strip()][:limit]

    return {
        "chat_message": chat_message[:260],
        "analysis": analysis,
        "conclusion": conclusion,
        "evidence_chain": evidence,
        "open_questions": _normalize_text_list(parsed.get("open_questions")),
        "missing_info": _normalize_text_list(parsed.get("missing_info")),
        "needs_validation": _normalize_text_list(parsed.get("needs_validation")),
        "confidence": confidence_value,
        "raw_text": raw_content[:1200],
    }


def normalize_verification_output(parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
    """对输入执行归一化verificationoutput，将原始数据整理为稳定的内部结构。"""
    base = normalize_normal_output(parsed, raw_content)
    raw_plan = parsed.get("verification_plan")
    plan: List[Dict[str, Any]] = []
    if isinstance(raw_plan, list):
        for idx, item in enumerate(raw_plan[:8], start=1):
            if isinstance(item, dict):
                plan.append(
                    {
                        "id": str(item.get("id") or f"ver_{idx}"),
                        "dimension": str(item.get("dimension") or "functional"),
                        "objective": str(item.get("objective") or "")[:220],
                        "steps": [str(step).strip()[:240] for step in (item.get("steps") or []) if str(step).strip()][:6],
                        "pass_criteria": str(item.get("pass_criteria") or "")[:220],
                        "owner": str(item.get("owner") or "待确认"),
                        "priority": str(item.get("priority") or "p1"),
                    }
                )
            else:
                text = str(item or "").strip()
                if text:
                    plan.append(
                        {
                            "id": f"ver_{idx}",
                            "dimension": "functional",
                            "objective": text[:220],
                            "steps": [text[:220]],
                            "pass_criteria": "目标达成且无新增错误",
                            "owner": "待确认",
                            "priority": "p1",
                        }
                    )
    if not plan:
        conclusion = str(base.get("conclusion") or "完成修复后执行功能与性能回归验证")[:220]
        plan = [
            {
                "id": "ver_1",
                "dimension": "functional",
                "objective": conclusion,
                "steps": [conclusion],
                "pass_criteria": "核心接口成功率恢复",
                "owner": "待确认",
                "priority": "p0",
            }
        ]
    base["verification_plan"] = plan
    return base


def normalize_commander_output(parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
    """对输入执行归一化主Agentoutput，将原始数据整理为稳定的内部结构。"""
    normalized = normalize_normal_output(parsed, raw_content)

    def _normalize_tables(value: Any) -> List[str]:
        """对输入执行归一化tables，将原始数据整理为稳定的内部结构。"""
        if not isinstance(value, list):
            return []
        picks: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            picks.append(text[:120])
        return list(dict.fromkeys(picks))[:20]

    def _normalize_skill_hints(value: Any) -> List[str]:
        """对输入执行归一化Skillhints，将原始数据整理为稳定的内部结构。"""
        if not isinstance(value, list):
            return []
        picks: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            picks.append(text[:80])
        return list(dict.fromkeys(picks))[:8]

    commands_raw = parsed.get("commands")
    commands: List[Dict[str, Any]] = []
    if isinstance(commands_raw, list):
        for item in commands_raw[:10]:
            if not isinstance(item, dict):
                continue
            target_agent = str(item.get("target_agent") or "").strip()
            if not target_agent:
                continue
            commands.append(
                {
                    "target_agent": target_agent,
                    "task": str(item.get("task") or "").strip(),
                    "focus": str(item.get("focus") or "").strip(),
                    "expected_output": str(item.get("expected_output") or "").strip(),
                    "use_tool": item.get("use_tool"),
                    "database_tables": _normalize_tables(item.get("database_tables")),
                    "skill_hints": _normalize_skill_hints(item.get("skill_hints")),
                }
            )
    if not commands:
        commands = _extract_commander_commands_from_markdown(raw_content)
    if not str(normalized.get("chat_message") or "").strip():
        normalized["chat_message"] = "我来拆解问题并给各专家Agent下达命令。"
    normalized["commands"] = commands
    next_mode = str(parsed.get("next_mode") or "").strip().lower()
    next_agent = str(parsed.get("next_agent") or "").strip()
    should_stop = parsed.get("should_stop")
    if isinstance(should_stop, str):
        should_stop_value = should_stop.strip().lower() in ("1", "true", "yes", "y", "是")
    else:
        should_stop_value = bool(should_stop)
    normalized["next_mode"] = next_mode
    normalized["next_agent"] = next_agent
    normalized["should_stop"] = should_stop_value
    normalized["stop_reason"] = str(parsed.get("stop_reason") or "").strip()[:240]
    should_pause_for_review = parsed.get("should_pause_for_review")
    if isinstance(should_pause_for_review, str):
        pause_for_review_value = should_pause_for_review.strip().lower() in ("1", "true", "yes", "y", "是")
    else:
        pause_for_review_value = bool(should_pause_for_review)
    review_payload = parsed.get("review_payload")
    normalized["should_pause_for_review"] = pause_for_review_value
    normalized["review_reason"] = str(parsed.get("review_reason") or "").strip()[:240]
    normalized["review_payload"] = review_payload if isinstance(review_payload, dict) else {}
    return normalized


def _extract_commander_commands_from_markdown(raw_content: str) -> List[Dict[str, Any]]:
    """
    当 commander 漂成 Markdown 表格时，尽量把表格行回收成最小可执行命令。

    这是兜底，不替代正常的结构化 JSON 输出。
    """
    text = str(raw_content or "")
    if "| **target_agent** |" not in text:
        return []

    row_commands = _extract_commander_commands_from_markdown_rows(text)
    if row_commands:
        return row_commands

    commands: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    field_map = {
        "target_agent": "target_agent",
        "task": "task",
        "focus": "focus",
        "expected_output": "expected_output",
        "use_tool": "use_tool",
        "database_tables": "database_tables",
        "skill_hints": "skill_hints",
    }

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or line.startswith("|:---"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        key = parts[0].replace("**", "").strip().lower()
        value = parts[1].strip()
        mapped = field_map.get(key)
        if not mapped:
            continue
        if mapped == "target_agent":
            if current.get("target_agent"):
                commands.append(current)
            current = {
                "target_agent": value,
                "task": "",
                "focus": "",
                "expected_output": "",
                "use_tool": None,
                "database_tables": [],
                "skill_hints": [],
            }
            continue
        if not current:
            continue
        if mapped == "use_tool":
            normalized_value = value.strip().lower()
            current["use_tool"] = normalized_value in {"true", "1", "yes", "y", "是"}
            continue
        if mapped == "database_tables":
            current["database_tables"] = _normalize_commander_tables(_split_markdown_list(value))
            continue
        if mapped == "skill_hints":
            current["skill_hints"] = _normalize_commander_skill_hints(_split_markdown_list(value))
            continue
        current[mapped] = value

    if current.get("target_agent"):
        commands.append(current)
    return commands[:10]


def _extract_commander_commands_from_markdown_rows(text: str) -> List[Dict[str, Any]]:
    """从标准 Markdown 横表中回收 commander 命令。"""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip().startswith("|")]
    if len(lines) < 3:
        return []

    header_line = lines[0]
    separator_line = lines[1]
    if "| **target_agent** |" not in header_line or ":---" not in separator_line:
        return []

    headers = [part.strip().replace("**", "").lower() for part in header_line.strip("|").split("|")]
    commands: List[Dict[str, Any]] = []
    field_map = {
        "target_agent": "target_agent",
        "task": "task",
        "focus": "focus",
        "expected_output": "expected_output",
        "use_tool": "use_tool",
        "database_tables": "database_tables",
        "skill_hints": "skill_hints",
    }

    for raw_line in lines[2:]:
        if raw_line.startswith("|:---"):
            continue
        parts = [part.strip() for part in raw_line.strip("|").split("|")]
        if len(parts) < len(headers):
            parts.extend([""] * (len(headers) - len(parts)))
        row = {headers[idx]: parts[idx] for idx in range(min(len(headers), len(parts)))}
        target_agent = str(row.get("target_agent") or "").strip()
        if not target_agent:
            continue
        use_tool_text = str(row.get("use_tool") or "").strip().lower()
        commands.append(
            {
                "target_agent": target_agent,
                "task": str(row.get("task") or "").strip(),
                "focus": str(row.get("focus") or "").strip(),
                "expected_output": str(row.get("expected_output") or "").strip(),
                "use_tool": use_tool_text in {"true", "1", "yes", "y", "是"} if use_tool_text else None,
                "database_tables": _normalize_commander_tables(_split_markdown_list(row.get("database_tables") or "")),
                "skill_hints": _normalize_commander_skill_hints(_split_markdown_list(row.get("skill_hints") or "")),
            }
        )

    return commands[:10]


def _split_markdown_list(value: str) -> List[str]:
    """把 Markdown 风格的数组/列表值拆成普通字符串数组。"""
    text = str(value or "").strip()
    if not text:
        return []
    stripped = text.strip("[]")
    picks: List[str] = []
    for item in stripped.split(","):
        cleaned = item.strip().strip('"').strip("'")
        if cleaned:
            picks.append(cleaned)
    return picks


def _normalize_commander_tables(value: Any) -> List[str]:
    """归一化 commander 命令里的表名数组。"""
    if not isinstance(value, list):
        return []
    picks: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        picks.append(text[:120])
    return list(dict.fromkeys(picks))[:20]


def _normalize_commander_skill_hints(value: Any) -> List[str]:
    """归一化 commander 命令里的 skill hints 数组。"""
    if not isinstance(value, list):
        return []
    picks: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        picks.append(text[:80])
    return list(dict.fromkeys(picks))[:8]


def normalize_judge_output(
    parsed: Dict[str, Any],
    raw_content: str,
    *,
    fallback_summary: str,
) -> Dict[str, Any]:
    """对输入执行归一化裁决output，将原始数据整理为稳定的内部结构。"""
    chat_message = str(parsed.get("chat_message") or "").strip()
    final_judgment = parsed.get("final_judgment")
    if not isinstance(final_judgment, dict) and any(
        key in parsed for key in ("root_cause", "evidence_chain", "fix_recommendation")
    ):
        final_judgment = parsed
    if not isinstance(final_judgment, dict):
        final_judgment = {}

    root_cause = final_judgment.get("root_cause")
    if isinstance(root_cause, str):
        root_cause = {
            "summary": extract_readable_text(root_cause, fallback=str(root_cause or "")),
            "category": "unknown",
            "confidence": 0.6,
        }
    elif not isinstance(root_cause, dict):
        recovered_root = extract_object_by_named_key(str(raw_content or ""), "root_cause")
        if isinstance(recovered_root, dict) and recovered_root.get("summary"):
            root_cause = recovered_root
        else:
            root_cause = {
                "summary": fallback_summary,
                "category": "unknown",
                "confidence": 0.5,
            }
    if isinstance(root_cause, dict):
        summary = extract_readable_text(root_cause.get("summary"), fallback=str(root_cause.get("summary") or ""))
        if not summary:
            root_cause["summary"] = fallback_summary
        else:
            root_cause["summary"] = summary
        if not root_cause.get("category"):
            root_cause["category"] = "unknown"
        try:
            root_cause["confidence"] = max(0.0, min(1.0, float(root_cause.get("confidence") or 0.5)))
        except (TypeError, ValueError):
            root_cause["confidence"] = 0.5
    else:
        root_cause = {
            "summary": fallback_summary,
            "category": "unknown",
            "confidence": 0.5,
        }

    evidence_chain = final_judgment.get("evidence_chain")
    if not isinstance(evidence_chain, list):
        evidence_chain = []
    evidence_items: List[Dict[str, Any]] = []
    for index, item in enumerate(evidence_chain[:6], start=1):
        if isinstance(item, dict):
            description_text = str(
                item.get("description") or item.get("evidence") or item.get("summary") or ""
            ).strip()
            source_text = str(item.get("source") or "langgraph")
            source_ref_text = str(item.get("source_ref") or item.get("location") or "")
            evidence_items.append(
                {
                    "evidence_id": str(item.get("evidence_id") or _evidence_id(description_text, source_ref_text, source_text, index)),
                    "type": str(item.get("type") or "analysis"),
                    "description": description_text,
                    "source": source_text,
                    "source_ref": source_ref_text,
                    "location": item.get("location"),
                    "strength": str(item.get("strength") or "medium"),
                }
            )
        else:
            description_text = str(item).strip()
            evidence_items.append(
                {
                    "evidence_id": _evidence_id(description_text, "", "langgraph", index),
                    "type": "analysis",
                    "description": description_text,
                    "source": "langgraph",
                    "source_ref": "",
                    "location": None,
                    "strength": "medium",
                }
            )

    fix_recommendation = final_judgment.get("fix_recommendation")
    if not isinstance(fix_recommendation, dict):
        fix_recommendation = {
            "summary": "建议先进行止损并补充监控告警",
            "steps": [],
            "code_changes_required": True,
            "rollback_recommended": False,
            "testing_requirements": [],
        }

    fix_recommendation["summary"] = extract_readable_text(
        fix_recommendation.get("summary"),
        fallback=str(fix_recommendation.get("summary") or "建议先进行止损并补充监控告警"),
        max_len=420,
    )
    fix_recommendation["steps"] = [
        extract_readable_text(item, fallback=str(item or ""), max_len=220)
        for item in list(fix_recommendation.get("steps") or [])
        if extract_readable_text(item, fallback=str(item or ""), max_len=220)
    ][:6]

    impact_analysis = final_judgment.get("impact_analysis")
    if not isinstance(impact_analysis, dict):
        impact_analysis = {
            "affected_services": [],
            "business_impact": "待评估",
            "affected_users": "待评估",
        }

    risk_assessment = final_judgment.get("risk_assessment")
    if not isinstance(risk_assessment, dict):
        risk_assessment = {
            "risk_level": "medium",
            "risk_factors": [],
            "mitigation_suggestions": [],
        }

    decision_rationale = parsed.get("decision_rationale")
    if not isinstance(decision_rationale, dict):
        decision_rationale = {
            "key_factors": [],
            "reasoning": raw_content[:400],
        }

    action_items = parsed.get("action_items")
    if not isinstance(action_items, list):
        action_items = []

    responsible_team = parsed.get("responsible_team")
    if not isinstance(responsible_team, dict):
        responsible_team = {
            "team": "待确认",
            "owner": "待确认",
        }

    confidence = parsed.get("confidence")
    try:
        confidence_value = float(confidence)
    except Exception:
        confidence_value = float(root_cause.get("confidence") or 0.6)
    confidence_value = max(0.0, min(1.0, confidence_value))
    if not chat_message:
        root_summary = str(root_cause.get("summary") or "").strip()
        if root_summary:
            chat_message = f"综合各位观点，我倾向结论是：{root_summary}"
        elif raw_content:
            chat_message = raw_content[:220]

    return {
        "chat_message": chat_message[:300],
        "final_judgment": {
            "root_cause": root_cause,
            "evidence_chain": evidence_items,
            "fix_recommendation": fix_recommendation,
            "impact_analysis": impact_analysis,
            "risk_assessment": risk_assessment,
        },
        "decision_rationale": decision_rationale,
        "action_items": action_items,
        "responsible_team": responsible_team,
        "confidence": confidence_value,
        "raw_text": raw_content[:1400],
    }


def normalize_agent_output(agent_name: str, raw_content: str, *, judge_fallback_summary: str) -> Dict[str, Any]:
    """对输入执行归一化Agentoutput，将原始数据整理为稳定的内部结构。"""
    if agent_name == "JudgeAgent":
        parsed = parse_judge_payload(raw_content)
        return normalize_judge_output(parsed, raw_content, fallback_summary=judge_fallback_summary)
    if agent_name == "VerificationAgent":
        parsed = extract_mixed_json_dict(raw_content)
        return normalize_verification_output(parsed, raw_content)
    if agent_name == "ProblemAnalysisAgent":
        parsed = extract_mixed_json_dict(raw_content)
        return normalize_commander_output(parsed, raw_content)
    parsed = extract_mixed_json_dict(raw_content)
    return normalize_normal_output(parsed, raw_content)


def _normalize_evidence_items(raw_evidence: Any, *, source_hint: str, max_items: int = 5) -> List[Dict[str, Any]]:
    """对输入执行归一化evidenceitems，将原始数据整理为稳定的内部结构。"""
    if not isinstance(raw_evidence, list):
        raw_evidence = []
    items: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_evidence[:max_items], start=1):
        if isinstance(item, dict):
            description = str(item.get("description") or item.get("evidence") or item.get("summary") or "").strip()
            if not description:
                continue
            source = str(item.get("source") or source_hint or "analysis")
            source_ref = str(item.get("source_ref") or item.get("location") or "")
            items.append(
                {
                    "evidence_id": str(item.get("evidence_id") or _evidence_id(description, source_ref, source, index)),
                    "type": str(item.get("type") or source_hint or "analysis"),
                    "description": description[:300],
                    "source": source,
                    "source_ref": source_ref[:300],
                    "location": item.get("location"),
                    "strength": str(item.get("strength") or "medium"),
                }
            )
            continue
        text = str(item or "").strip()
        if not text:
            continue
        items.append(
            {
                "evidence_id": _evidence_id(text, "", source_hint or "analysis", index),
                "type": source_hint or "analysis",
                "description": text[:300],
                "source": source_hint or "analysis",
                "source_ref": "",
                "location": None,
                "strength": "medium",
            }
        )
    return items


def _evidence_id(description: str, source_ref: str, source: str, index: int) -> str:
    """执行evidenceid相关逻辑，并为当前模块提供可复用的处理能力。"""
    raw = "|".join([str(description or "").strip(), str(source_ref or "").strip(), str(source or "").strip(), str(index)])
    digest = sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"evd_{digest}"
