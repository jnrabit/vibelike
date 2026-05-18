#!/usr/bin/env python3
"""
Workflow Agent - 5-Phasen Feature Development mit Qwen2.5-Coder
================================================================

Orchestriert den kompletten Development Workflow:
1. BRIEFING  - Qwen analysiert Anfrage + Code
2. PLANNING  - Qwen schlägt Plan vor (User-Genehmigung)
3. EXECUTION - Qwen schreibt Code automatisch
4. VERIFY    - Tests laufen automatisch
5. COMMIT    - Git-Commit wird erstellt

Start: python workflow_agent.py
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "ossifikat"))

from terminal import QwenCoder
import subprocess


class WorkflowAgent:
    """5-Phasen Workflow Agent mit Qwen2.5-Coder."""

    def __init__(self):
        self.qwen = QwenCoder()
        self.root = Path(__file__).parent
        self.workflow_log = self.root / "logs" / "workflows.jsonl"
        self.workflow_log.parent.mkdir(parents=True, exist_ok=True)
        self.current_workflow = None

    # =========================================================================
    # PHASE 1: BRIEFING
    # =========================================================================

    def phase_briefing(self, task: str) -> dict:
        """Phase 1: Analyse der Aufgabe + Projektstruktur."""
        print("\n" + "="*70)
        print("PHASE 1: BRIEFING")
        print("="*70)
        print(f"\n📝 Aufgabe: {task}\n")

        # Sammle Projektinfo
        project_info = self._gather_project_info()

        # Qwen analysiert
        analysis_prompt = f"""Du bist ein Senior Code-Architekt. Analysiere diese Aufgabe und das Projekt:

AUFGABE:
{task}

PROJEKTSTRUKTUR:
{json.dumps(project_info, indent=2)}

Antworte mit einer Analyse:
1. Verstehen Sie die Aufgabe korrekt?
2. Welche Komponenten sind betroffen?
3. Wie passt es ins bestehende System?
4. Gibt es Abhängigkeiten oder Konflikte?
5. Welche Risiken sehen Sie?

Sei präzise und technisch."""

        print("[🤖 Qwen analysiert...]")
        analysis = self.qwen.generate(analysis_prompt, temperature=0.3)

        result = {
            "phase": "BRIEFING",
            "task": task,
            "timestamp": datetime.now().isoformat(),
            "analysis": analysis,
            "project_info": project_info
        }

        print(f"\n{analysis}\n")
        return result

    # =========================================================================
    # PHASE 2: PLANNING
    # =========================================================================

    def phase_planning(self, briefing: dict) -> dict:
        """Phase 2: Plan-Erstellung mit Qwen (User-Genehmigung erforderlich)."""
        print("\n" + "="*70)
        print("PHASE 2: PLANNING")
        print("="*70)

        plan_prompt = f"""Basierend auf dieser Analyse, erstelle einen detaillierten Implementierungsplan:

ANALYSE:
{briefing['analysis']}

Erstelle einen Plan mit:
1. Betroffene Dateien (mit Zeilen-Nummern wenn möglich)
2. Neue Funktionen/Klassen
3. Tests die geschrieben werden müssen
4. Dependencies/Imports
5. Risiken & Mitigationen
6. Estimated Lines of Code

Format: Strukturiert, aber lesbar für den User."""

        print("[🤖 Qwen erstellt Plan...]")
        plan = self.qwen.generate(plan_prompt, temperature=0.2)

        result = {
            "phase": "PLANNING",
            "plan": plan,
            "timestamp": datetime.now().isoformat(),
            "approved": False
        }

        print(f"\n{plan}\n")
        print("\n" + "-"*70)

        # User-Genehmigung
        while True:
            approval = input("\n👤 Plan ok? (ja/nein/änderungen): ").strip().lower()
            if approval in ["ja", "yes", "y"]:
                result["approved"] = True
                print("\n✅ Plan genehmigt! Starte Execution...\n")
                break
            elif approval in ["nein", "no", "n"]:
                print("\n❌ Plan nicht genehmigt. Bitte neue Aufgabe.\n")
                return None
            elif approval.startswith("änder"):
                changes = input("Welche Änderungen? ")
                # Qwen könnte hier iterativ den Plan anpassen
                print(f"[Info] Änderungswunsch notiert: {changes}")
            else:
                print("Bitte 'ja', 'nein' oder 'änderungen' eingeben.")

        return result

    # =========================================================================
    # PHASE 3: EXECUTION
    # =========================================================================

    def phase_execution(self, briefing: dict, plan: dict) -> dict:
        """Phase 3: Automatische Code-Implementierung."""
        print("\n" + "="*70)
        print("PHASE 3: EXECUTION")
        print("="*70)

        execution_prompt = f"""Du bist ein Experten-Code-Generator. Implementiere basierend auf diesem Plan:

ORIGINALAUFGABE:
{briefing['task']}

PLAN:
{plan['plan']}

ANFORDERUNGEN:
1. Schreib produktionsreife Code
2. Folge dem bestehenden Coding-Style
3. Inkludiere Error-Handling
4. Schreib Tests (pytest-Format)
5. Keine bestehende Logik zerstören
6. Kommentiere nur wenn nötig

Strukturiere die Antwort als:
## Datei: <path>
```python
<code>
```

## Tests: <path>
```python
<tests>
```

Generiere kompletten, lauffähigen Code."""

        print("[🤖 Qwen schreibt Code...]")
        code = self.qwen.generate(execution_prompt, temperature=0.1)

        result = {
            "phase": "EXECUTION",
            "code": code,
            "timestamp": datetime.now().isoformat(),
            "files_written": []
        }

        # Parse und schreib Code
        try:
            files = self._parse_and_write_code(code)
            result["files_written"] = files
            print(f"\n✅ Code geschrieben in {len(files)} Dateien")
            for f in files:
                print(f"   - {f}")
        except Exception as e:
            print(f"\n❌ Fehler beim Schreiben: {e}")
            result["error"] = str(e)

        print(f"\n{code}\n")
        return result

    # =========================================================================
    # PHASE 4: VERIFICATION
    # =========================================================================

    def phase_verification(self, execution: dict) -> dict:
        """Phase 4: Automatische Test-Verifikation."""
        print("\n" + "="*70)
        print("PHASE 4: VERIFICATION")
        print("="*70)

        print("[🧪 Führe Tests aus...]")

        # Laufe run_tests.py
        result = {
            "phase": "VERIFICATION",
            "timestamp": datetime.now().isoformat(),
            "tests_passed": False,
            "output": ""
        }

        try:
            cmd = [sys.executable, str(self.root / "run_tests.py")]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.root
            )

            result["output"] = proc.stdout
            result["return_code"] = proc.returncode

            # Parse Ergebnis
            if "ALL TESTS PASSED" in proc.stdout:
                result["tests_passed"] = True
                print("\n✅ ALLE TESTS BESTANDEN (100%)\n")
            else:
                print("\n⚠️ Tests mit Fehler:\n")
                print(proc.stdout[-500:])

        except Exception as e:
            result["error"] = str(e)
            print(f"\n❌ Test-Fehler: {e}")

        return result

    # =========================================================================
    # PHASE 5: COMMIT
    # =========================================================================

    def phase_commit(self, briefing: dict, execution: dict, verification: dict) -> dict:
        """Phase 5: Automatischer Git-Commit."""
        print("\n" + "="*70)
        print("PHASE 5: COMMIT")
        print("="*70)

        # Generiere Commit-Message mit Qwen
        commit_prompt = f"""Generiere eine präzise Git-Commit-Message für diese Änderung:

AUFGABE:
{briefing['task']}

ÄNDERUNGEN:
{json.dumps([f for f in execution.get('files_written', [])], indent=2)}

Format:
- Title (1 Zeile, max 70 Zeichen)
- Leerzeile
- Body (beschreib WHY, nicht WHAT)
- Bullet points für Highlights

Beispiel:
Add GitHub README harvester for Code-Vault

- Collects README files from trending repos
- Integrates with harvest_scheduler
- Adds 500+ documents per harvest run
- Handles API rate limits gracefully"""

        print("[🤖 Qwen erstellt Commit-Message...]")
        commit_msg = self.qwen.generate(commit_prompt, temperature=0.2)

        # Erstelle Commit
        result = {
            "phase": "COMMIT",
            "message": commit_msg,
            "timestamp": datetime.now().isoformat(),
            "committed": False
        }

        print(f"\n📝 Commit-Message:\n\n{commit_msg}\n")
        print("-"*70)

        # User-Bestätigung
        confirm = input("\n👤 Commit erstellen? (ja/nein): ").strip().lower()
        if confirm in ["ja", "yes", "y"]:
            try:
                # Git add all modified/new files
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=self.root,
                    capture_output=True,
                    check=True
                )

                # Git commit
                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    cwd=self.root,
                    capture_output=True,
                    check=True
                )

                result["committed"] = True
                print("\n✅ Commit erstellt!\n")
            except subprocess.CalledProcessError as e:
                result["error"] = str(e)
                print(f"\n❌ Git-Fehler: {e}")
        else:
            print("\n⏭️ Commit übersprungen.\n")

        return result

    # =========================================================================
    # HILFSMETHODEN
    # =========================================================================

    def _gather_project_info(self) -> dict:
        """Sammle Projektstruktur-Info."""
        return {
            "root": str(self.root),
            "main_files": list((self.root).glob("*.py"))[:10],
            "has_tests": (self.root / "tests").exists(),
            "has_git": (self.root / ".git").exists(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        }

    def _parse_and_write_code(self, code: str) -> list:
        """Parse Code-Output und schreib Dateien."""
        files_written = []

        # Einfacher Parser für "## Datei: <path>" Blöcke
        lines = code.split("\n")
        current_file = None
        current_code = []
        in_code_block = False

        for line in lines:
            if line.startswith("## Datei:") or line.startswith("## File:"):
                # Schreib vorherige Datei
                if current_file and current_code:
                    filepath = self.root / current_file.strip()
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    with open(filepath, "w") as f:
                        f.write("\n".join(current_code))
                    files_written.append(str(filepath))

                # Neue Datei
                current_file = line.replace("## Datei:", "").replace("## File:", "").strip()
                current_code = []
                in_code_block = False

            elif line.startswith("```"):
                in_code_block = not in_code_block

            elif in_code_block and current_file:
                current_code.append(line)

        # Schreib letzte Datei
        if current_file and current_code:
            filepath = self.root / current_file
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w") as f:
                f.write("\n".join(current_code))
            files_written.append(str(filepath))

        return files_written

    # =========================================================================
    # MAIN WORKFLOW
    # =========================================================================

    def run_workflow(self, task: str) -> dict:
        """Laufe alle 5 Phasen durch."""
        self.current_workflow = {
            "id": datetime.now().strftime("%Y%m%d-%H%M%S"),
            "task": task,
            "phases": {}
        }

        # Phase 1
        briefing = self.phase_briefing(task)
        self.current_workflow["phases"]["briefing"] = briefing

        # Phase 2
        planning = self.phase_planning(briefing)
        if not planning or not planning.get("approved"):
            print("\n❌ Workflow abgebrochen.\n")
            return self.current_workflow
        self.current_workflow["phases"]["planning"] = planning

        # Phase 3
        execution = self.phase_execution(briefing, planning)
        self.current_workflow["phases"]["execution"] = execution

        # Phase 4
        verification = self.phase_verification(execution)
        self.current_workflow["phases"]["verification"] = verification

        if not verification.get("tests_passed"):
            print("\n⚠️ Tests nicht alle bestanden. Überprüfe manuell.\n")

        # Phase 5
        commit = self.phase_commit(briefing, execution, verification)
        self.current_workflow["phases"]["commit"] = commit

        # Log
        with open(self.workflow_log, "a") as f:
            f.write(json.dumps(self.current_workflow) + "\n")

        print("\n" + "="*70)
        print("✅ WORKFLOW ABGESCHLOSSEN")
        print("="*70 + "\n")

        return self.current_workflow


def main():
    """CLI Interface."""
    print("\n" + "="*70)
    print("VIBELIKE WORKFLOW AGENT - 5-Phasen Development mit Qwen2.5-Coder")
    print("="*70)

    agent = WorkflowAgent()

    # Beispiel-Aufgaben
    examples = [
        "1. GitHub README Harvester (sammelt READMEs von Top Python-Repos)",
        "2. Stack Overflow Harvester (sammelt Q&A zu Programmierung)",
        "3. Deine eigene Aufgabe eingeben",
    ]

    print("\nBeispiel-Aufgaben:")
    for ex in examples:
        print(f"  {ex}")

    task = input("\n📝 Aufgabe eingeben: ").strip()

    if not task:
        print("❌ Keine Aufgabe eingegeben.")
        return

    # Workflow starten
    workflow = agent.run_workflow(task)


if __name__ == "__main__":
    main()
