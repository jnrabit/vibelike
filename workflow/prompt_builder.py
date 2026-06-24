"""
Prompt building utilities for workflow phases.

Centrizes prompt templates and builders to avoid duplication
in WorkflowAgent and enable consistent formatting.
"""

import json
from typing import Dict


# ═══════════════════════════════════════════════════════════════════
# Briefing Prompts
# ═══════════════════════════════════════════════════════════════════

BRIEFING_FRAMINGS = {
    "IMPLEMENTATION": {
        "role": """Du bist ein erfahrener Python-Architect und Code-Reviewer.
Deine Aufgabe: Analysiere die GIVEN task tief, verstehe die Projektstruktur,
und liefere einen ACTIONABLE Überblick für einen Junior-Developer, der die 
Implementierung starten wird.

GLIEDERUNG deiner Antwort:
## Zusammenfassung (Warum? Was? Wie viel Aufwand?)
## Betroffene Komponenten (Welche Module, Dateien, API-Grenzen?)
## Risikoanalyse (Fallstricke, Abhängigkeiten, Breaking Changes)
## Kurze Implementierungs-Skizze (Pseudo-Algorithmus, Reihenfolge der Schritte)

Halte Dich EXAKT an die Dateinamen oben. KEINE erfundenen Files!""",
        "body": "Gebe eine Briefing-Analyse (2-4 Absätze), die Junior für die Umsetzung vorbereitet."
    },
    "BUG_FIX": {
        "role": """Du bist ein erfahrener Debugger und Testplan-Schreiber.
Deine Aufgabe: Analysiere den Bug tiefgreifend.

GLIEDERUNG:
## Symptom & Root-Cause (Was ist kaputt? Warum?)
## Betroffene Code-Pfade (Welche Dateien, Funktionen?)
## Reproduktionsschritte (Wie kann man es sehen?)
## Fix-Strategie (Wo ändern? Welche Tests hinzufügen?)""",
        "body": "Gebe eine Briefing-Analyse für den Bug-Fix."
    },
    "REFACTOR": {
        "role": """Du bist ein Code-Quality-Expert mit Fokus auf Maintainability.
Deine Aufgabe: Analysiere den Refactoring-Bedarf.

GLIEDERUNG:
## Aktueller Zustand (Struktur, Anti-Patterns, Schmerzen)
## Ziel-Design (Wie soll es aussehen?)
## Migrations-Strategie (Schritte, Breaking-Change-Risiken)
## Regressions-Tests (Was muss getestet werden?)""",
        "body": "Gebe eine Briefing-Analyse für den Refactoring."
    },
    "ANALYSIS": {
        "role": """Du bist ein technischer Analyst und Dokumentation-Expert.
Deine Aufgabe: Analysiere das Code-Projekt vollständig und syntheisiere 
Erkenntnisse.

GLIEDERUNG:
## Erkenntnisse (Hauptlerning, Architektur-Pattern, Stärken/Schwächen)
## Struktur-Übersicht (Was tut jedes Modul? Wie hängen sie zusammen?)
## Technische Schulden (Was sollte refaktoriert werden?)
## Empfehlungen (Prioritäten, Roadmap-Vorschläge)""",
        "body": "Gebe eine tiefe Analyse des Projektcodes."
    },
    "EXPLAIN": {
        "role": """Du bist ein Technical Writer und Educationist.
Deine Aufgabe: Erkläre das Konzept/die Codesektion verständlich.

GLIEDERUNG:
## Zusammenfassung (Kurz: Was ist das?)
## Deep-Dive (Wie funktioniert es? Warum so?)
## Praktische Beispiele (Wo wird es verwendet?)
## Weitere Ressourcen (Verwandte Konzepte)""",
        "body": "Gebe eine verständliche Erklärung."
    }
}


def get_briefing_framing(task_type: str) -> Dict[str, str]:
    """
    Get role and body template for briefing phase.
    
    Args:
        task_type: One of IMPLEMENTATION, BUG_FIX, REFACTOR, ANALYSIS, EXPLAIN
        
    Returns:
        Dictionary with 'role' and 'body' keys
    """
    # Map EXPLAIN to ANALYSIS
    if task_type == "EXPLAIN":
        task_type = "ANALYSIS"
    
    return BRIEFING_FRAMINGS.get(task_type, BRIEFING_FRAMINGS["IMPLEMENTATION"])


def build_briefing_prompt(
    task: str,
    task_type: str,
    framing: Dict[str, str],
    project_info: Dict,
    code_overview: str,
    focused_files: str,
    authoritative_files: str,
    monolith: str = ""
) -> str:
    """
    Build complete briefing prompt with all context.
    
    Args:
        task: The task description
        task_type: Task type for framing
        framing: Role and body templates
        project_info: Project metadata
        code_overview: AST-based code overview
        focused_files: Full content of relevant files
        authoritative_files: List of all .py files
        monolith: Project monolith/architecture doc
        
    Returns:
        Complete prompt string
    """
    monolith_block = (
        f"\n{'='*70}\n"
        f"📜 PROJEKT-FUNDAMENT (MONOLITH):\n"
        f"{'='*70}\n"
        f"{monolith}\n"
    ) if monolith else ""
    
    prompt = f"""{framing['role']}

{'='*70}
🚨 VERBINDLICHE DATEILISTE — DAS SIND DIE EINZIGEN EXISTIERENDEN .py DATEIEN:
{'='*70}
{authoritative_files}

⚠️  Jeder andere Dateiname ist eine HALLUZINATION!
{'='*70}
{monolith_block}
AUFGABE:
{task}

PROJEKTSTRUKTUR (Metadata):
{json.dumps(project_info, indent=2, default=str)}

CODE-ÜBERSICHT (AST-extrahiert):
{code_overview}

VOLLER CODE relevanter Dateien:
{focused_files}

{'='*70}
🚨 ERINNERUNG — verwende NUR diese Dateinamen:
{authoritative_files}
{'='*70}

{framing['body']}

{'='*70}
🚨 Wenn du eine Datei nennst die nicht in der Liste oben steht — STOP, prüfe nochmal.
{'='*70}"""
    
    return prompt


# ═══════════════════════════════════════════════════════════════════
# Planning Prompts
# ═══════════════════════════════════════════════════════════════════

def build_planning_prompt(
    briefing: Dict,
    task_type: str
) -> str:
    """
    Build planning phase prompt.
    
    Args:
        briefing: Output from briefing phase
        task_type: Task type
        
    Returns:
        Planning prompt
    """
    analysis = briefing.get('analysis', '')
    task = briefing.get('task', '')
    
    prompt = f"""Du bist ein erfahrener Projekt-Planer.
Analysiere die bisherige BRIEFING-Analyse und erstelle einen detaillierten Implementierungsplan.

BRIEFING-ANALYSE:
{analysis}

TASK:
{task}

Gebe einen Schritt-für-Schritt-Plan mit:
1. Ordnung (Welche Dateien zuerst? Welche Abhängigkeiten?)
2. Pro Schritt: Pseudocode oder Pseudo-Änderungen
3. Verifikations-Steps (Tests, Checks)
4. Rollback-Plan (Wenn etwas schiefgeht)"""
    
    return prompt
