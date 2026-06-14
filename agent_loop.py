#!/usr/bin/env python3
"""
P0: Agent Loop — primitive Essenz.

Philosophie: sequenziell, lokal, kein Overhead. Step-für-Step, Modell wählt Action pro Step.
Verwaltung: append-only Log wie ossifikat. Komplexität: im Modell-Prompt + Tool-Code, nicht hier.

Architektur:
- Step: {query, action, params, result, state_before, state_after, timestamp}
- Storage: data/agent_log.jsonl (append-only)
- Tools: Funktionen, die direkt aufgerufen werden (search_vault, read_file, run_sandboxed, verify)
- Loop: model.choose_action(query, state, tools) → execute → observe → log → repeat
"""

import json
import os
import time
import sys
import threading
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from datetime import datetime

# Import Step + AgentLog from shared_models (избегаем дублирования)
from shared_models import Step, AgentLog

ROOT = Path(__file__).parent
AGENT_LOG = ROOT / "data" / "agent_log.jsonl"


class ToolRegistry:
    """Verfügbare Tools für den Agent — SHARED SINGLETON für P3 Parallel-Agents."""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """Thread-safe Singleton getter. Alle AgentLoops teilen sich eine ToolRegistry."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset_for_testing(cls):
        """Test-Helper: Setze Singleton zurück (für Tests)."""
        with cls._lock:
            cls._instance = None

    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self._param_schema: Dict[str, Dict[str, type]] = {}  # Signatur-Validierung
        self._register_builtins()

    def _register_builtins(self):
        """Built-in Tools mit Signatur-Metadaten für Validierung."""
        self.register(
            "search_vault",
            self._tool_search_vault,
            params={"query": str, "scope": str}
        )
        self.register(
            "read_file",
            self._tool_read_file,
            params={"path": str}
        )
        self.register(
            "run_sandboxed",
            self._tool_run_sandboxed,
            params={"command": str, "timeout": int}
        )
        self.register(
            "query_ossifikat",
            self._tool_query_ossifikat,
            params={"query": str, "confirmed_only": bool}
        )
        self.register(
            "verify",
            self._tool_verify,
            params={"statement": str, "method": str}
        )

    def register(self, name: str, func: Callable, params: Dict[str, type] = None) -> None:
        """Registriere ein Tool mit optionaler Signatur."""
        self.tools[name] = func
        if params:
            self._param_schema[name] = params

    def available(self) -> List[str]:
        """Liste der verfügbaren Tools."""
        return list(self.tools.keys())

    async def execute(self, action: str, params: Dict[str, Any]) -> str:
        """Führe ein Tool aus mit Param-Validierung."""
        if action not in self.tools:
            return f"[ERR] Tool '{action}' nicht bekannt. Verfügbar: {self.available()}"

        # Validiere Params gegen bekannte Signatur
        if action in self._param_schema:
            schema = self._param_schema[action]
            for param_name in params:
                if param_name not in schema:
                    expected_keys = list(schema.keys())
                    return f"[ERR] Tool '{action}' erwartet kein param '{param_name}'. Gültig: {expected_keys}"

        try:
            result = self.tools[action](**params)
            # Falls async, warten (für jetzt sync)
            if hasattr(result, "__await__"):
                import asyncio
                result = await result
            return str(result)[:500]  # Gekürzt
        except TypeError as e:
            # Fange Parameter-Mismatch (z.B. missing required arg)
            return f"[ERR] Param-Mismatch in '{action}': {e}"
        except Exception as e:
            return f"[ERR] {type(e).__name__}: {e}"

    # ═══ Built-in Tools (mit echten Implementierungen) ═══

    def _tool_search_vault(self, query: str, scope: str = "all") -> str:
        """Suche in den Vaults (Code + Wissen)."""
        # Import hier (lazy) um zirkuläre Abhängigkeiten zu vermeiden
        try:
            from agent_tools import ToolsFactory
            return ToolsFactory.vault().search(query, k=5)
        except Exception as e:
            return f"[ERR] search_vault() fehlgeschlagen: {e}"

    def _tool_read_file(self, path: str) -> str:
        """Lese eine Datei."""
        try:
            from agent_tools import ToolsFactory
            return ToolsFactory.file().read(path, max_lines=30)
        except Exception as e:
            return f"[ERR] read_file() fehlgeschlagen: {e}"

    def _tool_run_sandboxed(self, command: str, timeout: int = 5) -> str:
        """Führe einen Command in der Sandbox aus (später)."""
        try:
            from agent_tools import ToolsFactory
            return ToolsFactory.sandbox().run(command, timeout=timeout)
        except Exception as e:
            return f"[ERR] run_sandboxed() fehlgeschlagen: {e}"

    def _tool_query_ossifikat(self, query: str, confirmed_only: bool = True) -> str:
        """Abfrage confirmte Fakten aus ossifikat."""
        try:
            from agent_tools import ToolsFactory
            if confirmed_only:
                return ToolsFactory.ossifikat().query_confirmed(subject=query, k=5)
            else:
                return ToolsFactory.ossifikat().list_staging()
        except Exception as e:
            return f"[ERR] query_ossifikat() fehlgeschlagen: {e}"

    def _tool_verify(self, statement: str, method: str = "syntax") -> str:
        """Verifiziere einen Statement (Syntax, Test, Logik)."""
        try:
            from agent_tools import ToolsFactory
            if method == "syntax":
                return ToolsFactory.verify().check_syntax(statement)
            else:
                return f"[STUB] verify('{statement}', method='{method}') — später"
        except Exception as e:
            return f"[ERR] verify() fehlgeschlagen: {e}"


class State:
    """Agent-Zustand zwischen Steps."""

    def __init__(self):
        self.error_context: Optional[str] = None
        self.model_choice: Optional[str] = None
        # Nutze SHARED Singleton ToolRegistry
        self.tools_available = ToolRegistry.get_instance().available()
        self.step_count = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_context": self.error_context,
            "model_choice": self.model_choice,
            "tools_available": self.tools_available,
            "step_count": self.step_count,
        }

    def observe(self, result: str, success: bool = True) -> None:
        """Beobachte das Resultat und passe State an."""
        if not success:
            self.error_context = result[:200]
        self.step_count += 1


class AgentLoop:
    """Der Kern: Schritt für Schritt, primitiv verwaltet. Nutzt SHARED ToolRegistry."""

    def __init__(self, model_name: str = "qwen3:8b"):
        self.model_name = model_name
        self.log = AgentLog()
        # Nutze SHARED Singleton ToolRegistry (für P3 Parallel-Agents)
        self.tools = ToolRegistry.get_instance()
        self.state = State()
        self._decider = None  # lazy, einmal erstellt
        self._coder = None   # lazy ModelCoder (kein Socket-Check pro Query)

        # Analyzer-Coder für Reasoning-Tasks (z.B. TaskClassifier)
        # Lazy-loaded bei erster Verwendung
        self._analyzer_coder = None

    @property
    def analyzer_coder(self):
        """Lazy-loaded Analyzer-Coder (für TaskClassifier + Reasoning)."""
        if self._analyzer_coder is None:
            try:
                from terminal import QwenCoder, ANALYSIS_MODEL
                self._analyzer_coder = QwenCoder(model=ANALYSIS_MODEL)
            except Exception as e:
                print(f"[WARN] analyzer_coder init failed: {e}, falling back to default")
                from agent_inference import ModelCoder
                self._analyzer_coder = ModelCoder()
        return self._analyzer_coder

    async def step(self, query: str, correlation_id: Optional[str] = None, max_steps: int = 5) -> str:
        """Ein Agent-Durchlauf: query → Schritte → Antwort.

        Stop-Bedingung: Modell wählt action='done' (Healthpoint-Anker) ODER max_steps.
        Synthese-Antwort: nach dem Loop generiert das Modell eine finale Antwort aus
        allen Tool-Ergebnissen (statt roher Tool-Output).
        """
        cid = correlation_id or f"{int(time.time() * 1000)}"
        print(f"\n[AGENT] Starte '{query[:60]}' (cid={cid})")

        tool_results = []  # alle Tool-Ergebnisse für die Synthese

        for step_idx in range(max_steps):
            self.state.step_count = step_idx

            # Recent Steps NUR aus diesem Query-Lauf (cid-gefiltert) — verhindert
            # dass done-Antworten aus vorherigen Queries das Modell vergiften
            recent = [vars(s) for s in self.log.recent(6)
                      if s.correlation_id == cid]

            action = self._choose_action(query, self.state, recent)
            if not action:
                break

            action_name, params = action
            # Wenn Modell search_vault/query_ossifikat/verify ohne params wählt → query einsetzen
            if action_name in ("search_vault", "query_ossifikat") and "query" not in params:
                params = {"query": query}
            elif action_name == "verify" and "statement" not in params:
                params = {"statement": query}
            print(f"  [{step_idx}] {action_name}({list(params.keys())})")

            # done-Action = Modell signalisiert "genug Infos" (Healthpoint-Anker)
            # Guard: done auf Schritt 0 ohne Tool-Ergebnisse → erst recherchieren
            if action_name == "done":
                if step_idx == 0 and not tool_results:
                    # Kein Kontext gesammelt → erzwinge search_vault
                    action_name, params = "search_vault", {"query": query}
                    print(f"    (done ohne Kontext → search_vault erzwungen)")
                else:
                    answer = params.get("answer", "").strip()
                    if answer:
                        print(f"  → done nach {step_idx} Schritten")
                        # done NICHT ins Log — würde nächsten Query vergiften
                        return answer
                    print(f"  → done (kein answer) — direkte Antwort")
                    return self._synthesize(query, tool_results or [])

            # Tool ausführen
            result = await self.tools.execute(action_name, params)
            print(f"      → {result[:100]}")

            self._log_step(query, action_name, params, result, cid)

            success = not result.startswith("[ERR]") and "[STUB]" not in result
            self.state.observe(result, success)

            if success:
                tool_results.append(f"[{action_name}] {result[:300]}")

        # Synthese: Modell formuliert finale Antwort aus den Tool-Ergebnissen
        if tool_results:
            return self._synthesize(query, tool_results)
        elif tool_results is not None:
            return self._fallback_answer(query)
        return "[STOP] keine Tool-Ergebnisse"

    def _log_step(self, query: str, action: str, params: dict, result: str, cid: str):
        """Schreibe einen Step ins Log (append-only wie ossifikat)."""
        s = Step(
            query=query,
            action=action,
            params=params,
            result=result,
            state_before=self.state.to_dict(),
            state_after=self.state.to_dict(),
            correlation_id=cid,
        )
        self.log.append(s)

    def _synthesize(self, query: str, tool_results: list) -> str:
        """Generiere finale Antwort aus Tool-Ergebnissen (Cloud → Lokal Fallback)."""
        try:
            from agent_inference import ModelCoderFactory

            coder = ModelCoderFactory.get(self.model_name)
            if self._coder is None:
                self._coder = coder

            # Use the right coder for this model
            if coder and coder.client:
                if tool_results:
                    context = "\n\n".join(tool_results)
                    prompt = (f"FRAGE: {query}\n\n"
                              f"GEFUNDENE INFORMATIONEN:\n{context}\n\n"
                              f"Beantworte die Frage auf Basis der gefundenen Informationen. "
                              f"Antworte auf Deutsch, präzise und direkt.")
                else:
                    prompt = (f"{query}\n\nAntworte auf Deutsch, natürlich und hilfreich.")
                result = coder.generate(prompt, temperature=0.3, max_tokens=600)
                if result:
                    return result

            return "\n\n".join(tool_results) if tool_results else f"[WARN] keine Antwort für '{query[:60]}'"
        except Exception:
            return "\n\n".join(tool_results) if tool_results else ""

    def _fallback_answer(self, query: str) -> str:
        """Antwort wenn keine Tools erfolgreich waren."""
        return f"[WARN] Keine verwertbaren Informationen für '{query[:60]}' gefunden."

    def _choose_action(self, query: str, state: State, recent_steps: list = None) -> Optional[tuple]:
        """Modell wählt nächste Action — LLM-Inferencing mit Fallback."""
        recent_steps = recent_steps or []
        try:
            from agent_inference import ActionDecider
            if self._decider is None:
                self._decider = ActionDecider(model=self.model_name)
            available = state.tools_available + ["done"]
            action, params = self._decider.decide(
                query=query,
                available_tools=available,
                recent_steps=recent_steps,
            )
            if action:
                return (action, params)
        except Exception:
            pass

        # Fallback-Heuristik
        q = query.lower()
        if "search" in q or "find" in q or "suche" in q:
            return ("search_vault", {"query": query})
        elif "read" in q or "file" in q or "lies" in q or "datei" in q:
            return ("read_file", {"path": "terminal.py"})
        elif "verify" in q or "check" in q or "syntax" in q or "prüf" in q:
            return ("verify", {"statement": query})
        else:
            return ("query_ossifikat", {"query": query})


# ═══ Demo / Test ═══

async def demo():
    """P0-Demo: zeige das Step-Log in Aktion."""
    loop = AgentLoop()

    # Ein paar Fragen durchspielen
    queries = [
        "Suche nach Vault-Retrieval in der Codebase",
        "Lies die README",
        "Verifiziere die terminal.py Syntax",
    ]

    for q in queries:
        result = await loop.step(q)
        print(f"  ↳ {result}\n")

    # Statistiken zeigen
    print("\n═══ Agent-Log Statistiken ═══")
    stats = loop.log.stats()
    print(f"Total Steps: {stats['total']}")
    print(f"By Action: {stats['by_action']}")

    # Letzte Steps anzeigen
    print(f"\nLetzte 3 Steps:")
    for s in loop.log.recent(3):
        print(f"  [{s.action}] {s.result[:50]}...")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())
