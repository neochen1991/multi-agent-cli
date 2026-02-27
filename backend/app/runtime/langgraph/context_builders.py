"""Prompt/context helper builders for LangGraph runtime.

These helpers keep orchestration code smaller by extracting prompt context
construction into pure functions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from app.runtime.messages import AgentEvidence


def _cap(limit: int, floor: int = 1) -> int:
    return max(floor, int(limit or 0))


def collect_peer_items_from_dialogue(
    dialogue_items: Sequence[Dict[str, Any]],
    *,
    exclude_agent: str,
    limit: int,
) -> List[Dict[str, Any]]:
    peers: List[Dict[str, Any]] = []
    seen_agents: set[str] = set()
    for item in reversed(list(dialogue_items or [])):
        agent_name = str(item.get("speaker") or "").strip()
        if not agent_name or agent_name == exclude_agent or agent_name in seen_agents:
            continue
        message = str(item.get("message") or "").strip()
        conclusion = str(item.get("conclusion") or "").strip()
        if not message and not conclusion:
            continue
        peers.append(
            {
                "agent": agent_name,
                "phase": str(item.get("phase") or ""),
                "summary": message[:72],
                "conclusion": (conclusion or message)[:100],
                "confidence": 0.0,
            }
        )
        seen_agents.add(agent_name)
        if len(peers) >= _cap(limit):
            break
    peers.reverse()
    return peers


def collect_peer_items_from_cards(
    history_cards: Sequence[AgentEvidence],
    *,
    exclude_agent: str,
    limit: int,
) -> List[Dict[str, Any]]:
    peers: List[Dict[str, Any]] = []
    for card in reversed(list(history_cards or [])):
        if card.agent_name == exclude_agent:
            continue
        peers.append(
            {
                "agent": card.agent_name,
                "phase": card.phase,
                "summary": card.summary[:72],
                "conclusion": card.conclusion[:100],
                "confidence": round(float(card.confidence or 0.0), 3),
            }
        )
        if len(peers) >= _cap(limit):
            break
    peers.reverse()
    return peers


def _merge_peer_items(
    primary: Sequence[Dict[str, Any]],
    fallback: Sequence[Dict[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    merged = list(primary or [])
    known: set[Tuple[str, str]] = {
        (str(item.get("agent") or ""), str(item.get("conclusion") or ""))
        for item in merged
    }
    for item in list(fallback or []):
        sig = (str(item.get("agent") or ""), str(item.get("conclusion") or ""))
        if sig in known:
            continue
        merged.append(item)
        known.add(sig)
        if len(merged) >= _cap(limit):
            break
    return merged[-_cap(limit) :]


def coordination_peer_items(
    *,
    history_cards: Sequence[AgentEvidence],
    dialogue_items: Sequence[Dict[str, Any]],
    existing_agent_outputs: Dict[str, Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    peers = collect_peer_items_from_dialogue(
        dialogue_items,
        exclude_agent="ProblemAnalysisAgent",
        limit=limit,
    )
    peers = _merge_peer_items(
        peers,
        collect_peer_items_from_cards(
            history_cards,
            exclude_agent="ProblemAnalysisAgent",
            limit=limit,
        ),
        limit=limit,
    )
    if len(peers) < _cap(limit):
        seen_agents = {str(item.get("agent") or "").strip() for item in peers}
        for agent_name, output in dict(existing_agent_outputs or {}).items():
            name = str(agent_name or "").strip()
            if not name or name == "ProblemAnalysisAgent" or name in seen_agents:
                continue
            conclusion = str((output or {}).get("conclusion") or "").strip()
            analysis = str((output or {}).get("analysis") or "").strip()
            text = conclusion or analysis
            if not text:
                continue
            peers.append(
                {
                    "agent": name,
                    "phase": "",
                    "summary": text[:72],
                    "conclusion": text[:100],
                    "confidence": float((output or {}).get("confidence") or 0.0),
                }
            )
            seen_agents.add(name)
            if len(peers) >= _cap(limit):
                break
    return peers[-_cap(limit) :]


def supervisor_recent_messages(
    *,
    round_history_cards: Sequence[AgentEvidence],
    dialogue_items: Sequence[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for item in list(dialogue_items or [])[-_cap(limit) :]:
        agent = str(item.get("speaker") or "").strip()
        if not agent:
            continue
        items.append(
            {
                "agent": agent,
                "phase": str(item.get("phase") or ""),
                "conclusion": (
                    str(item.get("conclusion") or "").strip()
                    or str(item.get("message") or "").strip()
                )[:160],
                "confidence": 0.0,
            }
        )
    if items:
        return items[-_cap(limit) :]
    return [
        {
            "agent": card.agent_name,
            "phase": card.phase,
            "conclusion": card.conclusion[:160],
            "confidence": round(float(card.confidence or 0.0), 3),
        }
        for card in list(round_history_cards or [])[-8:]
    ]


def history_items_for_agent_prompt(
    *,
    agent_name: str,
    history_cards: Sequence[AgentEvidence],
    dialogue_items: Sequence[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for entry in collect_peer_items_from_dialogue(
        dialogue_items,
        exclude_agent=agent_name,
        limit=_cap(limit) + 2,
    ):
        sig = (str(entry.get("agent") or ""), str(entry.get("conclusion") or ""))
        if sig in seen:
            continue
        seen.add(sig)
        items.append(
            {
                "agent": str(entry.get("agent") or ""),
                "phase": str(entry.get("phase") or ""),
                "summary": str(entry.get("summary") or "")[:120],
                "conclusion": str(entry.get("conclusion") or "")[:140],
                "evidence": [],
                "confidence": float(entry.get("confidence") or 0.0),
            }
        )
        if len(items) >= _cap(limit):
            break

    if len(items) < _cap(limit):
        for card in reversed(list(history_cards or [])):
            if card.agent_name == agent_name:
                continue
            sig = (str(card.agent_name or ""), str(card.conclusion or ""))
            if sig in seen:
                continue
            seen.add(sig)
            items.append(
                {
                    "agent": card.agent_name,
                    "phase": card.phase,
                    "summary": card.summary[:120],
                    "conclusion": card.conclusion[:140],
                    "evidence": list((card.evidence_chain or [])[:2]),
                    "confidence": round(float(card.confidence or 0.0), 3),
                }
            )
            if len(items) >= _cap(limit):
                break
    return items[: _cap(limit)]


def peer_items_for_collaboration_prompt(
    *,
    spec_name: str,
    peer_cards: Sequence[AgentEvidence],
    dialogue_items: Sequence[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_agents: set[str] = set()
    for entry in collect_peer_items_from_dialogue(
        dialogue_items,
        exclude_agent=spec_name,
        limit=_cap(limit) + 2,
    ):
        agent = str(entry.get("agent") or "").strip()
        if not agent or agent in seen_agents:
            continue
        seen_agents.add(agent)
        items.append(
            {
                "agent": agent,
                "summary": str(entry.get("summary") or "")[:120],
                "conclusion": str(entry.get("conclusion") or "")[:160],
                "confidence": float(entry.get("confidence") or 0.0),
            }
        )
        if len(items) >= _cap(limit):
            break
    if len(items) < _cap(limit):
        for card in list(peer_cards or []):
            if card.agent_name == spec_name or card.agent_name in seen_agents:
                continue
            seen_agents.add(card.agent_name)
            items.append(
                {
                    "agent": card.agent_name,
                    "summary": card.summary[:120],
                    "conclusion": card.conclusion[:160],
                    "confidence": round(float(card.confidence or 0.0), 3),
                }
            )
            if len(items) >= _cap(limit):
                break
    return items[: _cap(limit)]


__all__ = [
    "collect_peer_items_from_dialogue",
    "collect_peer_items_from_cards",
    "coordination_peer_items",
    "supervisor_recent_messages",
    "history_items_for_agent_prompt",
    "peer_items_for_collaboration_prompt",
]
