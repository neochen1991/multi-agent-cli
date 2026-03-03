"""Lineage replay helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from app.runtime.trace_lineage.recorder import lineage_recorder


def _render_step(row: Dict[str, Any]) -> str:
    kind = str(row.get("kind") or "")
    ts = str(row.get("timestamp") or "")
    phase = str(row.get("phase") or "")
    agent = str(row.get("agent_name") or "")
    event_type = str(row.get("event_type") or "")
    if kind == "event":
        return f"[{ts}] event/{event_type} phase={phase} agent={agent}".strip()
    if kind == "tool":
        return f"[{ts}] tool/{event_type} agent={agent}".strip()
    if kind == "agent":
        output = row.get("output_summary") or {}
        conclusion = str(output.get("conclusion") or "")[:140]
        return f"[{ts}] agent/{agent} => {conclusion}".strip()
    return f"[{ts}] {kind} phase={phase} agent={agent}".strip()


async def replay_session_lineage(session_id: str, *, limit: int = 120) -> Dict[str, Any]:
    """Replay a session using recorded lineage records."""

    rows = await lineage_recorder.read(session_id)
    subset = rows[: max(1, int(limit or 120))]
    timeline: List[Dict[str, Any]] = [row.model_dump(mode="json") for row in subset]
    rendered = [_render_step(item) for item in timeline]
    key_decisions: List[Dict[str, Any]] = []
    evidence_refs: List[str] = []
    for item in timeline:
        if str(item.get("kind") or "") == "agent":
            output = item.get("output_summary") if isinstance(item.get("output_summary"), dict) else {}
            conclusion = str(output.get("conclusion") or output.get("summary") or "").strip()
            if conclusion:
                key_decisions.append(
                    {
                        "agent": str(item.get("agent_name") or ""),
                        "phase": str(item.get("phase") or ""),
                        "conclusion": conclusion[:280],
                        "confidence": float(item.get("confidence") or 0.0),
                    }
                )
            chain = output.get("evidence_chain")
            if isinstance(chain, list):
                for ev in chain:
                    if isinstance(ev, dict):
                        ref = str(ev.get("evidence_id") or ev.get("source_ref") or "").strip()
                        if ref:
                            evidence_refs.append(ref)
                    else:
                        text = str(ev or "").strip()
                        if text:
                            evidence_refs.append(text[:120])
    return {
        "session_id": session_id,
        "count": len(timeline),
        "timeline": timeline,
        "rendered_steps": rendered,
        "key_decisions": key_decisions[:30],
        "evidence_refs": sorted(list({ref for ref in evidence_refs if ref}))[:80],
        "summary": await lineage_recorder.summarize(session_id),
    }
