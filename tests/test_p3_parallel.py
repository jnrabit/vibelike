import pytest
from pathlib import Path
import sys
import asyncio


from vibelike.agent_loop import ToolRegistry, AgentLoop


@pytest.mark.asyncio
async def test_parallel_agents_shared_registry():
    """Test dass mehrere parallel-laufende AgentLoops die gleiche ToolRegistry teilen."""
    ToolRegistry._reset_for_testing()

    # Erstelle zwei AgentLoops (wie P3 es tut)
    agent_qwen = AgentLoop(model_name="qwen3:8b")
    agent_claude = AgentLoop(model_name="claude-haiku")

    # Beide sollten die gleiche ToolRegistry nutzen
    assert agent_qwen.tools is agent_claude.tools

    # Hole die gemeinsame Registry
    shared_registry = ToolRegistry.get_instance()
    assert agent_qwen.tools is shared_registry
    assert agent_claude.tools is shared_registry


@pytest.mark.asyncio
async def test_parallel_tool_execution():
    """Test dass beide Agents in parallel Tools aufrufen können ohne Konflikte."""
    ToolRegistry._reset_for_testing()

    agent_qwen = AgentLoop(model_name="qwen3:8b")
    agent_claude = AgentLoop(model_name="claude-haiku")

    # Simuliere parallele Tool-Aufrufe (wie in P3 bei asyncio.gather)
    # Beide Agents versuchen gleichzeitig, query_ossifikat aufzurufen
    results = await asyncio.gather(
        agent_qwen.tools.execute("query_ossifikat", {"query": "test1"}),
        agent_claude.tools.execute("query_ossifikat", {"query": "test2"}),
        return_exceptions=True
    )

    # Beide sollten erfolgreich sein (oder nur Agent-Tool-Fehler, keine Param-Fehler)
    for result in results:
        assert isinstance(result, str), f"Expected string, got {type(result)}"
        # Keine [ERR] Param-Mismatch-Fehler (könnte Tool-Not-Found sein, das ist OK)
        if "[ERR]" in result:
            # Sollte nicht "unexpected keyword argument 'query'" sein
            assert "unexpected keyword" not in result, f"Param mismatch: {result}"


@pytest.mark.asyncio
async def test_parallel_different_tools():
    """Test dass verschiedene Tools parallel aufgerufen werden können."""
    ToolRegistry._reset_for_testing()

    agent1 = AgentLoop(model_name="qwen3:8b")
    agent2 = AgentLoop(model_name="claude-haiku")

    # Parallele Tool-Aufrufe mit verschiedenen Tools
    results = await asyncio.gather(
        agent1.tools.execute("search_vault", {"query": "test"}),
        agent2.tools.execute("verify", {"statement": "test"}),
        return_exceptions=True
    )

    assert len(results) == 2
    assert all(isinstance(r, str) for r in results)


@pytest.mark.asyncio
async def test_p3_gather_simulation():
    """Simuliere das P3 asyncio.gather mit actual_models."""
    ToolRegistry._reset_for_testing()

    # Wie in terminal.py:1703-1704 (P3)
    agents = {
        "qwen": AgentLoop(model_name="qwen3:8b"),
        "claude": AgentLoop(model_name="claude-haiku"),
    }

    actual_models = ["qwen", "claude"]

    # Simuliere eine Gather-Operation wie in P3
    async def agent_step(model_name, query):
        agent = agents[model_name]
        # Versuche ein Tool auszuführen (vereinfachte Simulation)
        result = await agent.tools.execute(
            "query_ossifikat",
            {"query": query, "confirmed_only": True}
        )
        return model_name, result

    query = "was ist quantentheorie?"

    # Das ist die kritische P3-Operation (asyncio.gather mit parallel Agents)
    results = await asyncio.gather(
        *[agent_step(m, query) for m in actual_models],
        return_exceptions=True
    )

    # Beide sollten erfolgreich sein oder nur normale Tool-Fehler haben
    assert len(results) == 2
    for result in results:
        assert isinstance(result, tuple), f"Expected tuple, got {type(result)}"
        model_name, response = result
        # Sollte KEINE Parameter-Fehler sein
        assert "unexpected keyword" not in str(response)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
