import pytest

from app.runtime.langgraph.agent_runner import AgentRunner
from app.runtime.langgraph.execution import FatalLLMError
from app.runtime.langgraph.state import AgentSpec


class _DummyOrchestrator:
    async def _create_fallback_turn(self, **kwargs):  # pragma: no cover
        return {"fallback": True, "kwargs": kwargs}


@pytest.mark.asyncio
async def test_agent_runner_reraises_fatal_error(monkeypatch):
    orchestrator = _DummyOrchestrator()
    runner = AgentRunner(orchestrator)

    async def _raise_fatal(*args, **kwargs):
        raise FatalLLMError("fatal")

    monkeypatch.setattr("app.runtime.langgraph.agent_runner.call_agent", _raise_fatal)

    with pytest.raises(FatalLLMError):
        await runner.run_agent(
            spec=AgentSpec(name="JudgeAgent", role="judge", phase="judgment", system_prompt=""),
            prompt="x",
            round_number=1,
            loop_round=1,
            history_cards_context=[],
        )
