#!/usr/bin/env python3
"""
Workflow Agent - 6-Phasen Feature Development mit Qwen2.5-Coder
================================================================

Orchestriert den kompletten Development Workflow:
1.  BRIEFING            - Qwen analysiert Anfrage + Code   (parallel validiert)
2a. PLANNING-STRATEGIE  - Allgemeines Vorgehen             (parallel validiert)
2b. PLANNING-DETAIL     - Konkrete Durchführung            (parallel validiert)
3.  EXECUTION           - Code-Gen + Dry-Run-Diff          (parallel code-reviewt)
4.  VERIFY              - Tests laufen automatisch
4b. FAILURE-ANALYSIS    - Bei Test-Fail: Root-Cause →      Loop zurück zu Phase 1
5.  COMMIT              - Per Teilschritt aus Detail-Plan  ein eigener Git-Commit

Plan-Phasen (1, 2a, 2b) bekommen parallel einen kritischen Validator.
Execution bekommt parallel einen Code-Reviewer + Dry-Run-Diff-Anzeige.
Test-Fail → Qwen formuliert Korrektur-Task → neue Iteration (max 3).
Commit-Phase splittet Änderungen in logische Teilschritte (Per-Step-Commits).

Start: python workflow_agent.py
"""

import os
import sys
import json
import subprocess
import concurrent.futures
from pathlib import Path
from datetime import datetime

# Imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "ossifikat"))


class WorkflowAgent:
    """6-Phasen Workflow Agent mit Qwen2.5-Coder + paralleler Phase-Validierung."""

    def __init__(self):
        # Import QwenCoder locally to avoid circular imports
        from terminal import QwenCoder

        self.qwen = QwenCoder()
        # Separate QwenCoder instance for parallel validator (own HTTP session)
        self.validator_qwen = QwenCoder()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

        self.root = Path(__file__).parent
        self.workflow_log = self.root / "logs" / "workflows.jsonl"
        self.workflow_log.parent.mkdir(parents=True, exist_ok=True)
        self.current_workflow = None

    # =========================================================================
    # PARALLELE VALIDIERUNG (Critic)
    # =========================================================================

    def _start_validation(self, phase_name: str, output: str, context: str) -> concurrent.futures.Future:
        """Startet Validator im Hintergrund. Gibt Future zurück (nicht blockierend)."""
        def _run() -> str:
            validator_prompt = f"""Du bist ein KRITISCHER REVIEWER. Validiere unabhängig diese {phase_name}-Ausgabe.

KONTEXT (Originalaufgabe / Vorphase):
{context}

ZU VALIDIERENDE AUSGABE:
{output}

Prüfe diese Punkte ehrlich und knapp:
1. VOLLSTÄNDIGKEIT  - Fehlt etwas Wichtiges? Lücken im Reasoning?
2. WIDERSPRÜCHE    - Inkonsistenzen oder Annahmen, die kollidieren?
3. RISIKEN         - Wurde an Edge Cases gedacht? Was geht schief?
4. ANNAHMEN        - Unausgesprochene Annahmen, die problematisch sein könnten?
5. ALTERNATIVEN    - Wurde ein besserer Ansatz übersehen?
6. AMPEL           - 🟢 ok / 🟡 mit Vorbehalt / 🔴 Stop, neu denken

Sei knapp und KRITISCH. Keine Bestätigungs-Floskeln, kein Lob.
Wenn alles ok ist: 1 Satz + 🟢. Sonst: konkrete Punkte."""
            return self.validator_qwen.generate(validator_prompt, temperature=0.4)

        return self._executor.submit(_run)

    def _render_validation(self, validation_future: concurrent.futures.Future) -> str:
        """Holt Validator-Ergebnis ab und rendert es."""
        print("\n[🔍 Validator läuft parallel...]")
        try:
            result = validation_future.result(timeout=300)
        except Exception as e:
            result = f"[Validator-Fehler: {e}]"
        print("\n" + "─"*70)
        print("🔍 PARALLELE VALIDIERUNG (unabhängiger Critic)")
        print("─"*70)
        print(result)
        print("─"*70)
        return result

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
{json.dumps(project_info, indent=2, default=str)}

Antworte mit einer Analyse:
1. Verstehen Sie die Aufgabe korrekt?
2. Welche Komponenten sind betroffen?
3. Wie passt es ins bestehende System?
4. Gibt es Abhängigkeiten oder Konflikte?
5. Welche Risiken sehen Sie?

Sei präzise und technisch."""

        print("[🤖 Qwen analysiert...]\n")
        analysis = self.qwen.generate(analysis_prompt, temperature=0.3, stream=True)

        # Parallel: Validator startet, nachdem Stream fertig ist
        validation_future = self._start_validation("BRIEFING", analysis, f"AUFGABE: {task}")

        # Validation einsammeln (User-Lesezeit überlappt mit Validator-Run)
        validation = self._render_validation(validation_future)

        result = {
            "phase": "BRIEFING",
            "task": task,
            "timestamp": datetime.now().isoformat(),
            "analysis": analysis,
            "validation": validation,
            "project_info": project_info
        }
        return result

    # =========================================================================
    # PHASE 2A: PLANNING (STRATEGIE / ALLGEMEINES VORGEHEN)
    # =========================================================================

    def phase_planning_strategy(self, briefing: dict) -> dict:
        """Phase 2a: Strategische Planung - allgemeines Vorgehen (User-Genehmigung)."""
        print("\n" + "="*70)
        print("PHASE 2A: PLANNING - STRATEGIE (Allgemeines Vorgehen)")
        print("="*70)

        strategy_prompt = f"""Du bist ein Senior Software-Architekt. Erstelle eine STRATEGISCHE Planung für die Aufgabe.

ANALYSE:
{briefing['analysis']}

Diese Phase ist HIGH-LEVEL - noch KEINE konkreten Dateien/Funktionen.

Beantworte:
1. ANSATZ: Welche grundsätzliche Strategie? (z.B. neuer Service, Erweiterung, Refactoring)
2. ARCHITEKTUR: Welche Komponenten/Pattern verwenden? (z.B. Plugin-System, Adapter, Decorator)
3. ALTERNATIVEN: Welche Alternativen gibt es? Warum diese Wahl?
4. TRADE-OFFS: Vor- und Nachteile des gewählten Ansatzes
5. ABHÄNGIGKEITEN: Welche externen Libraries/APIs nötig?
6. RISIKEN: Was könnte schiefgehen? (technisch & inhaltlich)
7. AUFWAND: Grob - Stunden? Tage? Wochen?

Format: Strukturiert, aber NICHT zu detailliert. Konzentriere dich auf das WAS und WARUM, noch nicht auf das WIE."""

        print("[🤖 Qwen entwickelt Strategie...]\n")
        strategy = self.qwen.generate(strategy_prompt, temperature=0.3, stream=True)

        # Parallel: Validator startet
        validation_future = self._start_validation(
            "PLANNING-STRATEGIE",
            strategy,
            f"BRIEFING-ANALYSE:\n{briefing['analysis']}"
        )

        # Validation einsammeln
        validation = self._render_validation(validation_future)

        result = {
            "phase": "PLANNING_STRATEGY",
            "strategy": strategy,
            "validation": validation,
            "timestamp": datetime.now().isoformat(),
            "approved": False
        }

        print("\n" + "-"*70)

        # User-Genehmigung der Strategie
        while True:
            approval = input("\n👤 Strategie ok? (ja/nein/änderungen): ").strip().lower()
            if approval in ["ja", "yes", "y"]:
                result["approved"] = True
                print("\n✅ Strategie genehmigt! Starte Detail-Planung...\n")
                break
            elif approval in ["nein", "no", "n"]:
                print("\n❌ Strategie nicht genehmigt. Workflow abgebrochen.\n")
                return None
            elif approval.startswith("änder"):
                changes = input("Welche Änderungen an der Strategie? ")
                print(f"[Info] Änderungswunsch notiert: {changes}")
                result["change_request"] = changes
            else:
                print("Bitte 'ja', 'nein' oder 'änderungen' eingeben.")

        return result

    # =========================================================================
    # PHASE 2B: PLANNING (DETAILPLAN / KONKRETE DURCHFÜHRUNG)
    # =========================================================================

    def phase_planning_detailed(self, briefing: dict, strategy: dict) -> dict:
        """Phase 2b: Detail-Planung - konkrete Durchführung (User-Genehmigung)."""
        print("\n" + "="*70)
        print("PHASE 2B: PLANNING - DETAILPLAN (Konkrete Durchführung)")
        print("="*70)

        detail_prompt = f"""Du bist ein Senior Software Engineer. Erstelle den DETAILLIERTEN Durchführungsplan
basierend auf der genehmigten Strategie.

ORIGINALAUFGABE:
{briefing['task']}

GENEHMIGTE STRATEGIE:
{strategy['strategy']}

Diese Phase ist KONKRET - jetzt das WIE.

Erstelle einen Plan mit:
1. BETROFFENE DATEIEN (exakte Pfade, ggf. mit Zeilen-Nummern)
2. NEUE DATEIEN (mit Begründung warum nötig)
3. FUNKTIONEN/KLASSEN (Signaturen, Parameter, Return-Types)
4. CODE-FLOW (Schritt-für-Schritt was passieren soll)
5. TESTS (Test-Funktionen mit Setup/Teardown, Edge Cases)
6. IMPORTS (welche neuen Imports werden gebraucht)
7. INTEGRATION (wie wird in bestehenden Code eingebunden)
8. ROLLBACK-PLAN (wie kann man die Änderung rückgängig machen)
9. ESTIMATED LINES OF CODE (pro Datei)

Format: Strukturierter Plan, lesbar wie eine TODO-Liste. Sei präzise."""

        print("[🤖 Qwen erstellt Detail-Plan...]\n")
        plan = self.qwen.generate(detail_prompt, temperature=0.2, stream=True)

        # Parallel: Validator startet
        validation_future = self._start_validation(
            "PLANNING-DETAIL",
            plan,
            f"AUFGABE: {briefing['task']}\n\nGENEHMIGTE STRATEGIE:\n{strategy['strategy']}"
        )

        # Validation einsammeln
        validation = self._render_validation(validation_future)

        result = {
            "phase": "PLANNING_DETAILED",
            "plan": plan,
            "validation": validation,
            "strategy_ref": strategy.get("strategy", ""),
            "timestamp": datetime.now().isoformat(),
            "approved": False
        }

        print("\n" + "-"*70)

        # User-Genehmigung des Detail-Plans
        while True:
            approval = input("\n👤 Detail-Plan ok? (ja/nein/änderungen): ").strip().lower()
            if approval in ["ja", "yes", "y"]:
                result["approved"] = True
                print("\n✅ Detail-Plan genehmigt! Starte Execution...\n")
                break
            elif approval in ["nein", "no", "n"]:
                print("\n❌ Detail-Plan nicht genehmigt. Workflow abgebrochen.\n")
                return None
            elif approval.startswith("änder"):
                changes = input("Welche Änderungen am Detail-Plan? ")
                print(f"[Info] Änderungswunsch notiert: {changes}")
                result["change_request"] = changes
            else:
                print("Bitte 'ja', 'nein' oder 'änderungen' eingeben.")

        return result

    # Backwards-compat alias
    def phase_planning(self, briefing: dict) -> dict:
        """Legacy method - delegates to two-phase planning."""
        strategy = self.phase_planning_strategy(briefing)
        if not strategy or not strategy.get("approved"):
            return None
        return self.phase_planning_detailed(briefing, strategy)

    # =========================================================================
    # PHASE 3: EXECUTION
    # =========================================================================

    def phase_execution(self, briefing: dict, plan: dict) -> dict:
        """Phase 3: Code-Generierung mit Dry-Run + parallelem Code-Reviewer + User-Gate."""
        print("\n" + "="*70)
        print("PHASE 3: EXECUTION (Dry-Run + Code-Review)")
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

        print("[🤖 Qwen schreibt Code...]\n")
        code = self.qwen.generate(execution_prompt, temperature=0.1, stream=True)

        # Parse OHNE zu schreiben (Dry-Run)
        planned_changes = self._parse_code(code)

        # Parallel: Code-Reviewer startet (nach Stream-Ende)
        review_future = self._start_code_review(code, plan, briefing['task'])

        # Strukturierter Diff
        print(f"\n📦 GEPLANTE ÄNDERUNGEN ({len(planned_changes)} Dateien):")
        print("="*70)
        self._show_diff(planned_changes, full=False)

        # Code-Review einsammeln
        review = self._render_code_review(review_future)

        result = {
            "phase": "EXECUTION",
            "code": code,
            "planned_changes": [{"path": c["path"], "exists": c["exists"], "lines": len(c["content"].splitlines())} for c in planned_changes],
            "code_review": review,
            "timestamp": datetime.now().isoformat(),
            "files_written": [],
            "approved": False,
        }

        # User-Gate vor dem Schreiben
        print("\n" + "-"*70)
        while True:
            approval = input("\n👤 Änderungen anwenden? (ja/nein/diff/code): ").strip().lower()
            if approval in ["ja", "yes", "y"]:
                files = self._write_code(planned_changes)
                result["files_written"] = files
                result["approved"] = True
                print(f"\n✅ Code geschrieben in {len(files)} Dateien:")
                for f in files:
                    print(f"   - {f}")
                break
            elif approval in ["nein", "no", "n"]:
                print("\n❌ Execution abgebrochen, keine Files geschrieben.\n")
                return result
            elif approval == "diff":
                print("\n📦 KOMPLETTER DIFF:")
                self._show_diff(planned_changes, full=True)
            elif approval == "code":
                print(f"\n📝 KOMPLETTER CODE:\n{code}\n")
            else:
                print("Bitte 'ja', 'nein', 'diff' (volldiff) oder 'code' (vollcode) eingeben.")

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
            "output": "",
            "stderr": "",
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
            result["stderr"] = proc.stderr
            result["return_code"] = proc.returncode

            # Parse Ergebnis
            if "ALL TESTS PASSED" in proc.stdout:
                result["tests_passed"] = True
                print("\n✅ ALLE TESTS BESTANDEN (100%)\n")
            else:
                print("\n⚠️ Tests mit Fehler:\n")
                print(proc.stdout[-1500:])
                if proc.stderr:
                    print("\nSTDERR:")
                    print(proc.stderr[-500:])

        except Exception as e:
            result["error"] = str(e)
            print(f"\n❌ Test-Fehler: {e}")

        return result

    def phase_failure_analysis(self, briefing: dict, execution: dict, verification: dict) -> dict:
        """Phase 4b: Nach Test-Fail Root-Cause analysieren und neuen Task formulieren."""
        print("\n" + "="*70)
        print("PHASE 4B: FAILURE ANALYSIS")
        print("="*70)

        files_changed = execution.get("files_written", []) or [
            c["path"] for c in execution.get("planned_changes", [])
        ]

        analysis_prompt = f"""Du bist ein Senior Debug-Engineer. Die Tests sind nach folgender Änderung gefehlschlagen.
Analysiere den Root Cause und formuliere eine KORRIGIERENDE FOLGE-AUFGABE.

URSPRÜNGLICHE AUFGABE:
{briefing['task']}

GEÄNDERTE DATEIEN:
{json.dumps(files_changed, indent=2, default=str)}

TEST-OUTPUT (letzte Zeilen):
{verification.get('output', '')[-2000:]}

STDERR:
{verification.get('stderr', '')[-1000:]}

Liefere:
1. ROOT CAUSE        - Was ist die wahre Ursache? (nicht nur Symptom)
2. WIDERSPRUCH       - War der ursprüngliche Plan falsch oder die Umsetzung?
3. KORREKTUR-AUFGABE - 1-2 Sätze für die nächste Iteration. So formuliert,
   dass sie als neue Workflow-Aufgabe gestartet werden kann.
   Format: "Fix: <konkrete Anweisung>"
4. AMPEL             - 🟢 trivial fixbar / 🟡 brauchen Re-Plan / 🔴 Konzept neu denken

Sei knapp, kein Fließtext."""

        print("[🤖 Qwen analysiert Test-Failure...]\n")
        analysis = self.qwen.generate(analysis_prompt, temperature=0.3, stream=True)

        # Korrektur-Aufgabe extrahieren (suche nach "Fix:" Zeile)
        followup_task = None
        for line in analysis.splitlines():
            stripped = line.strip().lstrip("0123456789.-) ")
            if stripped.lower().startswith("fix:") or stripped.lower().startswith("korrektur:"):
                followup_task = stripped.split(":", 1)[1].strip()
                break

        if not followup_task:
            # Fallback: ganzen Analyse-Text als Task verwenden
            followup_task = f"Fix Test-Failure aus vorheriger Iteration:\n{analysis[:500]}"

        result = {
            "phase": "FAILURE_ANALYSIS",
            "analysis": analysis,
            "followup_task": followup_task,
            "timestamp": datetime.now().isoformat(),
        }

        print("\n" + "-"*70)
        print(f"\n🔁 Vorgeschlagene Folge-Aufgabe:\n  {followup_task}\n")

        return result

    # =========================================================================
    # PHASE 5: COMMIT
    # =========================================================================

    def phase_commit(self, briefing: dict, execution: dict, verification: dict) -> dict:
        """Phase 5: Per-Teilschritt Git-Commits aus Detail-Plan."""
        print("\n" + "="*70)
        print("PHASE 5: COMMIT (Per-Teilschritt)")
        print("="*70)

        files_changed = execution.get("files_written", [])
        if not files_changed:
            print("\n⚠️ Keine Files geändert, nichts zu committen.\n")
            return {"phase": "COMMIT", "committed": False, "steps": []}

        # Detail-Plan aus aktuellem Workflow lesen
        detail = (self.current_workflow or {}).get("phases", {}).get("planning_detailed", {})
        plan_text = detail.get("plan", "")

        # Qwen in Teilschritte aufteilen lassen
        grouping_prompt = f"""Gruppe diese Datei-Änderungen in LOGISCHE TEILSCHRITTE für separate Git-Commits.

ORIGINALAUFGABE:
{briefing['task']}

DETAIL-PLAN (Soll-Sequenz):
{plan_text[:3000]}

TATSÄCHLICH GEÄNDERTE DATEIEN:
{json.dumps(files_changed, indent=2, default=str)}

Antworte AUSSCHLIESSLICH mit gültigem JSON (kein Markdown-Block, kein Text drumherum):
[
  {{
    "step":  "Kurzer Step-Name",
    "files": ["absoluter/oder/relativer/pfad", ...],
    "title": "Commit-Title (max 70 Zeichen, imperativ)",
    "body":  "Warum diese Änderung. 1-3 Sätze."
  }},
  ...
]

Regeln:
- Mindestens 1, maximal 5 Commits
- Jede Datei in GENAU einem Step
- Reihenfolge = sinnvoller Abhängigkeits-Order
- Tests gehören zum Step, der die Logik einführt (nicht eigener Commit)"""

        print("[🤖 Qwen gruppiert Änderungen in Teilschritte...]")
        grouping_raw = self.qwen.generate(grouping_prompt, temperature=0.1)
        steps = self._parse_commit_groups(grouping_raw, files_changed)

        print(f"\n📦 {len(steps)} Teilschritt(e) geplant:\n")
        for i, s in enumerate(steps, 1):
            print(f"  {i}. {s['title']}")
            for f in s["files"]:
                rel = Path(f).relative_to(self.root) if Path(f).is_relative_to(self.root) else f
                print(f"       - {rel}")
        print()

        result = {
            "phase": "COMMIT",
            "steps": [],
            "timestamp": datetime.now().isoformat(),
            "committed": False,
        }

        # Pro Step: User-Gate, dann committen
        confirm = input("\n👤 Per-Step-Commits durchführen? (ja/nein/einer): ").strip().lower()
        if confirm in ["nein", "no", "n"]:
            print("\n⏭️ Commits übersprungen.\n")
            return result

        # "einer" Fallback: alles als 1 Commit
        if confirm == "einer":
            steps = [{
                "step": "Combined",
                "files": files_changed,
                "title": steps[0]["title"] if steps else briefing['task'][:60],
                "body": "\n".join(f"- {s['title']}" for s in steps) if steps else "",
            }]

        # Reset staging area, dann pro Step add+commit
        try:
            subprocess.run(["git", "reset", "HEAD", "--"], cwd=self.root, capture_output=True, check=False)
        except Exception:
            pass

        for i, step in enumerate(steps, 1):
            print(f"\n[{i}/{len(steps)}] {step['title']}")
            message = f"{step['title']}\n\n{step['body']}".strip()

            try:
                # Stage NUR die Files dieses Steps
                for f in step["files"]:
                    subprocess.run(["git", "add", "--", f], cwd=self.root, capture_output=True, check=True)

                # Commit
                proc = subprocess.run(
                    ["git", "commit", "-m", message],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode == 0:
                    # Hash holen
                    hash_proc = subprocess.run(
                        ["git", "rev-parse", "--short", "HEAD"],
                        cwd=self.root, capture_output=True, text=True, check=False,
                    )
                    commit_hash = hash_proc.stdout.strip()
                    print(f"   ✓ {commit_hash} — {step['title']}")
                    result["steps"].append({
                        "step": step["step"],
                        "title": step["title"],
                        "hash": commit_hash,
                        "files": step["files"],
                    })
                else:
                    print(f"   ⚠️ Commit übersprungen: {proc.stderr.strip() or 'nichts zu committen'}")
                    result["steps"].append({
                        "step": step["step"],
                        "title": step["title"],
                        "skipped": True,
                        "reason": proc.stderr.strip(),
                    })
            except subprocess.CalledProcessError as e:
                print(f"   ✗ Git-Fehler: {e}")
                result["steps"].append({"step": step["step"], "error": str(e)})

        result["committed"] = any("hash" in s for s in result["steps"])
        if result["committed"]:
            print(f"\n✅ {sum(1 for s in result['steps'] if 'hash' in s)} Commit(s) erstellt.\n")
        return result

    def _parse_commit_groups(self, raw: str, all_files: list) -> list:
        """Parse Qwen-JSON-Output für Commit-Steps. Fallback: 1 Commit mit allen Files."""
        import re

        # Code-Fences abziehen falls Qwen welche dranklebt
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
            cleaned = re.sub(r"\n```\s*$", "", cleaned)

        # JSON-Array suchen
        match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if not match:
            return [self._fallback_commit_step(all_files)]

        try:
            steps = json.loads(match.group(0))
        except json.JSONDecodeError:
            return [self._fallback_commit_step(all_files)]

        # Validierung + Normalisierung
        all_files_set = set(all_files)
        seen_files = set()
        valid_steps = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            files = [f for f in s.get("files", []) if f in all_files_set and f not in seen_files]
            if not files:
                continue
            seen_files.update(files)
            valid_steps.append({
                "step":  s.get("step", "Step"),
                "files": files,
                "title": (s.get("title") or "chore: update")[:70],
                "body":  s.get("body", "").strip(),
            })

        # Falls Files übrigbleiben (Qwen vergessen): Catchall-Step
        leftover = [f for f in all_files if f not in seen_files]
        if leftover:
            valid_steps.append({
                "step":  "remaining",
                "files": leftover,
                "title": "chore: remaining changes",
                "body":  "Files, die nicht von Qwen gruppiert wurden.",
            })

        return valid_steps or [self._fallback_commit_step(all_files)]

    def _fallback_commit_step(self, files: list) -> dict:
        """Fallback wenn Qwen-Gruppierung fehlschlägt: 1 Commit mit allem."""
        return {
            "step":  "all",
            "files": files,
            "title": "chore: workflow changes",
            "body":  "Combined commit (Qwen-Gruppierung fehlgeschlagen).",
        }

    # =========================================================================
    # HILFSMETHODEN
    # =========================================================================

    def _gather_project_info(self) -> dict:
        """Sammle Projektstruktur-Info (alle Pfade als str für JSON-Serialisierung)."""
        return {
            "root": str(self.root),
            "main_files": [p.name for p in sorted(self.root.glob("*.py"))[:10]],
            "has_tests": (self.root / "tests").exists(),
            "has_git": (self.root / ".git").exists(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        }

    def _parse_code(self, code: str) -> list:
        """Parse Code-Output, gibt Liste von {path, content, exists} zurück. SCHREIBT NICHT."""
        changes = []
        lines = code.split("\n")
        current_file = None
        current_code = []
        in_code_block = False

        def _flush():
            if current_file:
                path = (self.root / current_file.strip()).resolve()
                content = "\n".join(current_code)
                changes.append({
                    "path": str(path),
                    "content": content,
                    "exists": path.exists(),
                })

        for line in lines:
            if line.startswith("## Datei:") or line.startswith("## File:") or line.startswith("## Tests:"):
                _flush()
                current_file = (
                    line.replace("## Datei:", "")
                        .replace("## File:", "")
                        .replace("## Tests:", "")
                        .strip()
                )
                current_code = []
                in_code_block = False
            elif line.startswith("```"):
                in_code_block = not in_code_block
            elif in_code_block and current_file:
                current_code.append(line)
        _flush()

        return changes

    def _write_code(self, planned_changes: list) -> list:
        """Schreibt die geparsten Änderungen auf Platte. Gibt Liste der Pfade zurück."""
        files_written = []
        for change in planned_changes:
            path = Path(change["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(change["content"])
            files_written.append(str(path))
        return files_written

    def _show_diff(self, planned_changes: list, full: bool = False) -> None:
        """Zeigt Diff oder Preview pro geplanter Datei."""
        import difflib

        for change in planned_changes:
            path = Path(change["path"])
            new_content = change["content"]
            rel = path.relative_to(self.root) if path.is_relative_to(self.root) else path

            if change["exists"]:
                old_content = path.read_text()
                diff = list(difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                    n=3,
                ))
                if not diff:
                    print(f"  ≡ UNCHANGED: {rel}")
                    continue
                print(f"\n📝 MODIFY: {rel}  (+{sum(1 for l in diff if l.startswith('+') and not l.startswith('+++'))} / -{sum(1 for l in diff if l.startswith('-') and not l.startswith('---'))})")
                if full:
                    print("".join(diff))
                else:
                    preview = diff[:30]
                    print("".join(preview))
                    if len(diff) > 30:
                        print(f"   ... ({len(diff) - 30} weitere Diff-Zeilen, 'diff' für Vollansicht)")
            else:
                lines = new_content.splitlines()
                print(f"\n✨ NEW: {rel}  ({len(lines)} Zeilen)")
                if full:
                    print(new_content)
                else:
                    preview = "\n".join(lines[:15])
                    print(preview)
                    if len(lines) > 15:
                        print(f"   ... ({len(lines) - 15} weitere Zeilen, 'code' für Vollansicht)")

    def _start_code_review(self, code: str, plan: dict, task: str) -> concurrent.futures.Future:
        """Startet parallelen Code-Reviewer (zweiter Qwen als Critic)."""
        def _run() -> str:
            review_prompt = f"""Du bist ein Senior Code-Reviewer. Reviewe diesen frisch generierten Code KRITISCH.

ORIGINALAUFGABE:
{task}

DETAIL-PLAN (Soll-Zustand):
{plan.get('plan', '')[:2000]}

GENERIERTER CODE:
{code}

Prüfe konkret:
1. KORREKTHEIT    - Implementiert es den Plan? Logik-Bugs?
2. EDGE CASES     - Nullwerte, leere Listen, Race Conditions?
3. ERROR HANDLING - Was passiert bei Exceptions? Zu defensiv / zu offen?
4. STYLE          - Konsistenz mit bestehendem Code im Projekt?
5. TESTS          - Decken sie wirklich die Logik ab oder nur Happy Path?
6. SECURITY       - Injection, Pfad-Traversal, Secrets im Code, unsafe input?
7. IMPORTS        - Alle nötigen da? Unbenutzte? Circular?
8. AMPEL          - 🟢 mergen / 🟡 mergen mit Anmerkungen / 🔴 nicht mergen

Sei knapp, kritisch, konkret. Wenn ok: 1 Satz + 🟢. Sonst: nummerierte Punkte."""
            return self.validator_qwen.generate(review_prompt, temperature=0.3)

        return self._executor.submit(_run)

    def _render_code_review(self, review_future: concurrent.futures.Future) -> str:
        """Holt Code-Reviewer-Ergebnis ab und rendert es."""
        print("\n[🔍 Code-Reviewer läuft parallel...]")
        try:
            result = review_future.result(timeout=300)
        except Exception as e:
            result = f"[Reviewer-Fehler: {e}]"
        print("\n" + "─"*70)
        print("🔍 PARALLELER CODE-REVIEW (unabhängiger Critic)")
        print("─"*70)
        print(result)
        print("─"*70)
        return result

    def _parse_and_write_code(self, code: str) -> list:
        """Legacy-API: parse + write in einem Schritt (für Tests / externe Aufrufer)."""
        changes = self._parse_code(code)
        return self._write_code(changes)

    # =========================================================================
    # MAIN WORKFLOW
    # =========================================================================

    def run_workflow(self, task: str, iteration: int = 0, max_iterations: int = 3,
                     parent_id: str = None) -> dict:
        """Laufe Workflow durch. Bei Test-Fail Loop zurück zu Phase 1 (max N Iterationen)."""
        wf_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        if iteration > 0:
            print("\n" + "█"*70)
            print(f"🔁 ITERATION {iteration}/{max_iterations} — neue Aufgabe aus Failure-Analyse")
            print("█"*70)

        self.current_workflow = {
            "id": wf_id,
            "task": task,
            "iteration": iteration,
            "parent_id": parent_id,
            "phases": {}
        }

        # Phase 1: BRIEFING
        briefing = self.phase_briefing(task)
        self.current_workflow["phases"]["briefing"] = briefing

        # Phase 2A: PLANNING - STRATEGIE
        strategy = self.phase_planning_strategy(briefing)
        if not strategy or not strategy.get("approved"):
            print("\n❌ Workflow abgebrochen (Strategie nicht genehmigt).\n")
            return self.current_workflow
        self.current_workflow["phases"]["planning_strategy"] = strategy

        # Phase 2B: PLANNING - DETAILPLAN
        planning = self.phase_planning_detailed(briefing, strategy)
        if not planning or not planning.get("approved"):
            print("\n❌ Workflow abgebrochen (Detail-Plan nicht genehmigt).\n")
            return self.current_workflow
        self.current_workflow["phases"]["planning_detailed"] = planning

        # Phase 3: EXECUTION (Dry-Run + Code-Review + User-Gate)
        execution = self.phase_execution(briefing, planning)
        self.current_workflow["phases"]["execution"] = execution
        if not execution.get("approved"):
            print("\n❌ Workflow abgebrochen (Code-Änderungen nicht genehmigt).\n")
            self._executor.shutdown(wait=False)
            return self.current_workflow

        # Phase 4: VERIFICATION
        verification = self.phase_verification(execution)
        self.current_workflow["phases"]["verification"] = verification

        # Bei Test-Fail: Failure-Loop zurück zu Phase 1 (mit Iteration-Cap)
        if not verification.get("tests_passed"):
            failure = self.phase_failure_analysis(briefing, execution, verification)
            self.current_workflow["phases"]["failure_analysis"] = failure

            # Workflow-Log schreiben (auch die abgebrochene Iteration)
            with open(self.workflow_log, "a") as f:
                f.write(json.dumps(self.current_workflow, default=str) + "\n")

            if iteration + 1 >= max_iterations:
                print(f"\n🔴 Max Iterationen ({max_iterations}) erreicht. Workflow abgebrochen.\n")
                self._executor.shutdown(wait=False)
                return self.current_workflow

            # User-Gate: Loop weitermachen?
            choice = input(
                f"\n👤 Folge-Iteration starten? (ja/nein/edit) "
                f"[{iteration + 1}/{max_iterations}]: "
            ).strip().lower()
            if choice in ["nein", "no", "n"]:
                print("\n⏭️ Loop abgebrochen, kein Commit.\n")
                self._executor.shutdown(wait=False)
                return self.current_workflow
            if choice == "edit":
                custom = input("Eigene Folge-Aufgabe: ").strip()
                if custom:
                    failure["followup_task"] = custom

            # Rekursiv neue Iteration starten
            return self.run_workflow(
                task=failure["followup_task"],
                iteration=iteration + 1,
                max_iterations=max_iterations,
                parent_id=wf_id,
            )

        # Phase 5: COMMIT (per Teilschritt)
        commit = self.phase_commit(briefing, execution, verification)
        self.current_workflow["phases"]["commit"] = commit

        # Log
        with open(self.workflow_log, "a") as f:
            f.write(json.dumps(self.current_workflow, default=str) + "\n")

        print("\n" + "="*70)
        print("✅ WORKFLOW ABGESCHLOSSEN")
        print("="*70 + "\n")

        # Validator-Threads sauber beenden
        self._executor.shutdown(wait=False)

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
