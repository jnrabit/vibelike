#!/usr/bin/env python3
"""
Integration Test: SharedAtom + agent_loop + P3-Decision.

Zeigt wie die Stacks aufgebaut werden und wie P3 die Signals nutzt.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared_atom import reset_shared_atom, get_shared_atom
from agent_loop import AgentLoop, ToolRegistry
from p3_decision import decide_p3_models


async def test_atom_integration():
    """End-to-End Test: Atom accumulation durch Agent-Erfolge."""
    print("\n" + "=" * 70)
    print("SharedAtom Integration Test: Agent Success → Stack Growth")
    print("=" * 70)

    # Reset für sauberen Test
    reset_shared_atom()
    ToolRegistry._reset_for_testing()
    atom = get_shared_atom()

    print("\n[PHASE 1] Initial Atom-State:")
    signals = atom.get_all_signals()
    for name, signal in signals.items():
        if "model" in name:
            print(f"  {name:30} → {signal['height']:.2f}/{signal['size']:.1f}")

    # Simuliere mehrere Agent-Läufe
    print("\n[PHASE 2] Simuliere 3 erfolgreiche qwen-Runs:")
    for i in range(3):
        agent = AgentLoop(model_name="qwen2.5-coder:1.5b")
        # Simuliere erfolgreiche Tool-Ausführung (wird in agent_loop.py gemacht)
        atom.push("model:qwen:success")  # Generischer Name
        atom.push("tool:search_vault:hits")
        print(f"  Run {i+1}: pushed model:qwen + tool:search_vault")

    print("\n[PHASE 3] Atom-State nach Runs:")
    signals = atom.get_all_signals()
    for name, signal in signals.items():
        if signal["height"] > 0:
            print(f"  {name:30} → {signal['height']:.2f}/{signal['size']:.1f} ({signal['normalized']:.0%})")

    # Jetzt P3-Entscheidung treffen
    print("\n[PHASE 4] P3 Model Selection (mit Atom-Signalen):")

    test_queries = [
        ("Schreib eine Python-Funktion", "public"),
        ("Erkläre Quantenmechanik", "public"),
        ("Vergleiche REST vs GraphQL", "public"),
    ]

    for q, privacy in test_queries:
        print(f"\n  Query: '{q}'")
        models = decide_p3_models(q, ["qwen", "claude"], privacy)
        print(f"  → Selected: {models}")

    print("\n" + "=" * 70)
    print("Integration Test Complete!")
    print("=" * 70 + "\n")


async def test_atom_decay():
    """Test exponentiellen Decay der Stacks."""
    print("\n" + "=" * 70)
    print("SharedAtom Decay Test: Zeitbasierter Decay")
    print("=" * 70)

    reset_shared_atom()
    atom = get_shared_atom()

    print("\n[1] Initial State:")
    atom.push("model:qwen:success")
    atom.push("model:qwen:success")
    signal = atom.get_signal("model:qwen:success")
    print(f"  Height: {signal['height']:.2f} (2 fresh hits)")

    print("\n[2] Nach 1 Sekunde:")
    await asyncio.sleep(1)
    signal = atom.get_signal("model:qwen:success")
    print(f"  Height: {signal['height']:.2f} (decay_tau=900s, also minimal)")

    print("\n[3] Mit mehr Hits:")
    atom.push("model:qwen:success")
    atom.push("model:qwen:success")
    signal = atom.get_signal("model:qwen:success")
    print(f"  Height: {signal['height']:.2f} (4 Hits, neueste zählen mehr)")

    print("\n" + "=" * 70 + "\n")


async def main():
    await test_atom_integration()
    await test_atom_decay()


if __name__ == "__main__":
    asyncio.run(main())
