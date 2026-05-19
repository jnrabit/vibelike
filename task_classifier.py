"""
task_classifier.py -- Phase 0: Task-Typ erkennen vor Workflow-Routing.

Verhindert die "alles ist eine Implementation"-Halluzination:
'analysiere /vibelike' soll NICHT in die Plan/Execute-Pipeline gezwungen werden.
"""

from __future__ import annotations

import json
import re
from typing import Optional


TASK_TYPES = {
    "ANALYSIS": {
        "label": "Analyse / Untersuchung",
        "desc": "Code/Projekt anschauen, Befunde liefern. KEINE Code-Aenderung.",
        "examples": [
            "analysiere /vibelike",
            "was tut workflow_agent.py?",
            "schau dir die validator-architektur an",
        ],
    },
    "IMPLEMENTATION": {
        "label": "Implementation / neues Feature",
        "desc": "Neue Funktionalitaet bauen. Code wird geschrieben.",
        "examples": [
            "fuege XSS-Check zu validator2 hinzu",
            "implementiere eine retry-policy fuer ollama-calls",
            "neue klasse SecurityScanner anlegen",
        ],
    },
    "BUG_FIX": {
        "label": "Bug-Fix",
        "desc": "Konkreten bekannten Fehler beheben.",
        "examples": [
            "PosixPath JSON-error in phase_briefing fixen",
            "validator wirft TypeError bei leerem plan",
            "fix import error in static_validator",
        ],
    },
    "REFACTOR": {
        "label": "Refactoring",
        "desc": "Code umstrukturieren, gleiches Verhalten. Kein neues Feature.",
        "examples": [
            "phase_execution in mehrere methoden splitten",
            "extrahiere die ollama-config in eigene klasse",
            "alle prints durch logging ersetzen",
        ],
    },
    "EXPLAIN": {
        "label": "Erklaerung",
        "desc": "Code/Konzept erklaeren. Reine Wissensfrage.",
        "examples": [
            "wie funktioniert chaos retrieval?",
            "erklaer mir den ossifikat audit",
            "was macht der unified ast visitor?",
        ],
    },
}


class TaskClassifier:
    """Klassifiziert User-Tasks in einen der TASK_TYPES.

    Nutzt das Reasoning-Modell (kleines, schnelles Klassifikator-Setup).
    """

    def __init__(self, qwen):
        """qwen: QwenCoder-Instanz (am besten das analyzer_qwen = Reasoning-Modell)."""
        self.qwen = qwen

    def classify(self, task: str, project_files: list[str] | None = None) -> dict:
        """Klassifiziert task in einen TASK_TYPES-Key.

        Returns:
            {
                "type": "ANALYSIS" | "IMPLEMENTATION" | ...,
                "confidence": 0.0..1.0,
                "reasoning": "kurze begruendung",
            }
        """
        types_list = "\n".join(
            f"  - {key}: {meta['desc']}" for key, meta in TASK_TYPES.items()
        )
        examples_block = "\n".join(
            f"  {key}: {', '.join(meta['examples'][:2])}"
            for key, meta in TASK_TYPES.items()
        )

        files_hint = ""
        if project_files:
            files_hint = f"\nPROJEKT-DATEIEN (Top 10):\n  {', '.join(project_files[:10])}"

        prompt = f"""Du bist ein Task-Klassifikator. Ordne die folgende Anfrage in GENAU eine der Kategorien ein.

KATEGORIEN:
{types_list}

BEISPIELE PRO KATEGORIE:
{examples_block}
{files_hint}

ANFRAGE:
{task}

Antworte AUSSCHLIESSLICH mit gueltigem JSON in genau diesem Format:
{{
  "type": "ANALYSIS",
  "confidence": 0.85,
  "reasoning": "Ein-Satz-Begruendung warum diese Kategorie"
}}

WICHTIG:
- type MUSS einer dieser Werte sein: ANALYSIS, IMPLEMENTATION, BUG_FIX, REFACTOR, EXPLAIN
- Kein Text vor oder nach dem JSON
- confidence ist 0.0 bis 1.0 (wie sicher bist du dir)"""

        raw = self.qwen.generate(prompt, temperature=0.1, stream=False)
        parsed = self._parse_json_response(raw)

        # Fallback bei Parse-Fehler
        if not parsed or parsed.get("type") not in TASK_TYPES:
            return {
                "type": "IMPLEMENTATION",  # konservativer Default
                "confidence": 0.3,
                "reasoning": f"Klassifikator-Parse fehlgeschlagen, Default. Raw: {raw[:200]}",
                "raw": raw,
            }

        return parsed

    def _parse_json_response(self, raw: str) -> Optional[dict]:
        """Robustes JSON-Parsing -- entfernt Markdown-Fences, sucht JSON-Block."""
        if not raw:
            return None

        # Entferne Markdown-Code-Fences
        raw = re.sub(r"```(?:json)?\n?", "", raw)
        raw = re.sub(r"```\n?", "", raw)

        # Finde JSON-Block (greedy zwischen erstem { und letztem })
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None

        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def confirm_classification(classification: dict) -> str:
    """Zeigt Klassifikation, laesst User bestaetigen oder korrigieren.

    Returns: bestaetigter task_type (key aus TASK_TYPES)
    """
    task_type = classification["type"]
    confidence = classification.get("confidence", 0)
    reasoning = classification.get("reasoning", "")

    print("\n" + "─"*70)
    print(f"🎯 TASK-KLASSIFIKATION")
    print("─"*70)
    print(f"  Erkannt als: {task_type} ({TASK_TYPES[task_type]['label']})")
    print(f"  Confidence:  {confidence:.0%}")
    print(f"  Begruendung: {reasoning}")
    print("─"*70)

    while True:
        answer = input(f"\n👤 Passt '{task_type}'? (ja/nein/list): ").strip().lower()

        if answer in ("ja", "yes", "y", ""):
            return task_type

        if answer in ("list", "l", "?"):
            print("\nVerfuegbare Task-Typen:")
            for i, (key, meta) in enumerate(TASK_TYPES.items(), 1):
                print(f"  {i}. {key:15s} -- {meta['label']}")
            continue

        if answer in ("nein", "no", "n"):
            print("\nVerfuegbare Task-Typen:")
            keys = list(TASK_TYPES.keys())
            for i, key in enumerate(keys, 1):
                print(f"  {i}. {key:15s} -- {TASK_TYPES[key]['label']}")
            while True:
                pick = input("\n  Welcher Typ? (Nummer oder Key): ").strip().upper()
                if pick.isdigit() and 1 <= int(pick) <= len(keys):
                    return keys[int(pick) - 1]
                if pick in TASK_TYPES:
                    return pick
                print("  Ungueltige Eingabe.")

        print("  Bitte 'ja', 'nein' oder 'list' eingeben.")
