#!/usr/bin/env python3
"""
P3.3: Consensus Evaluator — human-like scoring + gap detection + auto-fill.

Architektur:
- Scoring: 40% keyword-overlap + 40% capability-fit + 20% effort (vault_hits + steps)
- Lücken-Erkennung: Themen die ≥2 Modelle erwähnen aber 1 auslässt
- Auto-Gap-Fill: Schwacher Agent mit Hinweis nochmal aufgerufen
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from agent_pool import AgentResult, AgentPool


# Modell-Stärken für verschiedene Task-Typen (Fähigkeitskarte)
CAPABILITY_MAP = {
    "claude": {
        "code": 0.9,
        "reasoning": 0.95,
        "factual": 0.85,
        "creative": 0.8,
        "default": 0.87,
    },
    "gemini": {
        "code": 0.8,
        "reasoning": 0.85,
        "factual": 0.9,
        "creative": 0.85,
        "default": 0.85,
    },
    "qwen3": {
        "code": 0.7,
        "reasoning": 0.7,
        "factual": 0.65,
        "creative": 0.6,
        "default": 0.66,
    },
    "mistral": {
        "code": 0.75,
        "reasoning": 0.75,
        "factual": 0.8,
        "creative": 0.7,
        "default": 0.75,
    },
    "openrouter": {
        "code": 0.5,
        "reasoning": 0.6,
        "factual": 0.7,
        "creative": 0.5,
        "default": 0.58,
    },
}


@dataclass
class ConsensusResult:
    """Ergebnis der Consensus-Bewertung."""
    winner: str                    # Modellname des Gewinners
    winner_answer: str             # Die beste Antwort
    winner_score: float            # Score des Gewinners (0.0-1.0)
    scores: Dict[str, float]       # Alle Scores {model → score}
    missing_gaps: Dict[str, List[str]]  # {model → [topics the model missed]}
    gaps_filled: Optional[str] = None   # Welche Gaps wurden nach auto-fill behoben?


class Consensus:
    """Evaluiere Responses von mehreren Agents (keine LLM-Overhead)."""

    def __init__(self):
        self.task_type = "default"  # Wird via Heuristik erkannt

    def evaluate(
        self,
        responses: Dict[str, AgentResult],
        query: str
    ) -> ConsensusResult:
        """
        Bewerte alle Responses, bestimme Winner + Gaps.
        """
        if not responses:
            return ConsensusResult(
                winner="none",
                winner_answer="",
                winner_score=0.0,
                scores={},
                missing_gaps={},
                gaps_filled=None
            )

        # Erkenne Task-Type aus Query
        self.task_type = self._detect_task_type(query)

        # Berechne Scores für jeden Response
        scores = {}
        normalized = {}

        for model, result in responses.items():
            if result.error:
                scores[model] = 0.0
                continue

            overlap_score = self._calc_overlap_score(
                result.answer,
                {m: r.answer for m, r in responses.items() if not r.error and m != model}
            )
            capability_score = self._calc_capability_score(model)
            effort_score = self._calc_effort_score(result)

            # Gewichtet: 40% overlap + 40% capability + 20% effort
            weighted = (
                0.40 * overlap_score +
                0.40 * capability_score +
                0.20 * effort_score
            )
            scores[model] = weighted
            normalized[model] = result.answer

        # Finde Winner
        winner = max(scores, key=scores.get) if scores else "unknown"
        winner_score = scores.get(winner, 0.0)

        # Erkenne Lücken
        missing_gaps = self._detect_gaps(normalized)

        return ConsensusResult(
            winner=winner,
            winner_answer=responses[winner].answer if winner in responses else "",
            winner_score=winner_score,
            scores=scores,
            missing_gaps=missing_gaps,
            gaps_filled=None
        )

    async def evaluate_and_fill(
        self,
        responses: Dict[str, AgentResult],
        query: str,
        pool: AgentPool
    ) -> ConsensusResult:
        """
        Evaluiere, erkenne Gaps, auto-fill schwache Agents (einmalig).
        """
        result = self.evaluate(responses, query)

        # Prüfe ob es Lücken mit signifikanten Gaps gibt
        significant_gaps = {
            model: gaps for model, gaps in result.missing_gaps.items()
            if len(gaps) >= 2  # ≥2 Topics augelassen
        }

        if not significant_gaps:
            return result

        print(f"[CONSENSUS] Erkannte Lücken: {significant_gaps}")

        # Auto-Fill: DISABLED für jetzt (zu aggressiv, verursacht Fehler bei schwachen Modellen)
        # Wird aktiviert wenn P3 stabiler läuft
        # weakest = min(result.scores, key=result.scores.get)
        # if weakest not in pool.agents:
        #     return result
        #
        # print(f"[AUTO-FILL] Frage {weakest} nochmal mit Hinweis...")
        # gap_hint = ", ".join(significant_gaps[weakest][:3])
        # gap_query = f"{query}\n[Ergänze bitte: {gap_hint}]"
        # try:
        #     filled_answer = await pool.agents[weakest].step(gap_query, max_steps=2)
        #     responses[weakest].answer = filled_answer
        #     responses[weakest].step_count += 2
        #     result = self.evaluate(responses, query)
        #     result.gaps_filled = gap_hint
        # except Exception as e:
        #     print(f"[WARN] Auto-Fill fehlgeschlagen: {e}")

        return result

    def _detect_task_type(self, query: str) -> str:
        """Erkenne Task-Type aus Query (heuristisch)."""
        q_lower = query.lower()
        if any(w in q_lower for w in ["code", "python", "javascript", "function"]):
            return "code"
        if any(w in q_lower for w in ["warum", "reason", "explain", "logic"]):
            return "reasoning"
        if any(w in q_lower for w in ["was", "wer", "wann", "wo", "fact", "true"]):
            return "factual"
        if any(w in q_lower for w in ["schreib", "create", "story", "idee", "imagine"]):
            return "creative"
        return "default"

    @staticmethod
    def _calc_overlap_score(answer: str, other_answers: Dict[str, str]) -> float:
        """
        Berechne Overlap-Score: wie viele Schlüsselwörter teilt dieser Answer mit anderen?
        """
        if not other_answers or not answer:
            return 0.0

        # Extrahiere Keywords (≥5 Zeichen, kein Satzzeichen)
        words = set(
            w.lower() for w in re.findall(r'\b\w{5,}\b', answer)
        )

        if not words:
            return 0.0

        # Zähle Matches mit anderen Answers
        total_matches = 0
        for other in other_answers.values():
            other_words = set(w.lower() for w in re.findall(r'\b\w{5,}\b', other))
            matches = len(words & other_words)
            total_matches += matches

        # Normalize: (matches / max_possible)
        if total_matches == 0:
            return 0.0

        max_possible = len(words) * len(other_answers)
        overlap = min(total_matches / max_possible, 1.0)
        return overlap

    @staticmethod
    def _calc_capability_score(model: str) -> float:
        """
        Hole Fähigkeit für diesen Model (auf Basis task_type).
        """
        return CAPABILITY_MAP.get(model, {}).get("default", 0.5)

    @staticmethod
    def _calc_effort_score(result: AgentResult) -> float:
        """
        Berechne Effort-Score: wie viel hat der Agent recherchiert?
        vault_hits + steps genommen.
        """
        if result.error:
            return 0.0

        # Normalisiere: mehr Steps/Hits = höherer Score
        # Cap bei 4 Steps + 2 Vault-Hits
        effort = min((result.step_count + result.vault_hits * 2) / 8.0, 1.0)
        return effort

    @staticmethod
    def _detect_gaps(normalized: Dict[str, str]) -> Dict[str, List[str]]:
        """
        Erkenne Lücken: Topics die ≥2 Modelle erwähnen aber 1 auslässt.
        """
        missing_gaps = {}

        if len(normalized) < 2:
            return missing_gaps

        # Extrahiere keywords aus jedem Response
        models_keywords = {}
        for model, answer in normalized.items():
            keywords = set(w.lower() for w in re.findall(r'\b\w{6,}\b', answer))
            models_keywords[model] = keywords

        # Finde Gaps: Keywords die in ≥2 anderen erwähnt sind aber hier nicht
        for model, keywords in models_keywords.items():
            other_models = [m for m in models_keywords if m != model]
            if len(other_models) < 2:
                continue

            # Keywords die in ≥2 anderen erwähnt sind
            other_keywords = {}
            for other_model in other_models:
                for kw in models_keywords[other_model]:
                    other_keywords[kw] = other_keywords.get(kw, 0) + 1

            # Gap = Keywords die in ≥2 anderen aber nicht hier erwähnt sind
            gaps = [kw for kw, count in other_keywords.items() if count >= 2 and kw not in keywords]
            if gaps:
                missing_gaps[model] = gaps[:5]  # Erste 5 Gaps

        return missing_gaps


# ═══ Test / Demo ═══

async def main():
    """Test Consensus mit Mock-Responses."""
    print("═══ P3.3: Consensus — Evaluation + Gap-Detection ═══\n")

    consensus = Consensus()

    # Mock-Responses
    responses = {
        "qwen3": AgentResult(
            model="qwen3",
            answer="Quantenverschränkung ist ein Phänomen der Quantenmechanik, bei dem zwei Teilchen eine nicht-lokale Verbindung haben.",
            step_count=2,
            vault_hits=1,
            error=None
        ),
        "claude": AgentResult(
            model="claude",
            answer="Quantenverschränkung (Entanglement) verbindet zwei oder mehr Quantensysteme so, dass ihr Zustand nur gemeinsam beschrieben werden kann. Dies führt zu Korrelationen, die klassisch unmöglich sind.",
            step_count=3,
            vault_hits=2,
            error=None
        ),
        "gemini": AgentResult(
            model="gemini",
            answer="Zwei Teilchen sind verschränkt, wenn ihre Quantenzustände korreliert sind. Die Messung eines Teilchens beeinflusst den Zustand des anderen augenblicklich.",
            step_count=1,
            vault_hits=0,
            error=None
        ),
    }

    query = "Was ist Quantenverschränkung?"

    print(f"[QUERY] {query}\n")
    print("[TEST] Consensus.evaluate()\n")

    result = consensus.evaluate(responses, query)

    print(f"Winner: {result.winner}")
    print(f"Winner Score: {result.winner_score:.2%}\n")

    print("Scores:")
    for model, score in sorted(result.scores.items(), key=lambda x: x[1], reverse=True):
        print(f"  {model:12s}: {score:.2%}")

    print("\nMissing Gaps:")
    for model, gaps in result.missing_gaps.items():
        print(f"  {model:12s}: {gaps}")

    print("\n[OK] Test abgeschlossen")


if __name__ == "__main__":
    asyncio.run(main())
