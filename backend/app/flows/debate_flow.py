"""
AutoGen Multi-Agent Debate Orchestration
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog

from app.config import settings
from app.core.autogen_client import autogen_client
from app.core.json_utils import extract_json_dict

logger = structlog.get_logger()


@dataclass
class DebateTurn:
    round_number: int
    phase: str
    agent_name: str
    agent_role: str
    model: Dict[str, str]
    input_message: str
    output_content: Dict[str, Any]
    confidence: float
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# Backward-compatible alias used by existing imports.
DebateRound = DebateTurn


class AIDebateOrchestrator:
    """
    AutoGen-oriented multi-agent, multi-round debate orchestrator.
    """

    MODELS = {
        "LogAgent": settings.default_model_config,
        "DomainAgent": settings.default_model_config,
        "CodeAgent": settings.default_model_config,
        "CriticAgent": settings.default_model_config,
        "RebuttalAgent": settings.default_model_config,
        "JudgeAgent": settings.default_model_config,
    }

    AGENT_SEQUENCE = [
        ("LogAgent", "日志分析专家", "analysis"),
        ("DomainAgent", "领域映射专家", "analysis"),
        ("CodeAgent", "代码分析专家", "analysis"),
        ("CriticAgent", "架构质疑专家", "critique"),
        ("RebuttalAgent", "技术反驳专家", "rebuttal"),
        ("JudgeAgent", "技术委员会主席", "judgment"),
    ]
    MAX_HISTORY_ITEMS = 3
    MAX_LOG_CHARS = 1600
    MAX_SUMMARY_CHARS = 96
    MAX_EVIDENCE_ITEMS = 2
    MAX_EVIDENCE_CHARS = 72

    def __init__(self, consensus_threshold: float = 0.85, max_rounds: int = 3):
        self.consensus_threshold = consensus_threshold
        self.max_rounds = max_rounds
        self.session_id: Optional[str] = None
        self.turns: List[DebateTurn] = []
        self._event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

        logger.info(
            "autogen_debate_orchestrator_initialized",
            consensus_threshold=consensus_threshold,
            max_rounds=max_rounds,
            model=settings.llm_model,
        )

    async def execute(
        self,
        context: Dict[str, Any],
        event_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        self.turns = []
        self._event_callback = event_callback
        self.session_id = await self._create_session()

        await self._emit_event(
            {
                "type": "session_created",
                "session_id": self.session_id,
                "mode": "autogen",
            }
        )

        dialogue_history: List[Dict[str, Any]] = []
        consensus_reached = False
        executed_rounds = 0

        for loop_round in range(1, self.max_rounds + 1):
            executed_rounds = loop_round
            await self._emit_event(
                {
                    "type": "round_started",
                    "loop_round": loop_round,
                    "max_rounds": self.max_rounds,
                    "mode": "autogen",
                }
            )

            for agent_name, agent_role, phase in self.AGENT_SEQUENCE:
                prompt = self._build_agent_prompt(
                    context=context,
                    dialogue_history=dialogue_history,
                    agent_name=agent_name,
                    agent_role=agent_role,
                    phase=phase,
                    loop_round=loop_round,
                )
                turn = await self._call_agent(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    phase=phase,
                    prompt=prompt,
                    round_number=len(self.turns) + 1,
                )
                self.turns.append(turn)
                dialogue_history.append(
                    {
                        "round_number": turn.round_number,
                        "phase": phase,
                        "agent_name": agent_name,
                        "agent_role": agent_role,
                        "output_content": turn.output_content,
                        "confidence": turn.confidence,
                    }
                )

            judge_turn = self.turns[-1] if self.turns else None
            judge_conf = (judge_turn.confidence if judge_turn else 0.0) or 0.0
            consensus_reached = judge_conf >= self.consensus_threshold

            await self._emit_event(
                {
                    "type": "round_completed",
                    "loop_round": loop_round,
                    "consensus_reached": consensus_reached,
                    "judge_confidence": judge_conf,
                    "mode": "autogen",
                }
            )
            if consensus_reached:
                break

        final_payload = self._build_final_payload(
            dialogue_history=dialogue_history,
            consensus_reached=consensus_reached,
            executed_rounds=executed_rounds,
        )

        await self._emit_event(
            {
                "type": "debate_completed",
                "confidence": final_payload.get("confidence", 0.0),
                "consensus_reached": consensus_reached,
                "executed_rounds": executed_rounds,
                "mode": "autogen",
            }
        )
        return final_payload

    async def _create_session(self) -> str:
        session = await autogen_client.create_session(title="AutoGen Multi-Agent Debate")
        return session.id

    def _build_agent_prompt(
        self,
        context: Dict[str, Any],
        dialogue_history: List[Dict[str, Any]],
        agent_name: str,
        agent_role: str,
        phase: str,
        loop_round: int,
    ) -> str:
        log_content = context.get("log_content", "")
        parsed_data = context.get("parsed_data", {})
        interface_mapping = context.get("interface_mapping", {})
        dev_assets = context.get("dev_assets", [])
        design_assets = context.get("design_assets", [])

        selected_history = self._select_history_items(dialogue_history, phase, agent_name)
        compact_history = [
            self._compact_history_item(item)
            for item in selected_history[-self.MAX_HISTORY_ITEMS:]
        ]
        history_json = json.dumps(compact_history, ensure_ascii=False, indent=2)
        context_block = {
            "log_content_excerpt": self._truncate(str(log_content), self.MAX_LOG_CHARS),
            "parsed_data": self._compact_parsed_data(parsed_data),
            "interface_mapping": self._compact_interface_mapping(interface_mapping),
            "dev_assets_size": len(dev_assets),
            "design_assets_size": len(design_assets),
        }

        non_judge_instructions = """
请输出 JSON，结构至少包含：
{
  "analysis": "本角色核心结论（<=180字）",
  "evidence_chain": ["证据1", "证据2"],
  "confidence": 0.0
}
要求：
1. 只保留核心观点和结论，不要输出长篇过程。
2. evidence_chain 最多 3 条。
"""

        judge_instructions = """
你是 JudgeAgent，必须输出 JSON：
{
  "final_judgment": {
    "root_cause": {"summary": "", "category": "", "confidence": 0.0},
    "evidence_chain": ["证据1", "证据2"],
    "fix_recommendation": {"summary": "", "steps": []},
    "impact_analysis": {"affected_services": [], "business_impact": ""},
    "risk_assessment": {"risk_level": "medium", "risk_factors": []}
  },
  "decision_rationale": {"key_factors": [], "reasoning": ""},
  "action_items": [],
  "responsible_team": {"team": "", "owner": ""},
  "confidence": 0.0
}
要求：结论简明，不要复述长篇历史。
"""
        shared_instructions = judge_instructions if agent_name == "JudgeAgent" else non_judge_instructions
        return f"""你是 {agent_name}（{agent_role}）。
当前处于第 {loop_round}/{self.max_rounds} 轮，阶段：{phase}。

故障上下文：
```json
{json.dumps(context_block, ensure_ascii=False, indent=2)}
```

最近多 Agent 核心观点卡片（仅结论）：
```json
{history_json}
```

{shared_instructions}
"""

    async def _call_agent(
        self,
        agent_name: str,
        agent_role: str,
        phase: str,
        prompt: str,
        round_number: int,
    ) -> DebateTurn:
        model = self.MODELS.get(agent_name, settings.default_model_config)
        started_at = datetime.utcnow()

        await self._emit_event(
            {
                "type": "llm_call_started",
                "phase": phase,
                "round_number": round_number,
                "agent_name": agent_name,
                "agent_role": agent_role,
                "model": model.get("name", settings.llm_model),
                "prompt_preview": prompt[:1200],
                "session_id": self.session_id,
                "mode": "autogen",
            }
        )

        try:
            result = await asyncio.wait_for(
                autogen_client.send_prompt(
                    session_id=self.session_id or "",
                    parts=[{"type": "text", "text": prompt}],
                    model=model,
                    agent=agent_name,
                    max_tokens=self._resolve_max_tokens(agent_name, phase),
                    use_session_history=False,
                    trace_context={
                        "phase": phase,
                        "stage": "autogen_round",
                        "agent_name": agent_name,
                        "round_number": round_number,
                    },
                ),
                timeout=max(45, min(settings.llm_timeout, 180)),
            )
            content = result.get("content", "") if isinstance(result, dict) else ""
            output_data = result.get("structured", {}) if isinstance(result, dict) else {}
            if not output_data:
                output_data = extract_json_dict(content) or {}
            if not output_data:
                output_data = {"analysis": content[:4000]}
            confidence = float(output_data.get("confidence", 0.5) or 0.5)

            turn = DebateTurn(
                round_number=round_number,
                phase=phase,
                agent_name=agent_name,
                agent_role=agent_role,
                model=model,
                input_message=prompt[:2000],
                output_content=output_data,
                confidence=confidence,
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )

            await self._emit_event(
                {
                    "type": "agent_round",
                    "phase": phase,
                    "round_number": round_number,
                    "agent_name": agent_name,
                    "agent_role": agent_role,
                    "confidence": confidence,
                    "mode": "autogen",
                }
            )
            await self._emit_event(
                {
                    "type": "llm_call_completed",
                    "phase": phase,
                    "round_number": round_number,
                    "agent_name": agent_name,
                    "agent_role": agent_role,
                    "model": model.get("name", settings.llm_model),
                    "output_json": output_data,
                    "output_preview": content[:1200],
                    "confidence": confidence,
                    "session_id": self.session_id,
                    "mode": "autogen",
                }
            )
            return turn
        except Exception as exc:
            error_text = str(exc).strip() or exc.__class__.__name__
            await self._emit_event(
                {
                    "type": "llm_call_failed",
                    "phase": phase,
                    "round_number": round_number,
                    "agent_name": agent_name,
                    "agent_role": agent_role,
                    "model": model.get("name", settings.llm_model),
                    "error": error_text,
                    "prompt_preview": prompt[:1200],
                    "session_id": self.session_id,
                    "mode": "autogen",
                }
            )
            raise RuntimeError(f"{agent_name} LLM 调用失败: {error_text}") from exc

    @classmethod
    def _truncate(cls, value: Any, limit: int) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        return f"{text[:limit]}...<truncated:{len(text) - limit}>"

    @classmethod
    def _compact_list(cls, values: Any, max_items: int = 5, item_limit: int = 120) -> List[str]:
        if not isinstance(values, list):
            return []
        result: List[str] = []
        for item in values[:max_items]:
            result.append(cls._truncate(item, item_limit))
        return result

    def _compact_parsed_data(self, parsed_data: Any) -> Dict[str, Any]:
        if not isinstance(parsed_data, dict):
            return {}
        return {
            "exceptions": self._compact_list(parsed_data.get("exceptions"), max_items=3, item_limit=240),
            "urls": self._compact_list(parsed_data.get("urls"), max_items=6, item_limit=200),
            "class_names": self._compact_list(parsed_data.get("class_names"), max_items=6, item_limit=120),
            "trace_ids": self._compact_list(parsed_data.get("trace_ids"), max_items=6, item_limit=120),
            "sqls": self._compact_list(parsed_data.get("sqls"), max_items=3, item_limit=200),
        }

    def _compact_interface_mapping(self, mapping: Any) -> Dict[str, Any]:
        if not isinstance(mapping, dict):
            return {}
        endpoints = mapping.get("matched_endpoint") or {}
        return {
            "matched": mapping.get("matched", False),
            "confidence": mapping.get("confidence", 0.0),
            "reason": self._truncate(mapping.get("reason", ""), 180),
            "domain": mapping.get("domain"),
            "aggregate": mapping.get("aggregate"),
            "owner_team": mapping.get("owner_team"),
            "owner": mapping.get("owner"),
            "matched_endpoint": {
                "method": endpoints.get("method"),
                "path": endpoints.get("path"),
                "service": endpoints.get("service"),
                "interface": endpoints.get("interface"),
            },
            "code_artifacts_count": len(mapping.get("code_artifacts") or []),
            "db_tables": self._compact_list(mapping.get("db_tables"), max_items=4, item_limit=80),
            "design_ref": mapping.get("design_ref"),
            "similar_cases_count": len(mapping.get("similar_cases") or []),
        }

    def _compact_history_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        output_content = item.get("output_content") if isinstance(item, dict) else {}
        summary = self._extract_core_conclusion(output_content)
        key_evidence = self._extract_key_evidence(output_content)
        return {
            "agent_name": item.get("agent_name"),
            "confidence": item.get("confidence"),
            "core_conclusion": self._truncate(summary, self.MAX_SUMMARY_CHARS),
            "key_evidence": key_evidence,
        }

    def _select_history_items(
        self,
        dialogue_history: List[Dict[str, Any]],
        phase: str,
        agent_name: str,
    ) -> List[Dict[str, Any]]:
        if not dialogue_history:
            return []

        phase = str(phase or "").lower()
        if phase == "analysis":
            if agent_name == "LogAgent":
                return []
            if agent_name == "DomainAgent":
                include_agents = ["LogAgent"]
            elif agent_name == "CodeAgent":
                include_agents = ["LogAgent", "DomainAgent"]
            else:
                include_agents = ["CodeAgent"]
        elif phase == "critique":
            include_agents = ["LogAgent", "DomainAgent", "CodeAgent"]
        elif phase == "rebuttal":
            include_agents = ["CriticAgent", "CodeAgent"]
        elif phase == "judgment":
            include_agents = ["CodeAgent", "CriticAgent", "RebuttalAgent"]
        else:
            include_agents = []

        picked_by_agent: Dict[str, Dict[str, Any]] = {}
        for agent in include_agents:
            for item in reversed(dialogue_history):
                if item.get("agent_name") == agent:
                    picked_by_agent[agent] = item
                    break
        return [picked_by_agent[a] for a in include_agents if a in picked_by_agent]

    def _extract_core_conclusion(self, output_content: Any) -> str:
        if not isinstance(output_content, dict):
            return ""
        candidates = [
            output_content.get("analysis"),
            ((output_content.get("final_judgment") or {}).get("root_cause") or {}).get("summary")
            if isinstance(output_content.get("final_judgment"), dict)
            else "",
            ((output_content.get("root_cause") or {}).get("summary") if isinstance(output_content.get("root_cause"), dict) else ""),
            output_content.get("response_summary"),
            output_content.get("reasoning"),
            output_content.get("description"),
        ]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if not text:
                continue
            first_line = text.replace("\r", "\n").split("\n", 1)[0].strip()
            return first_line
        return ""

    def _extract_key_evidence(self, output_content: Any) -> List[str]:
        if not isinstance(output_content, dict):
            return []
        raw_chain = output_content.get("evidence_chain")
        if not isinstance(raw_chain, list):
            return []
        compact: List[str] = []
        for item in raw_chain[: self.MAX_EVIDENCE_ITEMS]:
            if isinstance(item, dict):
                text = (
                    item.get("evidence")
                    or item.get("description")
                    or item.get("summary")
                    or item.get("title")
                    or ""
                )
            else:
                text = str(item or "")
            text = str(text).strip()
            if text:
                compact.append(self._truncate(text, self.MAX_EVIDENCE_CHARS))
        return compact

    @staticmethod
    def _resolve_max_tokens(agent_name: str, phase: str) -> int:
        if agent_name == "JudgeAgent" or phase == "judgment":
            return 1100
        if agent_name in {"CriticAgent", "RebuttalAgent"}:
            return 900
        return 800

    def _build_final_payload(
        self,
        dialogue_history: List[Dict[str, Any]],
        consensus_reached: bool,
        executed_rounds: int,
    ) -> Dict[str, Any]:
        judge_items = [t for t in self.turns if t.agent_name == "JudgeAgent"]
        judge_output = judge_items[-1].output_content if judge_items else {}
        final_judgment = judge_output.get("final_judgment", {})
        if not final_judgment:
            root_summary = ""
            for item in reversed(dialogue_history):
                output_content = item.get("output_content", {})
                root_summary = (
                    (output_content.get("root_cause") or {}).get("summary")
                    if isinstance(output_content.get("root_cause"), dict)
                    else output_content.get("analysis", "")
                )
                if root_summary:
                    break
            final_judgment = {
                "root_cause": {
                    "summary": root_summary or "模型未返回结构化最终结论，请查看对话过程",
                    "description": "",
                    "category": "unknown",
                    "confidence": judge_output.get("confidence", 0.5),
                },
                "evidence_chain": [],
                "fix_recommendation": {
                    "summary": "请结合辩论过程补充修复动作",
                    "steps": [],
                    "code_changes_required": True,
                    "rollback_recommended": False,
                },
                "impact_analysis": {
                    "affected_services": [],
                    "affected_users": "",
                    "business_impact": "",
                },
                "risk_assessment": {
                    "risk_level": "medium",
                    "risk_factors": [],
                    "mitigation_suggestions": [],
                },
            }

        confidence = float(judge_output.get("confidence", 0.5) or 0.5)
        return {
            "final_judgment": final_judgment,
            "decision_rationale": judge_output.get("decision_rationale", {"key_factors": [], "reasoning": ""}),
            "action_items": judge_output.get("action_items", []),
            "responsible_team": judge_output.get("responsible_team", {"team": "", "owner": ""}),
            "confidence": confidence,
            "dissenting_opinions": judge_output.get("dissenting_opinions", []),
            "round_control": {
                "consensus_reached": consensus_reached,
                "consensus_threshold": self.consensus_threshold,
                "executed_rounds": executed_rounds,
                "max_rounds": self.max_rounds,
            },
            "debate_history": [
                {
                    "round_number": t.round_number,
                    "phase": t.phase,
                    "agent_name": t.agent_name,
                    "agent_role": t.agent_role,
                    "model": t.model,
                    "input_message": t.input_message,
                    "output_content": t.output_content,
                    "confidence": t.confidence,
                    "started_at": t.started_at.isoformat(),
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                }
                for t in self.turns
            ],
        }

    async def _emit_event(self, event: Dict[str, Any]) -> None:
        if not self._event_callback:
            return
        try:
            maybe = self._event_callback(event)
            if asyncio.iscoroutine(maybe):
                await maybe
        except Exception as exc:
            logger.warning("autogen_debate_event_emit_failed", error=str(exc))


ai_debate_orchestrator = AIDebateOrchestrator()
