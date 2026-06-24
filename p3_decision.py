#!/usr/bin/env python3
"""
P3 Model Decision Engine: Multi-Signal Selection (Topf-Prinzip).

Integration von SharedAtom-Stacks mit anderen Auswahl-Kriterien.
Alle Signale nebeneinander (nicht hierarchisch).
"""

from typing import List, Dict, Optional
from vibelike.shared_atom import get_shared_atom


class P3ModelDecision:
    """Entscheide welche Models für P3 parallel laufen."""

    def __init__(self, available_models: List[str]):
        """
        available_models: z.B. ["qwen", "claude"]
        """
        self.available_models = available_models
        self.atom = get_shared_atom()

    def decide(self, query: str, privacy_level: str = "public") -> List[str]:
        """
        Wähle Top-2 Models basierend auf mehreren Signalen.

        Returns: List von Model-Namen (z.B. ["qwen", "claude"])
        """
        scores = {}

        for model in self.available_models:
            score = 0.0

            # Signal 1: SharedAtom-Stack (Historische Erfolge)
            stack_signal = self.atom.get_signal(f"model:{model}:success")
            if stack_signal:
                atom_contribution = stack_signal["normalized"] * 10.0  # 0-10 Punkte
                score += atom_contribution
                print(f"    [{model}] Atom: {atom_contribution:.1f} (height {stack_signal['height']:.2f})")

            # Signal 2: Query-Type-Heuristik
            heuristic = self._query_type_heuristic(query, model)
            score += heuristic
            if heuristic > 0:
                print(f"    [{model}] Heuristic: {heuristic:.1f}")

            # Signal 3: Privacy-Level-Matching
            privacy_bonus = self._privacy_match(privacy_level, model)
            score += privacy_bonus
            if privacy_bonus > 0:
                print(f"    [{model}] Privacy match: {privacy_bonus:.1f}")

            scores[model] = score

        # Sortiere und nimm alle verfügbaren Models (nicht nur Top-2!)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        selected = [m for m, _ in ranked]  # Alle nehmen, nicht nur Top-2

        print(f"  → P3 Selected: {selected} (scores: {[f'{s:.1f}' for _, s in ranked]})")

        return selected if selected else self.available_models

    def _query_type_heuristic(self, query: str, model: str) -> float:
        """
        Gebe Bonus-Punkte basierend auf Query-Typ.

        z.B.: Python-Code-Fragen bevorzugen qwen
              Reasoning-Fragen bevorzugen claude
              Diverse Queries bevorzugen mistral
        """
        q = query.lower()
        score = 0.0

        # qwen ist gut für Code/Technical
        if model == "qwen" and any(kw in q for kw in ["python", "code", "syntax", "function", "class"]):
            score += 5.0
        if model == "qwen" and any(kw in q for kw in ["algorithm", "performance", "architecture"]):
            score += 3.0

        # claude ist gut für Reasoning/Erklärungen
        if model == "claude" and any(kw in q for kw in ["explain", "why", "reason", "understand"]):
            score += 5.0
        if model == "claude" and any(kw in q for kw in ["philosophy", "ethics", "analyze", "compare"]):
            score += 3.0

        # mistral ist gut für diverse/balanced Fragen
        if model == "mistral" and any(kw in q for kw in ["was", "wie", "wer", "wo", "wann"]):
            score += 2.0

        return score

    def _privacy_match(self, privacy_level: str, model: str) -> float:
        """
        Privacy-Level-abhängiger Bonus.

        z.B.: LOCAL-only queries → nur lokale Modelle (qwen)
        """
        if privacy_level in ("SECRET", "INTERNAL"):
            # Nur lokale Modelle
            if model == "qwen":
                return 2.0
        elif privacy_level == "PUBLIC":
            # Alle Models OK
            pass

        return 0.0


def decide_p3_models(
    query: str,
    available_models: List[str] = None,
    privacy_level: str = "public"
) -> List[str]:
    """
    Convenience-Funktion für P3 Model-Entscheidung.

    Einfach in terminal.py aufrufen statt hardcodierter Models.
    """
    if available_models is None:
        available_models = ["qwen", "claude"]

    print(f"[P3-DECISION] Scoring models für query: '{query[:50]}...'")
    decision = P3ModelDecision(available_models)
    return decision.decide(query, privacy_level)


if __name__ == "__main__":
    # Test
    from vibelike.shared_atom import SharedAtom

    atom = SharedAtom()

    # Simuliere ein paar qwen-Erfolge
    atom.push("model:qwen:success")
    atom.push("model:qwen:success")

    print("Test: Entscheide Models für verschiedene Queries\n")

    test_queries = [
        "Schreib mir eine Python-Funktion für Fibonacci",
        "Erkläre mir die Quantenmechanik",
        "Was ist der Unterschied zwischen REST und GraphQL?",
        "Philosophische Fragen zur KI-Ethik",
    ]

    for q in test_queries:
        print(f"\n[Q] {q}")
        selected = decide_p3_models(q, privacy_level="public")
        print()
