#!/usr/bin/env python3
"""
P3-Integrations-Test: Echte parallel Agent-Ausführung.

Testet, dass asyncio.gather mit mehreren AgentPool-Agents funktioniert
und die Singleton-ToolRegistry richtig geteilt wird.
"""
import asyncio
import sys
from pathlib import Path


from vibelike.agent_pool import AgentPool
from vibelike.agent_loop import ToolRegistry


async def test_p3_basic():
    """Test P3 mit zwei Agents in parallel."""
    print("\n" + "=" * 60)
    print("P3-Test: Parallel Agent-Ausführung")
    print("=" * 60)

    # Reset Singleton für sauberen Test
    ToolRegistry._reset_for_testing()

    # Wie in terminal.py:1702-1704
    actual_models = ["qwen2.5-coder:1.5b", "claude-haiku-4-5-20251001"]

    print(f"\n[POOL] Erstelle AgentPool mit Modellen: {actual_models}")
    pool = AgentPool(actual_models)

    # Überprüfe, dass ToolRegistry geteilt wird
    print(f"\n[CHECK] Singleton-ToolRegistry wird geteilt:")
    for model in actual_models:
        agent = pool.agents[model]
        is_shared = agent.tools is ToolRegistry.get_instance()
        print(f"  {model}: {'✓' if is_shared else '✗'} shared={is_shared}")

    # Test-Query
    query = "was ist quantentheorie?"
    print(f"\n[QUERY] '{query}'")

    # Parallele Ausführung (wie in terminal.py:1703-1704)
    print("\n[GATHER] Starte asyncio.gather mit parallel agents...")
    try:
        responses = await asyncio.gather(
            *[pool.agents[m].step(query) for m in actual_models],
            return_exceptions=True
        )

        print(f"\n[RESULTS] Received {len(responses)} responses:\n")

        for i, model in enumerate(actual_models):
            resp = responses[i]
            if isinstance(resp, Exception):
                print(f"  [{model}] ✗ ERROR: {type(resp).__name__}: {resp}")
            else:
                # Überprüfe auf Param-Fehler
                resp_str = str(resp)
                if "unexpected keyword" in resp_str:
                    print(f"  [{model}] ✗ PARAM-ERROR: {resp_str[:100]}")
                else:
                    print(f"  [{model}] ✓ OK: {resp[:80]}...")

        return all(not isinstance(r, Exception) for r in responses)

    except Exception as e:
        print(f"\n[ERROR] asyncio.gather fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_p3_tool_execution():
    """Test dass Tools parallel korrekt ausgeführt werden."""
    print("\n" + "=" * 60)
    print("P3-Test: Parallel Tool-Ausführung")
    print("=" * 60)

    ToolRegistry._reset_for_testing()

    actual_models = ["qwen2.5-coder:1.5b", "claude-haiku-4-5-20251001"]
    pool = AgentPool(actual_models)

    print(f"\n[SETUP] AgentPool mit {len(actual_models)} Agents")

    # Beide Agents versuchen gleichzeitig Tools aufzurufen
    async def call_tool(model):
        agent = pool.agents[model]
        # Versuche ein Tool direkt aufzurufen (Simulation)
        result = await agent.tools.execute(
            "query_ossifikat",
            {"query": "test", "confirmed_only": True}
        )
        return model, result

    print("\n[GATHER] Parallel Tool-Aufrufe:")
    try:
        results = await asyncio.gather(
            *[call_tool(m) for m in actual_models],
            return_exceptions=True
        )

        success = True
        for result in results:
            if isinstance(result, Exception):
                print(f"  ✗ Exception: {result}")
                success = False
            else:
                model, resp = result
                # Kein Param-Mismatch-Fehler?
                if "unexpected keyword" in str(resp):
                    print(f"  [{model}] ✗ Param-Fehler: {resp}")
                    success = False
                else:
                    print(f"  [{model}] ✓ OK (Tool-Fehler OK, nur nicht Param-Fehler)")

        return success

    except Exception as e:
        print(f"  ✗ gather() fehlgeschlagen: {e}")
        return False


async def main():
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║      P3-Integrations-Tests: Singleton ToolRegistry       ║")
    print("╚════════════════════════════════════════════════════════════╝")

    test1_ok = await test_p3_basic()
    test2_ok = await test_p3_tool_execution()

    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    print(f"P3 Basic Test:         {'✓ PASS' if test1_ok else '✗ FAIL'}")
    print(f"P3 Tool Execution:     {'✓ PASS' if test2_ok else '✗ FAIL'}")
    print(f"\nInsgesamt:             {'✓ SUCCESS' if test1_ok and test2_ok else '✗ FAILED'}")
    print("=" * 60 + "\n")

    return 0 if (test1_ok and test2_ok) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
