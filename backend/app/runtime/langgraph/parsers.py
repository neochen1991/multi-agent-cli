"""Output parsing and normalization helpers for LangGraph runtime agents."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.core.json_utils import extract_json_dict


def extract_balanced_object(text: str, start_index: int) -> Optional[str]:
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
    matches = re.findall(r'"confidence"\s*:\s*(-?\d+(?:\.\d+)?)', text)
    if not matches:
        return fallback
    try:
        value = float(matches[-1])
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, value))


def extract_largest_json_dict(text: str) -> Dict[str, Any]:
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
    chat_message = str(parsed.get("chat_message") or "").strip()
    analysis = str(parsed.get("analysis") or "").strip()
    conclusion = str(parsed.get("conclusion") or analysis or "").strip()
    evidence = parsed.get("evidence_chain")
    if not isinstance(evidence, list):
        evidence = []
    evidence = [str(item).strip() for item in evidence if str(item).strip()][:3]

    confidence = parsed.get("confidence")
    try:
        confidence_value = float(confidence)
    except Exception:
        confidence_value = 0.66 if analysis or conclusion else 0.45
    confidence_value = max(0.0, min(1.0, confidence_value))

    if not analysis and raw_content:
        analysis = raw_content[:220]
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


def normalize_commander_output(parsed: Dict[str, Any], raw_content: str) -> Dict[str, Any]:
    normalized = normalize_normal_output(parsed, raw_content)
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
                }
            )
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
    return normalized


def normalize_judge_output(
    parsed: Dict[str, Any],
    raw_content: str,
    *,
    fallback_summary: str,
) -> Dict[str, Any]:
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
            "summary": root_cause,
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
        summary = str(root_cause.get("summary") or "").strip()
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
    for item in evidence_chain[:6]:
        if isinstance(item, dict):
            evidence_items.append(
                {
                    "type": str(item.get("type") or "analysis"),
                    "description": str(
                        item.get("description") or item.get("evidence") or item.get("summary") or ""
                    ),
                    "source": str(item.get("source") or "langgraph"),
                    "location": item.get("location"),
                    "strength": str(item.get("strength") or "medium"),
                }
            )
        else:
            evidence_items.append(
                {
                    "type": "analysis",
                    "description": str(item),
                    "source": "langgraph",
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
    if agent_name == "JudgeAgent":
        parsed = parse_judge_payload(raw_content)
        return normalize_judge_output(parsed, raw_content, fallback_summary=judge_fallback_summary)
    if agent_name == "ProblemAnalysisAgent":
        parsed = extract_mixed_json_dict(raw_content)
        return normalize_commander_output(parsed, raw_content)
    parsed = extract_mixed_json_dict(raw_content)
    return normalize_normal_output(parsed, raw_content)
