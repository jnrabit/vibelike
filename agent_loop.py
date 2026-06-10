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
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
AGENT_LOG = ROOT / "data" / "agent_log.jsonl"


@dataclass
class Step:
    """Eine Iteration des Agent-Loops: was wurde versucht, was passierte."""
    query: str                    # ursprüngliche Frage oder Kontext
    action: str                   # "search_vault" | "read_file" | "run_sandboxed" | "verify" | ...
    params: Dict[str, Any]        # Argumente für die Action
    result: str                   # Antwort der Action (Text, Länge gekürzt)
    state_before: Dict[str, Any]  # {model_choice, tools_available, error_context}
    state_after: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None  # Trace-ID für zusammenhängende Queries

    def to_json(self) -> str:
        """Serialisiere als JSONL-Zeile."""
        d = asdict(self)
        d["timestamp"] = self.timestamp
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "Step":
        """Deserialisiere aus JSONL-Zeile."""
        d = json.loads(line)
        return cls(**d)


class AgentLog:
    """Append-only Log der Steps (wie ossifikat für Tripel)."""

    def __init__(self, log_path: Path = AGENT_LOG):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, step: Step) -> None:
        """Speichere einen Step (append-only)."""
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(step.to_json() + "\n")

    def read_all(self) -> List[Step]:
        """Alle Steps lesen (für Kontext/Analysen)."""
        steps = []
        if not self.log_path.exists():
            return steps
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    steps.append(Step.from_json(line))
                except json.JSONDecodeError:
                    continue
        return steps

    def recent(self, n: int = 5) -> List[Step]:
        """Letzte N Steps (für Modell-Kontext)."""
        return self.read_all()[-n:]

    def by_correlation(self, cid: str) -> List[Step]:
        """Alle Steps einer Query-Familie."""
        return [s for s in self.read_all() if s.correlation_id == cid]

    def stats(self) -> Dict[str, Any]:
        """Einfache Statistiken."""
        steps = self.read_all()
        if not steps:
            return {"total": 0, "by_action": {}}
        actions = {}
        for s in steps:
            actions[s.action] = actions.get(s.action, 0) + 1
        return {
            "total": len(steps),
            "by_action": actions,
            "first": steps[0].timestamp,
            "last": steps[-1].timestamp,
        }


class ToolRegistry:
    """Verfügbare Tools für den Agent."""

    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self._register_builtins()

    def _register_builtins(self):
        """Built-in Tools: Platzhalter, werden später gefüllt."""
        self.register("search_vault", self._tool_search_vault)
        self.register("read_file", self._tool_read_file)
        self.register("run_sandboxed", self._tool_run_sandboxed)
        self.register("query_ossifikat", self._tool_query_ossifikat)
        self.register("verify", self._tool_verify)

    def register(self, name: str, func: Callable) -> None:
        """Registriere ein Tool."""
        self.tools[name] = func

    def available(self) -> List[str]:
        """Liste der verfügbaren Tools."""
        return list(self.tools.keys())

    async def execute(self, action: str, params: Dict[str, Any]) -> str:
        """Führe ein Tool aus."""
        if action not in self.tools:
            return f"[ERR] Tool '{action}' nicht bekannt. Verfügbar: {self.available()}"
        try:
            result = self.tools[action](**params)
            # Falls async, warten (für jetzt sync)
            if hasattr(result, "__await__"):
                import asyncio
                result = await result
            return str(result)[:500]  # Gekürzt
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
        self.tools_available = ToolRegistry().available()
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
    """Der Kern: Schritt für Schritt, primitiv verwaltet."""

    def __init__(self, model_name: str = "qwen3:8b"):
        self.model_name = model_name
        self.log = AgentLog()
        self.tools = ToolRegistry()
        self.state = State()

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

            # Recent Steps aus Log (letzte 3) als Kontext ans Modell
            recent = [vars(s) for s in self.log.recent(3)]

            action = self._choose_action(query, self.state, recent)
            if not action:
                break

            action_name, params = action
            print(f"  [{step_idx}] {action_name}({list(params.keys())})")

            # done-Action = Modell signalisiert "genug Infos" (Healthpoint-Anker)
            if action_name == "done":
                answer = params.get("answer", "").strip()
                if answer:
                    print(f"  → done nach {step_idx} Schritten")
                    self._log_step(query, "done", params, answer, cid)
                    return answer
                break

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
        """Generiere finale Antwort aus Tool-Ergebnissen (Modell-Synthese)."""
        try:
            from agent_inference import ModelCoder
            coder = ModelCoder(self.model_name)
            if not coder.client:
                # Kein Modell → einfache Zusammenfassung der Tool-Outputs
                return "\n\n".join(tool_results)
            context = "\n\n".join(tool_results)
            prompt = (f"FRAGE: {query}\n\n"
                      f"GEFUNDENE INFORMATIONEN:\n{context}\n\n"
                      f"Beantworte die Frage auf Basis der gefundenen Informationen. "
                      f"Antworte auf Deutsch, präzise und direkt.")
            return coder.generate(prompt, temperature=0.2, max_tokens=600)
        except Exception:
            return "\n\n".join(tool_results)

    def _fallback_answer(self, query: str) -> str:
        """Antwort wenn keine Tools erfolgreich waren."""
        return f"[WARN] Keine verwertbaren Informationen für '{query[:60]}' gefunden."

    def _choose_action(self, query: str, state: State, recent_steps: list = None) -> Optional[tuple]:
        """Modell wählt nächste Action — LLM-Inferencing mit Fallback."""
        recent_steps = recent_steps or []
        try:
            from agent_inference import ActionDecider
            decider = ActionDecider(model=self.model_name)
            # Tools inkl. 'done' (Stop-Signal)
            available = state.tools_available + ["done"]
            action, params = decider.decide(
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
