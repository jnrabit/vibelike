#!/usr/bin/env python3
"""
Agent Harness — terminal.py + Agent-Loop Integrations-Wrapper.

Zeigt: wie man den Agent-Loop von terminal.py aus nutzt.
Phased: Phase 1 (jetzt) = Integration-Skelett + Dokumentation.
        Phase 2 (später) = main() umschreiben um Agent-Mode zu nutzen.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent

import asyncio
from vibelike.agent_loop import AgentLoop
from vibelike.agent_backends import get_registry
from vibelike.terminal import CodeRetriever, QwenCoder, build_system_prompt, KNOWLEDGE_ANSWER_MODEL


async def run_agent_query(query: str, agent: AgentLoop) -> str:
    """Führe eine Query durch den Agent-Loop aus (mit Fallback auf normal-Flow)."""
    print(f"[AGENT-MODE] Query: {query}")

    # Agent-Loop starten
    result = await agent.step(query)

    return result


async def main_agent_mode(enable_agent: bool = True):
    """Agent-Mode: Query→Agent-Loop→Answer (mit Fallback auf Normal-Mode)."""
    print("[AGENT-MODE] Lade hótr̥ mit Agent-Loop...")

    # Backend-Status
    registry = get_registry()
    print(registry.status_string())

    # Retriever + Coder (wie normal)
    print("\n[INIT] Lade Vaults...")
    retriever = CodeRetriever()
    coder = QwenCoder(model=KNOWLEDGE_ANSWER_MODEL)

    # Agent-Loop (neu)
    print("[INIT] Initialisiere Agent-Loop...")
    agent = AgentLoop(model_name="qwen3:8b")

    print("\n[OK] Bereit für Queries (Agent-Mode)")
    print("   Tip: 'q' zum Beenden, normale Query-Syntax\n")

    history = []

    while True:
        try:
            query = input("\n> ").strip()

            if not query:
                continue

            if query.lower() == "q":
                print("[BYE] Auf Wiedersehen")
                break

            if query.lower() == "c":
                history.clear()
                agent.state.step_count = 0
                print("[OK] Kontext gelöscht")
                continue

            # Agent-Mode: Agent lädt los
            if enable_agent:
                result = await run_agent_query(query, agent)
            else:
                # Fallback: Normal-Flow (Retrieval→Generate)
                context, _, _ = retriever.search(query, k=6)
                system_prompt = build_system_prompt(context)
                print(f"\n{KNOWLEDGE_ANSWER_MODEL}...\n" + "-" * 60)
                result = coder.generate(query, system=system_prompt, stream=True)
                print("-" * 60)

            # History
            clean = result.replace("<think>", "").replace("</think>", "")[:100]
            history.append((query, clean))
            if len(history) > 6:
                del history[:-6]

        except KeyboardInterrupt:
            print("\n[STOP] Unterbrochen")
            break
        except Exception as e:
            print(f"[ERR] {e}")


# ═══ Entry Point ═══

if __name__ == "__main__":
    print("═══ Agent Harness — terminal.py + Agent-Loop ═══\n")
    print("Dies ist ein Integration-Skelett (Phase 1).")
    print("Phase 2 (später): main() umschreiben um Agent-Mode zu nutzen.\n")

    asyncio.run(main_agent_mode(enable_agent=True))
