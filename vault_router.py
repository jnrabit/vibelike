#!/usr/bin/env python3
"""
vault_router.py - Intelligent Vault Selection (Code vs Knowledge)

Entscheidet VOR dem Workflow: welcher Vault ist für diese Aufgabe relevant?
- Code-Vault:      Projektdateien, SELFCODE, Architektur, Refactoring
- Knowledge-Vault: Konzepte, Externe Docs, Allgemeines Wissen
- Hybrid:          Beides, fair gemerged
- None:            Reine Reasoning-Aufgabe (kein Vault nötig)

Architektur:
1. Heuristik: Keywords, Pfade, Task-Typ → Initialschätzung
2. LLM-Fallback (deepseek): Nur wenn Heuristik unsicher (confidence < 0.7)
3. Confidence Score + Reasoning zurückgeben
"""

import re
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class VaultDecision:
    """Resultat der Vault-Entscheidung."""
    vault_type: str           # "code" | "knowledge" | "hybrid" | "none"
    confidence: float         # 0.0-1.0
    reasoning: str            # Warum diese Entscheidung?
    suggested_mode: str       # "code_focused" | "conceptual" | "balanced"
    requires_llm_fallback: bool


class VaultRouter:
    """Heuristisch + LLM-basiertes Vault-Routing."""

    # Vault-Typ Definitionen
    VAULT_TYPES = {
        "code": {
            "label": "Code-Vault",
            "desc": "SELFCODE: Projektdateien, Funktionen, Klassen, Architektur",
        },
        "knowledge": {
            "label": "Knowledge-Vault",
            "desc": "Wikipedia, RFCs, PEPs, Tools-Docs, allgemeines Wissen",
        },
        "hybrid": {
            "label": "Hybrid (beide)",
            "desc": "Code + Knowledge gemerged nach Relevanz",
        },
        "none": {
            "label": "Kein Vault",
            "desc": "Reine Reasoning-Aufgabe (kein Kontext nötig)",
        },
    }

    # Heuristik-Keywords pro Vault-Typ
    CODE_KEYWORDS = {
        "files": ["datei", "file", "modul", "module", "klasse", "class", "funktion", "function", "method"],
        "changes": ["ändere", "change", "implementiere", "implement", "fix", "refactor", "umstruktur", "refaktor"],
        "architecture": ["architektur", "architecture", "design", "struktur", "pattern"],
        "project": ["projekt", "project", "vibelike", "hótr", "workflow_agent", "terminal", "harvest"],
        "debugging": ["debug", "bug", "fehler", "error", "traceback", "exception"],
    }

    KNOWLEDGE_KEYWORDS = {
        "explain": ["erkläre", "explain", "was ist", "what is", "wie funktioniert", "how does"],
        "concepts": ["konzept", "concept", "theorie", "theory", "algorithmus", "algorithm"],
        "external": ["wikipedia", "rfc", "pep", "standard", "protocol", "specification"],
        "learn": ["lerne", "learn", "verstehe", "understand", "grundlagen", "fundamentals"],
    }

    NONE_KEYWORDS = {
        "reasoning": ["denkst du", "think you", "meinung", "opinion", "begründe", "reason", "analyse", "analysis"],
        "brainstorm": ["brainstorm", "idea", "idee", "vorschlag", "suggestion"],
    }

    def __init__(self, qwen_coder=None):
        """
        Initialisiere Router mit optionalem LLM für Fallback.
        qwen_coder: QwenCoder-Instanz für LLM-Klassifikation (lazy loading ok)
        """
        self.qwen_coder = qwen_coder
        self.llm_calls = 0

    def route(
        self,
        task: str,
        task_type: Optional[str] = None,
        force_vault: Optional[str] = None,
    ) -> VaultDecision:
        """
        Entscheide Vault-Typ für diese Aufgabe.

        Args:
            task: Benutzer-Aufgabe (z.B. "Ändere terminal.py um neue Search zu unterstützen")
            task_type: Optional Klassifikation (ANALYSIS, IMPLEMENTATION, EXPLAIN, BUG_FIX, REFACTOR)
            force_vault: Optional Override (für Tests oder explizite Konfiguration)

        Returns:
            VaultDecision mit vault_type, confidence, reasoning
        """
        # Override
        if force_vault and force_vault in self.VAULT_TYPES:
            return VaultDecision(
                vault_type=force_vault,
                confidence=1.0,
                reasoning=f"Explizit erzwungen: {force_vault}",
                suggested_mode="balanced",
                requires_llm_fallback=False,
            )

        # 1. Heuristik
        heuristic = self._heuristic_route(task, task_type)

        # 2. Wenn Heuristik unsicher → LLM-Fallback
        if heuristic["confidence"] < 0.7 and self.qwen_coder:
            llm = self._llm_route(task, task_type)
            # Kombiniere: LLM hat höheres Gewicht bei Unsicherheit
            return VaultDecision(
                vault_type=llm["vault_type"],
                confidence=llm["confidence"],
                reasoning=llm["reasoning"],
                suggested_mode=self._suggest_mode(llm["vault_type"]),
                requires_llm_fallback=True,
            )

        # 3. Heuristik war sicher genug
        return VaultDecision(
            vault_type=heuristic["vault_type"],
            confidence=heuristic["confidence"],
            reasoning=heuristic["reasoning"],
            suggested_mode=self._suggest_mode(heuristic["vault_type"]),
            requires_llm_fallback=False,
        )

    def _heuristic_route(self, task: str, task_type: Optional[str]) -> dict:
        """Schnelle Heuristik-basierte Entscheidung."""
        task_lower = task.lower()
        scores = {
            "code": 0.0,
            "knowledge": 0.0,
            "hybrid": 0.0,
            "none": 0.0,
        }

        # Task-Typ Hints
        if task_type == "IMPLEMENTATION":
            scores["code"] += 0.4
        elif task_type == "EXPLAIN":
            scores["knowledge"] += 0.4
        elif task_type == "BUG_FIX":
            scores["code"] += 0.4
        elif task_type == "REFACTOR":
            scores["code"] += 0.3
        elif task_type == "ANALYSIS":
            scores["hybrid"] += 0.3

        # Keyword-Scoring
        for keyword_group in self.CODE_KEYWORDS.values():
            if any(kw in task_lower for kw in keyword_group):
                scores["code"] += 0.2

        for keyword_group in self.KNOWLEDGE_KEYWORDS.values():
            if any(kw in task_lower for kw in keyword_group):
                scores["knowledge"] += 0.2

        for keyword_group in self.NONE_KEYWORDS.values():
            if any(kw in task_lower for kw in keyword_group):
                scores["none"] += 0.2

        # Längenheuristik: sehr kurze Fragen → oft Knowledge
        if len(task) < 50:
            scores["knowledge"] += 0.1

        # Pfade/Dateien erwähnt? → Code
        if re.search(r"\.(py|java|js|ts|go|rs)\b|/[a-z_]+\.py", task):
            scores["code"] += 0.3

        # Finde Maximum
        best_vault = max(scores, key=scores.get)
        best_score = scores[best_vault]

        # Normalisiere auf 0-1 (sum=1)
        total = sum(scores.values())
        confidence = (best_score / total) if total > 0 else 0.5

        return {
            "vault_type": best_vault,
            "confidence": min(confidence, 1.0),
            "reasoning": f"Heuristik: {best_vault} (Keywords + Task-Typ)",
            "scores": scores,
        }

    def _llm_route(self, task: str, task_type: Optional[str]) -> dict:
        """LLM-basierte Entscheidung (Fallback bei Unsicherheit)."""
        self.llm_calls += 1

        task_type_hint = f" Task-Typ: {task_type}." if task_type else ""
        prompt = f"""Du bist ein Vault-Router. Entscheide: Welcher Vault ist für diese Aufgabe wichtig?

Aufgabe:
{task}
{task_type_hint}

Vault-Optionen:
1. code: Projektdateien, Funktionen, Architektur, Bugs, Refactoring
2. knowledge: Konzepte, Externe Docs (Wikipedia, RFCs, PEPs), Allgemeines Wissen
3. hybrid: Beide Vaults, fair gemerged
4. none: Reine Reasoning-Aufgabe (kein Kontext nötig)

Antworte AUSSCHLIESSLICH als JSON:
{{
  "vault_type": "code|knowledge|hybrid|none",
  "confidence": 0.0-1.0,
  "reasoning": "kurze Begründung"
}}

Kein Text vor/nach JSON."""

        try:
            raw = self.qwen_coder.generate(prompt, temperature=0.1, stream=False)
            if not raw:
                return self._heuristic_route(task, task_type)

            # Parse JSON
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return self._heuristic_route(task, task_type)

            data = json.loads(match.group(0))
            vault = data.get("vault_type", "hybrid")
            if vault not in self.VAULT_TYPES:
                vault = "hybrid"

            return {
                "vault_type": vault,
                "confidence": float(data.get("confidence", 0.5)),
                "reasoning": f"LLM (deepseek): {data.get('reasoning', '?')}",
            }
        except Exception as e:
            print(f"[WARN] vault_router LLM-Fallback fehlgeschlagen: {e}")
            return self._heuristic_route(task, task_type)

    def _suggest_mode(self, vault_type: str) -> str:
        """Schlag Retrieval-Mode vor."""
        if vault_type == "code":
            return "code_focused"
        elif vault_type == "knowledge":
            return "conceptual"
        else:
            return "balanced"

    def stats(self) -> dict:
        """Statistiken über Router-Nutzung."""
        return {
            "llm_calls": self.llm_calls,
            "vault_types_available": list(self.VAULT_TYPES.keys()),
        }


# ═══ Test / Demo ═══

if __name__ == "__main__":
    print("═══ Vault Router — Demo ═══\n")

    router = VaultRouter(qwen_coder=None)  # Kein LLM für Demo

    test_queries = [
        ("Implementiere einen neuen Harvester für GitHub", "IMPLEMENTATION"),
        ("Was ist Quantenverschränkung?", "EXPLAIN"),
        ("Fix den Import-Fehler in agent_loop.py", "BUG_FIX"),
        ("Refaktoriere workflow_agent.py für bessere Lesbarkeit", "REFACTOR"),
        ("Analysiere die Vault-Architektur", "ANALYSIS"),
        ("Wie funktioniert ChaosRetrieval?", "EXPLAIN"),
    ]

    for query, task_type in test_queries:
        decision = router.route(query, task_type)
        print(f"Query: {query}")
        print(f"  → Vault: {decision.vault_type} ({decision.confidence:.0%})")
        print(f"     Mode:  {decision.suggested_mode}")
        print(f"     Reason: {decision.reasoning}")
        print()

    print(f"\nStats: {router.stats()}")
