#!/usr/bin/env python3
"""
P3.1: Agent Pool — parallel execution of N AgentLoop instances.

Architektur:
- AgentPool(backends: list[str]) → creates N AgentLoop instances (one per backend)
- run_all(query) → asyncio.gather() all agents, returns Dict[model_name, AgentResult]
- AgentResult captures: answer, steps taken, vault_hits, step_count (effort)
- No middleware, no serialization — direct AgentLoop + asyncio.gather
"""

import asyncio
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from agent_loop import AgentLoop
from shared_models import AgentLog
from agent_backends import get_registry


@dataclass
class AgentResult:
    """Ergebnis einer einzelnen Agents-Ausführung."""
    model: str
    answer: str
    step_count: int = 0
    vault_hits: int = 0
    error: Optional[str] = None

    def __repr__(self) -> str:
        if self.error:
            return f"AgentResult({self.model}: ERROR — {self.error})"
        return f"AgentResult({self.model}: {len(self.answer)} chars, {self.step_count} steps)"


class AgentPool:
    """Verwalte N AgentLoop-Instanzen (eine pro Backend)."""

    def __init__(self, backends: List[str]):
        """
        Initialisiere Pool mit angegebenen Backends.
        backends: list of model names ["qwen3", "claude", "gemini", ...]
        """
        self.backends = backends
        self.agents: Dict[str, AgentLoop] = {}

        for backend in backends:
            try:
                self.agents[backend] = AgentLoop(model_name=backend)
            except Exception as e:
                print(f"[WARN] AgentPool: Konnte Agent für {backend} nicht initialisieren: {e}")

    async def run_all(self, query: str) -> Dict[str, AgentResult]:
        """
        Führe Abfrage parallel durch alle aktiven Agents aus.
        Rückgabe: Dict[model_name → AgentResult]
        """
        if not self.agents:
            return {"error": AgentResult("none", "", error="Keine Agents verfügbar")}

        tasks = [
            self._run_one(name, agent, query)
            for name, agent in self.agents.items()
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for res in results:
            if isinstance(res, AgentResult):
                output[res.model] = res
            elif isinstance(res, Exception):
                # Fehlerfall aus gather
                output[f"error_{id(res)}"] = AgentResult(
                    "unknown",
                    "",
                    error=str(res)
                )

        return output

    async def _run_one(self, name: str, agent: AgentLoop, query: str) -> AgentResult:
        """Führe einen Agent aus, sammle Metriken ein."""
        try:
            # Agent starten
            answer = await agent.step(query)

            # Metriken
            step_count = len(agent.log.recent(100))  # geschätzte Schritte
            vault_hits = self._count_vault_hits(agent)

            return AgentResult(
                model=name,
                answer=answer,
                step_count=step_count,
                vault_hits=vault_hits,
                error=None
            )
        except Exception as e:
            print(f"[WARN] AgentPool._run_one({name}): {e}")
            return AgentResult(
                model=name,
                answer="",
                error=str(e)
            )

    @staticmethod
    def _count_vault_hits(agent: AgentLoop) -> int:
        """Zähle search_vault-Actions in letzten Steps."""
        count = 0
        for step in agent.log.recent(20):
            if step.action == "search_vault":
                count += 1
        return count


# ═══ Test / Demo ═══

async def main():
    """Test AgentPool mit qwen3 + claude (wenn verfügbar)."""
    print("═══ P3.1: Agent Pool — Parallel Execution ═══\n")

    registry = get_registry()
    print(registry.status_string())
    print()

    # Sammle verfügbare Backends
    available = []
    for backend in registry.list_all():
        if backend.can_infer_actions:
            # Kürze Namen (z.B. "qwen3:8b (Ollama lokal)" → "qwen3")
            short_name = backend.model_id.split(":")[0] if ":" in backend.model_id else backend.name
            # Mapping für AgentLoop-Kompatibilität
            if "qwen3" in backend.name.lower():
                available.append("qwen3")
            elif "claude" in backend.name.lower():
                available.append("claude")
            elif "gemini" in backend.name.lower():
                available.append("gemini")
            elif "mistral" in backend.name.lower():
                available.append("mistral")

    if not available:
        print("[ERR] Keine Backends verfügbar")
        return

    print(f"[OK] Verfügbare Backends: {available}\n")

    pool = AgentPool(available)

    # Test-Query
    test_query = "Was ist Quantenverschränkung?"
    print(f"[POOL] Query: {test_query}\n")

    results = await pool.run_all(test_query)

    print("\n═══ Ergebnisse ═══\n")
    for model, result in results.items():
        print(f"[{result.model}]")
        if result.error:
            print(f"  ERROR: {result.error}")
        else:
            preview = result.answer[:200].replace("\n", " ")
            print(f"  Answer: {preview}...")
            print(f"  Metrics: {result.step_count} steps, {result.vault_hits} vault_hits")
        print()


if __name__ == "__main__":
    asyncio.run(main())
