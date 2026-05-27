"""
healthpoint.py — Versiegelter Ziel-Anker gegen Phasen-Drift.

Die eine tragende Idee aus dem inkonsistence-Konzept (die Gate/Superposition-
Maschinerie bleibt geparkt): Das Ziel wird beim Briefing EINMAL versiegelt und
an jeder Phasengrenze + final dagegen geprueft. Faengt kumulativen Drift —
Briefing sagt X, Plan wird leise Y, Code macht Z.

Verwandt mit ossifikat: ossifikat faengt Widerspruch zum VERGANGENEN Ich
(Veraltung ueber Laeufe), Healthpoint faengt Widerspruch zum eigenen ZIEL
(Drift ueber Phasen). Konsistenz-Anker auf verschiedenen Zeitskalen.

Der Judge ist duck-typed auf QwenCoder (.generate(prompt, temperature, stream)),
damit das Modul direkt das analyzer_qwen des Workflows nutzen kann.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


class Healthpoint:
    """Der EINE versiegelte Ziel-Anker. Nach Konstruktion read-only."""

    def __init__(self, goal: str, invariants: list[str] | None = None):
        object.__setattr__(self, "_goal", goal.strip())
        object.__setattr__(self, "_invariants", tuple(i.strip() for i in (invariants or []) if i.strip()))
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name, value):  # versiegelt: keine Mutation nach Init
        raise AttributeError(f"Healthpoint ist versiegelt — '{name}' nicht aenderbar")

    @property
    def goal(self) -> str:
        return self._goal

    @property
    def invariants(self) -> tuple[str, ...]:
        return self._invariants

    def render(self) -> str:
        lines = [f"ZIEL (versiegelt): {self._goal}"]
        if self._invariants:
            lines.append("INVARIANTEN (muessen wahr bleiben):")
            lines.extend(f"  - {inv}" for inv in self._invariants)
        return "\n".join(lines)


@dataclass(frozen=True)
class DriftVerdict:
    phase: str
    aligned: bool
    drift: str  # 1-Satz-Begruendung wenn drift, sonst ""

    @property
    def symbol(self) -> str:
        return "🟢" if self.aligned else "🔴"

    def render(self) -> str:
        if self.aligned:
            return f"{self.symbol} {self.phase}: am Ziel"
        return f"{self.symbol} {self.phase}: DRIFT — {self.drift}"


_JUDGE_SYSTEM = (
    "Du bist ein Drift-Waechter. Du pruefst NUR, ob ein Phasen-Output noch dem "
    "VERSIEGELTEN Ziel dient — nicht ob er gut/elegant ist. Achte auf: "
    "Scope-Creep (mehr als verlangt), Ziel-Substitution (was anderes gebaut), "
    "fallengelassene Anforderungen (Invariante verletzt)."
)


def check_drift(hp: Healthpoint, phase_name: str, phase_output: str, judge) -> DriftVerdict:
    """Prueft EIN Phasen-Ergebnis gegen den versiegelten Healthpoint.

    judge: QwenCoder-artig (.generate(prompt, temperature, stream)).
    Bei Parse-/Judge-Fehler: konservativ aligned=True (kein false-positive-Abbruch).
    """
    prompt = f"""{hp.render()}

PHASE: {phase_name}
OUTPUT DIESER PHASE:
{phase_output[:3000]}

Dient dieser Output noch dem versiegelten Ziel oben? Beachte Scope-Creep,
Ziel-Substitution, verletzte Invarianten.

Antworte AUSSCHLIESSLICH mit JSON, kein Text drumherum:
{{"aligned": true, "drift": ""}}
oder
{{"aligned": false, "drift": "<EIN Satz: was genau vom Ziel abgewichen ist>"}}"""

    try:
        raw = judge.generate(prompt, system=_JUDGE_SYSTEM, temperature=0.0, stream=False)
    except TypeError:
        # Judge ohne system-Parameter
        raw = judge.generate(prompt, temperature=0.0, stream=False)
    except Exception as e:
        return DriftVerdict(phase_name, aligned=True, drift=f"[judge-fehler: {e}]")

    parsed = _parse_verdict(raw)
    if parsed is None:
        return DriftVerdict(phase_name, aligned=True, drift="[unparsbar — konservativ aligned]")

    return DriftVerdict(
        phase=phase_name,
        aligned=bool(parsed.get("aligned", True)),
        drift=str(parsed.get("drift", "")).strip(),
    )


def _parse_verdict(raw: str) -> dict | None:
    if not raw:
        return None
    raw = re.sub(r"```(?:json)?\n?", "", raw)
    raw = re.sub(r"```\n?", "", raw)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
