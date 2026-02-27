"""
Unit tests for GraphBuilder.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.runtime.langgraph.builder import GraphBuilder
from app.runtime.langgraph.state import AgentSpec


class TestGraphBuilder:
    """Tests for GraphBuilder."""

    def _create_mock_orchestrator(self):
        """Create a mock orchestrator for testing."""
        orchestrator = MagicMock()
        orchestrator.session_id = "test_session"
        orchestrator._route_after_supervisor_decide = lambda state: "round_evaluate"
        orchestrator._route_after_round_evaluate = lambda state: "finalize"
        return orchestrator

    def test_builder_initialization(self):
        """Should initialize GraphBuilder with orchestrator."""
        orchestrator = self._create_mock_orchestrator()
        builder = GraphBuilder(orchestrator)

        assert builder._orchestrator is orchestrator

    def test_agent_to_node_name(self):
        """Should convert agent name to node name correctly."""
        orchestrator = self._create_mock_orchestrator()
        builder = GraphBuilder(orchestrator)

        assert builder._agent_to_node_name("LogAgent") == "log_agent_node"
        assert builder._agent_to_node_name("CodeAgent") == "code_agent_node"
        assert builder._agent_to_node_name("JudgeAgent") == "judge_agent_node"

    def test_get_route_table(self):
        """Should generate correct route table."""
        orchestrator = self._create_mock_orchestrator()
        builder = GraphBuilder(orchestrator)

        agent_specs = [
            AgentSpec(name="LogAgent", role="Log", phase="analysis", system_prompt=""),
            AgentSpec(name="CodeAgent", role="Code", phase="analysis", system_prompt=""),
            AgentSpec(name="JudgeAgent", role="Judge", phase="judgment", system_prompt=""),
        ]

        route_table = builder.get_route_table(agent_specs)

        # Should contain core nodes
        assert "round_evaluate" in route_table
        assert "finalize" in route_table
        assert "analysis_parallel_node" in route_table

        # Should contain agent nodes
        assert "log_agent_node" in route_table
        assert "code_agent_node" in route_table
        assert "judge_agent_node" in route_table

    def test_get_route_table_with_collaboration(self):
        """Should include collaboration node when enabled."""
        orchestrator = self._create_mock_orchestrator()
        builder = GraphBuilder(orchestrator)

        agent_specs = [
            AgentSpec(name="LogAgent", role="Log", phase="analysis", system_prompt=""),
        ]

        with patch("app.runtime.langgraph.builder.settings.DEBATE_ENABLE_COLLABORATION", True):
            route_table = builder.get_route_table(agent_specs)
            assert "analysis_collaboration_node" in route_table

    def test_build_creates_graph(self):
        """Should build a valid StateGraph."""
        orchestrator = self._create_mock_orchestrator()
        builder = GraphBuilder(orchestrator)

        agent_specs = [
            AgentSpec(name="LogAgent", role="Log", phase="analysis", system_prompt=""),
            AgentSpec(name="CodeAgent", role="Code", phase="analysis", system_prompt=""),
            AgentSpec(name="JudgeAgent", role="Judge", phase="judgment", system_prompt=""),
        ]

        with patch("app.config.settings.DEBATE_ENABLE_COLLABORATION", False), \
             patch("app.config.settings.DEBATE_ENABLE_CRITIQUE", False):
            graph = builder.build(agent_specs)

            # Graph should be a StateGraph instance
            assert graph is not None
            # Should have nodes attribute (internal StateGraph structure)
            assert hasattr(graph, 'nodes') or hasattr(graph, '_nodes')


class TestGraphBuilderNodeConstants:
    """Tests for GraphBuilder node name constants."""

    def test_node_constants_exist(self):
        """Should have node name constants defined."""
        assert GraphBuilder.NODE_INIT_SESSION == "init_session"
        assert GraphBuilder.NODE_ROUND_START == "round_start"
        assert GraphBuilder.NODE_SUPERVISOR_DECIDE == "supervisor_decide"
        assert GraphBuilder.NODE_ROUND_EVALUATE == "round_evaluate"
        assert GraphBuilder.NODE_FINALIZE == "finalize"
        assert GraphBuilder.NODE_ANALYSIS_PARALLEL == "analysis_parallel_node"
        assert GraphBuilder.NODE_ANALYSIS_COLLABORATION == "analysis_collaboration_node"
        assert GraphBuilder.NODE_AGENT_SUFFIX == "_agent_node"
