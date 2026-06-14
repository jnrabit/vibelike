import pytest
from pathlib import Path
import sys
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_loop import ToolRegistry, State, AgentLoop


class TestToolRegistrySingleton:
    """Test dass ToolRegistry ein Singleton ist."""

    def test_singleton_instance(self):
        """ToolRegistry.get_instance() liefert immer die gleiche Instanz."""
        ToolRegistry._reset_for_testing()  # Reset für saubere Tests

        registry1 = ToolRegistry.get_instance()
        registry2 = ToolRegistry.get_instance()

        assert registry1 is registry2, "ToolRegistry should be a singleton"

    def test_singleton_shared_across_agents(self):
        """Mehrere AgentLoops teilen sich die gleiche ToolRegistry."""
        ToolRegistry._reset_for_testing()

        agent1 = AgentLoop(model_name="qwen3:8b")
        agent2 = AgentLoop(model_name="claude-haiku")

        assert agent1.tools is agent2.tools, "Agents should share ToolRegistry"
        assert agent1.tools is ToolRegistry.get_instance()

    def test_singleton_thread_safe(self):
        """Singleton ist thread-safe (basic check)."""
        ToolRegistry._reset_for_testing()

        instances = []

        def get_instance():
            instances.append(ToolRegistry.get_instance())

        import threading
        threads = [threading.Thread(target=get_instance) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Alle sollten die gleiche Instanz sein
        assert all(inst is instances[0] for inst in instances), "Thread-safety failed"


class TestToolRegistryTools:
    """Test die verfügbaren Tools."""

    def test_tools_registered(self):
        """Alle Built-in Tools sind registriert."""
        ToolRegistry._reset_for_testing()
        registry = ToolRegistry.get_instance()

        expected_tools = {
            "search_vault",
            "read_file",
            "run_sandboxed",
            "query_ossifikat",
            "verify",
        }
        available = set(registry.available())
        assert expected_tools.issubset(available)

    def test_tool_availability_in_state(self):
        """State nutzt shared ToolRegistry für tools_available."""
        ToolRegistry._reset_for_testing()

        state1 = State()
        state2 = State()

        # Beide sollten die gleichen Tools sehen
        assert state1.tools_available == state2.tools_available
        assert "query_ossifikat" in state1.tools_available


class TestParamValidation:
    """Test Param-Validierung in execute()."""

    @pytest.mark.asyncio
    async def test_execute_with_invalid_param(self):
        """execute() sollte invalid params erkennen und Error zurückgeben."""
        ToolRegistry._reset_for_testing()
        registry = ToolRegistry.get_instance()

        # query_ossifikat erwartet 'query' und 'confirmed_only', nicht 'wrong_param'
        result = await registry.execute("query_ossifikat", {"wrong_param": "value"})

        assert "[ERR]" in result
        assert "wrong_param" in result

    @pytest.mark.asyncio
    async def test_execute_with_valid_params(self):
        """execute() sollte valid params akzeptieren."""
        ToolRegistry._reset_for_testing()
        registry = ToolRegistry.get_instance()

        # query_ossifikat mit gültigen Params (wird mock-Error wegen fehlender Tools sein, aber keine Param-Validierung)
        result = await registry.execute(
            "query_ossifikat",
            {"query": "test", "confirmed_only": True}
        )

        # Sollte kein Param-Validierungs-Error sein
        assert "wrong_param" not in result

    @pytest.mark.asyncio
    async def test_tool_not_found(self):
        """execute() sollte Tool-nicht-gefunden-Error zurückgeben."""
        ToolRegistry._reset_for_testing()
        registry = ToolRegistry.get_instance()

        result = await registry.execute("nonexistent_tool", {})

        assert "[ERR]" in result
        assert "nonexistent_tool" in result


class TestAgentLoopSharedRegistry:
    """Test dass AgentLoop die shared ToolRegistry nutzt."""

    def test_agent_loop_uses_shared_registry(self):
        """AgentLoop.__init__() sollte shared ToolRegistry nutzen, nicht neue."""
        ToolRegistry._reset_for_testing()

        shared_registry = ToolRegistry.get_instance()
        agent = AgentLoop(model_name="qwen3:8b")

        assert agent.tools is shared_registry

    def test_multiple_agents_parallel(self):
        """Mehrere AgentLoops in parallel sollten gleiche ToolRegistry nutzen."""
        ToolRegistry._reset_for_testing()

        agents = [
            AgentLoop(model_name="qwen3:8b"),
            AgentLoop(model_name="claude-haiku"),
            AgentLoop(model_name="qwen3:8b"),
        ]

        # Alle sollten die gleiche ToolRegistry-Instanz nutzen
        first_tools = agents[0].tools
        for agent in agents[1:]:
            assert agent.tools is first_tools


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
