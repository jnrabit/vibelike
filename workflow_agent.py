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

Plan-Phasen (1, 2a, 2b) bekommen parallel einen kritischen LLM-Validator.
Detail-Plan + Execution bekommen ZUSÄTZLICH einen deterministischen
Static-Validator (siehe static_validator.py) — der findet Syntax-Bugs,
Imports, Security-Patterns, Plan/Code-Drift ohne LLM-Halluzination.
Test-Fail → Qwen formuliert Korrektur-Task → neue Iteration (max 3).
Commit-Phase splittet Änderungen in logische Teilschritte (Per-Step-Commits).

Start: python workflow_agent.py
"""

import os
import re
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
        # Import QwenCoder + Modell-Konstanten lokal (circular-import-Schutz)
        from terminal import QwenCoder, VALIDATOR_MODEL, CodeRetriever
        from validator2 import StaticValidatorV2

        # Retriever für Code-Vault-Integration in Planning-Phasen
        try:
            self.retriever = CodeRetriever()
        except Exception:
            self.retriever = None

        # Foreground: großes Modell für Code-Gen / Planung (siehe terminal.MODEL)
        self.qwen = QwenCoder()
        # Background: kleines Modell für parallelen LLM-Critic.
        self.validator_qwen = QwenCoder(
            model=VALIDATOR_MODEL,
            num_predict=768,
            keep_alive="60m",
        )
        # Deterministischer Static-Validator (kein LLM, keine Halluzination).
        self.static_validator = StaticValidatorV2()
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
            validator_prompt = f"""Du bist ein adversarialer Reviewer. Deine EINZIGE Aufgabe: finde, was schiefgehen kann.

KONTEXT:
{context}

ZU REVIEWEN ({phase_name}):
{output}

REGELN (strikt):
- Beginne mit GENAU einer Zeile: "🟢" oder "🟡 <ein-Satz-Grund>" oder "🔴 <ein-Satz-Grund>"
- Danach MAXIMAL 3 konkrete Punkte, je 1-2 Sätze, mit Zitat aus der Ausgabe oder Verweis auf konkrete Stelle
- VERBOTEN: "✅"-Listen, Wiederholung der Punkte aus der Ausgabe, Bestätigungsfloskeln ("gut implementiert", "korrekt umgesetzt"), allgemeine Best-Practice-Lyrik
- Wenn du nichts Konkretes findest: NUR "🟢" ausgeben, sonst NICHTS

Beispiele für GUTE Punkte:
- "Annahme dass GitHub API ohne Auth nutzbar — bei >60 req/h hard limit, Plan erwähnt keinen Token"
- "Plan überspringt was passiert wenn README binary ist (UnicodeDecodeError in Zeile X)"
- "Tests behaupten 'race conditions abgedeckt' aber kein einziger Concurrency-Test im Plan"

Beispiele für SCHLECHTE Punkte (nicht so):
- "Implementiert Error-Handling mit try-except"
- "Folgt PEP 8 Style"
- "Tests decken die Logik ab"
"""
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
    # USER-INTERAKTION (Approval + Feedback-basiertes Regenerieren)
    # =========================================================================

    def _ask_approval(self, what: str) -> dict:
        """Fragt User nach Approval. Unterstützt inline-Feedback: 'änderungen: <text>'.

        Returns dict with action: 'approve' | 'reject' | 'change' (+ 'changes' on change).
        """
        while True:
            raw = input(f"\n👤 {what} ok? (ja/nein/änderungen): ").strip()
            low = raw.lower()

            if low in ["ja", "yes", "y", "j"]:
                return {"action": "approve"}
            if low in ["nein", "no", "n"]:
                return {"action": "reject"}

            # 'änderungen', 'änderung', 'ä', 'a' (mit optionalem inline-Text nach ':' oder ' ')
            m = re.match(r"^(änderung\w*|ä|a)\s*[:.\s]\s*(.*)$", raw, re.IGNORECASE)
            if low.startswith("änder") or low in ("ä", "a") or (m and m.group(1)):
                inline = m.group(2).strip() if m else ""
                if inline:
                    return {"action": "change", "changes": inline}
                changes = input(f"Welche Änderungen an der {what}? ").strip()
                if changes:
                    return {"action": "change", "changes": changes}
                print("Keine Änderungen angegeben.")
                continue

            print("Bitte 'ja', 'nein' oder 'änderungen' eingeben (oder 'änderungen: <text>').")

    def _build_feedback_block(self, feedback_history: list[str], previous_output: str, kind: str) -> str:
        """Baut Feedback-Block fürs Re-Generieren von Strategie/Plan."""
        if not feedback_history:
            return ""

        feedback_lines = "\n".join(f"- {fb}" for fb in feedback_history)
        prev = previous_output[:3000] + ("...[gekürzt]" if len(previous_output) > 3000 else "")
        return f"""
═══════════════════════════════════════════════════════════════════
🔴 USER-FEEDBACK ZUR VORHERIGEN {kind.upper()} (UNBEDINGT BEACHTEN!):
{feedback_lines}

VORHERIGE {kind.upper()} (war unzureichend):
---
{prev}
---

Erstelle die {kind} NEU unter strikter Beachtung des Feedbacks.
═══════════════════════════════════════════════════════════════════
"""

    def _retrieve(self, query: str, k: int = 3, max_snippet: int = 500) -> str:
        """Holt allgemeine CS-Konzepte aus dem Vault (Wikipedia/RFCs/PEPs).

        ⚠️  Der Vault enthält KEIN Projekt-Code — nur Enzyklopädie-Wissen.
        Für Projekt-Code: _extract_code_overview() / _read_focused_files() nutzen.
        """
        if not self.retriever:
            return ""
        try:
            docs, _, _ = self.retriever.search(query, k=k)
            if not docs:
                return ""
            lines = [
                "📚 ALLGEMEINES CS-WISSEN (Wikipedia/RFCs/PEPs — kein Projektcode!):",
                "(Nutze nur als Konzept-Refresh, NICHT als Quelle für Datei-/Funktionsnamen)",
            ]
            for i, doc in enumerate(docs, 1):
                title = doc.get("title", "unknown")
                source = doc.get("source", "?")
                distance = doc.get("distance", 0)
                content = doc.get("content", "")[:max_snippet]
                lines.append(f"\n[{i}] {title} (src={source}, dist={distance:.1f}):")
                lines.append(f"    {content}")
            return "\n".join(lines)
        except Exception:
            return ""

    # =========================================================================
    # PHASE 1: BRIEFING
    # =========================================================================

    def phase_briefing(self, task: str) -> dict:
        """Phase 1: Analyse der Aufgabe + ECHTER PROJEKTCODE."""
        print("\n" + "="*70)
        print("PHASE 1: BRIEFING")
        print("="*70)
        print(f"\n📝 Aufgabe: {task}\n")

        # Sammle Projektinfo + ECHTEN CODE (gegen Halluzinationen)
        project_info = self._gather_project_info()
        print("[📂 Lese Projektcode...]")
        code_overview = self._extract_code_overview()
        focused_files = self._read_focused_files(task)
        print(f"   Übersicht: {code_overview.count('📄')} Dateien strukturiert")
        print(f"   Volle Inhalte: {focused_files.count('═══')//2} Dateien gelesen\n")

        # Qwen analysiert
        analysis_prompt = f"""Du bist ein Senior Code-Architekt. Analysiere diese Aufgabe und das ECHTE Projekt:

AUFGABE:
{task}

PROJEKTSTRUKTUR (Metadata):
{json.dumps(project_info, indent=2, default=str)}

═══════════════════════════════════════════════════════════════════
📋 CODE-ÜBERSICHT (alle .py-Dateien, AST-extrahiert — NICHT erfinden!):
═══════════════════════════════════════════════════════════════════
{code_overview}

═══════════════════════════════════════════════════════════════════
📄 VOLLER CODE der task-relevanten Dateien (verbindlich, NICHT erfinden!):
═══════════════════════════════════════════════════════════════════
{focused_files}

═══════════════════════════════════════════════════════════════════

WICHTIG:
- Nur Dateien/Funktionen/Klassen erwähnen, die OBEN tatsächlich auftauchen.
- Wenn die Aufgabe sich auf "vibelike.py" o.ä. bezieht, das aber NICHT in der Übersicht steht — explizit darauf hinweisen.

Antworte mit einer Analyse:
1. Verstehen Sie die Aufgabe korrekt?
2. Welche KONKRETEN Dateien/Komponenten aus der Übersicht oben sind betroffen?
3. Wie passt es ins bestehende System? (mit Verweisen auf konkrete Klassen/Funktionen)
4. Gibt es Abhängigkeiten oder Konflikte?
5. Welche Risiken sehen Sie?

Sei präzise und technisch. Zitiere echten Code wo möglich."""

        print("[🤖 Qwen analysiert (mit ECHTEM Code)...]\n")
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
            "project_info": project_info,
            "code_overview": code_overview,
            "focused_files": focused_files,
        }
        return result

    # =========================================================================
    # PHASE 2A: PLANNING (STRATEGIE / ALLGEMEINES VORGEHEN)
    # =========================================================================

    def phase_planning_strategy(self, briefing: dict) -> dict:
        """Phase 2a: Strategische Planung - allgemeines Vorgehen (User-Genehmigung).

        Bei 'änderungen' wird die Strategie mit User-Feedback NEU generiert (max 3 Iterationen).
        """
        print("\n" + "="*70)
        print("PHASE 2A: PLANNING - STRATEGIE (Allgemeines Vorgehen)")
        print("="*70)

        # Retrieval: allgemeine CS-Konzepte (Vault hat kein Projektcode!)
        retrieval_ctx = self._retrieve(briefing['task'], k=3)
        if retrieval_ctx:
            print("\n[📚 Vault-Retrieval (allgemeines CS-Wissen)...]")
            print(retrieval_ctx)

        # Echter Projektcode aus Briefing (gegen Halluzinationen)
        code_overview = briefing.get("code_overview", "")

        feedback_history: list[str] = []
        previous_strategy = ""
        max_iterations = 3

        for iteration in range(1, max_iterations + 1):
            feedback_block = self._build_feedback_block(
                feedback_history, previous_strategy, "Strategie"
            )

            strategy_prompt = f"""Du bist ein Senior Software-Architekt. Erstelle eine STRATEGISCHE Planung für die Aufgabe.
{feedback_block}
ANALYSE:
{briefing['analysis']}

📋 ECHTE PROJEKT-CODE-ÜBERSICHT (AST-extrahiert, verbindlich):
{code_overview}

{retrieval_ctx}

Diese Phase ist HIGH-LEVEL - noch KEINE konkreten Dateien/Funktionen.
WICHTIG: Beziehe dich nur auf Dateien/Klassen die in der Übersicht oben tatsächlich existieren.

Beantworte:
1. ANSATZ: Welche grundsätzliche Strategie? (z.B. neuer Service, Erweiterung, Refactoring)
2. ARCHITEKTUR: Welche Komponenten/Pattern verwenden? (z.B. Plugin-System, Adapter, Decorator)
3. ALTERNATIVEN: Welche Alternativen gibt es? Warum diese Wahl?
4. TRADE-OFFS: Vor- und Nachteile des gewählten Ansatzes
5. ABHÄNGIGKEITEN: Welche externen Libraries/APIs nötig?
6. RISIKEN: Was könnte schiefgehen? (technisch & inhaltlich)
7. AUFWAND: Grob - Stunden? Tage? Wochen?

Format: Strukturiert, aber NICHT zu detailliert. Konzentriere dich auf das WAS und WARUM, noch nicht auf das WIE."""

            label = f"Strategie (Iter {iteration}, NEU mit Feedback)" if feedback_history else "Strategie"
            print(f"\n[🤖 Qwen entwickelt {label}...]\n")
            strategy = self.qwen.generate(strategy_prompt, temperature=0.3, stream=True)

            # Parallel: Validator startet
            validation_future = self._start_validation(
                "PLANNING-STRATEGIE",
                strategy,
                f"BRIEFING-ANALYSE:\n{briefing['analysis']}"
            )
            validation = self._render_validation(validation_future)

            previous_strategy = strategy

            result = {
                "phase": "PLANNING_STRATEGY",
                "strategy": strategy,
                "validation": validation,
                "iteration": iteration,
                "feedback_history": feedback_history.copy(),
                "timestamp": datetime.now().isoformat(),
                "approved": False,
            }

            print("\n" + "-"*70)

            decision = self._ask_approval("Strategie")
            if decision["action"] == "approve":
                result["approved"] = True
                print("\n✅ Strategie genehmigt! Starte Detail-Planung...\n")
                return result
            if decision["action"] == "reject":
                print("\n❌ Strategie nicht genehmigt. Workflow abgebrochen.\n")
                return None
            if decision["action"] == "change":
                feedback_history.append(decision["changes"])
                if iteration < max_iterations:
                    print(f"\n[🔁 Generiere Strategie neu mit Feedback (Iter {iteration+1}/{max_iterations})...]")
                else:
                    print(f"\n⚠️  Max Iterationen ({max_iterations}) erreicht.")
                    result["change_request"] = decision["changes"]
                    return result

        return result

    # =========================================================================
    # PHASE 2B: PLANNING (DETAILPLAN / KONKRETE DURCHFÜHRUNG)
    # =========================================================================

    def phase_planning_detailed(self, briefing: dict, strategy: dict) -> dict:
        """Phase 2b: Detail-Planung - konkrete Durchführung (User-Genehmigung).

        Bei 'änderungen' wird der Plan mit User-Feedback NEU generiert (max 3 Iterationen).
        """
        print("\n" + "="*70)
        print("PHASE 2B: PLANNING - DETAILPLAN (Konkrete Durchführung)")
        print("="*70)

        # Retrieval: allgemeine CS-Konzepte (Vault hat kein Projektcode!)
        retrieval_query = f"{briefing['task']} {strategy['strategy'][:200]}"
        retrieval_ctx = self._retrieve(retrieval_query, k=3)
        if retrieval_ctx:
            print("\n[📚 Vault-Retrieval für Detail-Plan (allgemeines CS-Wissen)...]")
            print(retrieval_ctx)

        # Echter Projektcode aus Briefing (gegen Halluzinationen)
        code_overview = briefing.get("code_overview", "")
        focused_files = briefing.get("focused_files", "")

        feedback_history: list[str] = []
        previous_plan = ""
        max_iterations = 3

        for iteration in range(1, max_iterations + 1):
            feedback_block = self._build_feedback_block(
                feedback_history, previous_plan, "Detail-Plan"
            )

            detail_prompt = f"""Du bist ein Senior Software Engineer. Erstelle den DETAILLIERTEN Durchführungsplan
basierend auf der genehmigten Strategie.
{feedback_block}
ORIGINALAUFGABE:
{briefing['task']}

GENEHMIGTE STRATEGIE:
{strategy['strategy']}

📋 ECHTE PROJEKT-CODE-ÜBERSICHT (AST-extrahiert, verbindlich — NICHT erfinden!):
{code_overview}

📄 VOLLER CODE relevanter Dateien (verbindliche Quelle):
{focused_files}

{retrieval_ctx}

Diese Phase ist KONKRET - jetzt das WIE.

WICHTIG:
- Nur Dateien planen, die in der Übersicht oben existieren (für Modifikationen) ODER explizit als NEU markieren.
- Zeilen-Nummern nur angeben wenn aus dem vollen Code oben verifizierbar.
- Keine erfundenen Pfade wie "vibelike.py" wenn nicht existent.

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

            label = f"Detail-Plan (Iter {iteration}, NEU mit Feedback)" if feedback_history else "Detail-Plan"
            print(f"\n[🤖 Qwen erstellt {label}...]\n")
            plan = self.qwen.generate(detail_prompt, temperature=0.2, stream=True)

            # Parallel: Validator startet
            validation_future = self._start_validation(
                "PLANNING-DETAIL",
                plan,
                f"AUFGABE: {briefing['task']}\n\nGENEHMIGTE STRATEGIE:\n{strategy['strategy']}"
            )
            validation = self._render_validation(validation_future)

            # Deterministischer Plan-Check (Struktur + Spezifität)
            plan_report = self.static_validator.validate_plan(plan, plan_kind="detail")
            if plan_report.findings:
                print("\n" + "─"*70)
                print("🔧 STATIC PLAN-CHECK (deterministisch)")
                print("─"*70)
                print(plan_report.render())
                print("─"*70)

            previous_plan = plan

            result = {
                "phase": "PLANNING_DETAILED",
                "plan": plan,
                "validation": validation,
                "static_validation": {
                    "verdict": plan_report.verdict,
                    "findings": [
                        {"severity": f.severity, "check": f.check,
                         "location": f.location, "message": f.message}
                        for f in plan_report.findings
                    ],
                },
                "strategy_ref": strategy.get("strategy", ""),
                "iteration": iteration,
                "feedback_history": feedback_history.copy(),
                "timestamp": datetime.now().isoformat(),
                "approved": False,
            }

            print("\n" + "-"*70)

            decision = self._ask_approval("Detail-Plan")
            if decision["action"] == "approve":
                result["approved"] = True
                print("\n✅ Detail-Plan genehmigt! Starte Execution...\n")
                return result
            if decision["action"] == "reject":
                print("\n❌ Detail-Plan nicht genehmigt. Workflow abgebrochen.\n")
                return None
            if decision["action"] == "change":
                feedback_history.append(decision["changes"])
                if iteration < max_iterations:
                    print(f"\n[🔁 Generiere Detail-Plan neu mit Feedback (Iter {iteration+1}/{max_iterations})...]")
                else:
                    print(f"\n⚠️  Max Iterationen ({max_iterations}) erreicht.")
                    result["change_request"] = decision["changes"]
                    return result

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

        # Parallel: LLM-Code-Reviewer startet (nach Stream-Ende)
        review_future = self._start_code_review(code, plan, briefing['task'])

        # Strukturierter Diff
        print(f"\n📦 GEPLANTE ÄNDERUNGEN ({len(planned_changes)} Dateien):")
        print("="*70)
        self._show_diff(planned_changes, full=False)

        # 3-Schichten Validierung: Code + Plan + Knowledge-Graph (Ossifikat Audits)
        # Layer 1 & 2: Code + Plan Validierung
        # Layer 3: Ossifikat Triple-Audits (optional, fallback wenn DB fehlt)
        ossifikat_db_path = None
        try:
            ossifikat_db_path = str(self.root / "ossifikat" / "data" / "ossifikat.db")
            if not (self.root / "ossifikat" / "data" / "ossifikat.db").exists():
                ossifikat_db_path = None
        except Exception:
            pass

        static_report = self.static_validator.validate_full(
            planned_changes,
            plan.get("plan", ""),
            ossifikat_db=ossifikat_db_path
        )

        print("\n" + "─"*70)
        print("🔧 3-SCHICHTEN VALIDATOR (Code + Plan + Knowledge-Graph)")
        print("─"*70)

        # Zeige Findings gruppiert nach Layer
        if static_report.findings:
            code_findings = [f for f in static_report.findings if not f.check.startswith("audit:")]
            audit_findings = [f for f in static_report.findings if f.check.startswith("audit:")]

            if code_findings:
                print(f"\n  Layer 1+2 (Code & Plan): {len(code_findings)} findings")
                for f in code_findings[:5]:
                    severity_symbol = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(f.severity, "⚪")
                    print(f"    {severity_symbol} {f.check:30s} @ {f.location}")
                if len(code_findings) > 5:
                    print(f"    ... (+{len(code_findings)-5} more)")

            if audit_findings:
                print(f"\n  Layer 3 (Knowledge-Graph Audits): {len(audit_findings)} findings")
                for f in audit_findings[:5]:
                    severity_symbol = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(f.severity, "⚪")
                    print(f"    {severity_symbol} {f.check:30s} @ {f.location}")
                if len(audit_findings) > 5:
                    print(f"    ... (+{len(audit_findings)-5} more)")
        else:
            print("  ✅ Keine Findings (sauberer Code & Knowledge-Graph)")

        print("─"*70)

        # LLM-Code-Review einsammeln (paralleles Reasoning oben drauf)
        review = self._render_code_review(review_future)

        # Self-Healing: bei StaticValidator 🔴 die problematischen Files
        # automatisch neu generieren lassen (max 2 Mikro-Cycles).
        heal_log = []
        if static_report.verdict == "🔴":
            planned_changes, static_report, heal_log = self._self_heal_execution(
                planned_changes, plan, briefing, static_report, review
            )
            if heal_log:
                final = "🟢" if static_report.verdict == "🟢" else (
                    "🟡" if static_report.verdict == "🟡" else "🔴 (Heal hat nicht geholfen)"
                )
                print(f"\n🔧 Self-Heal abgeschlossen — Verdict: {final}")
                print(f"\n📦 ÄNDERUNGEN NACH HEAL ({len(planned_changes)} Dateien):")
                print("="*70)
                self._show_diff(planned_changes, full=False)

        result = {
            "phase": "EXECUTION",
            "code": code,
            "planned_changes": [{"path": c["path"], "exists": c["exists"], "lines": len(c["content"].splitlines())} for c in planned_changes],
            "code_review": review,
            "static_validation": {
                "verdict": static_report.verdict,
                "findings": [
                    {"severity": f.severity, "check": f.check,
                     "location": f.location, "message": f.message}
                    for f in static_report.findings
                ],
            },
            "self_heal": heal_log,
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

        # Ampel aus Analyse extrahieren (erste 🟢/🟡/🔴 nach AMPEL-Zeile)
        traffic_light = "🟡"  # konservativer Default
        for line in analysis.splitlines():
            l = line.strip()
            if "🟢" in l:
                traffic_light = "🟢"; break
            if "🔴" in l:
                traffic_light = "🔴"; break
            if "🟡" in l:
                traffic_light = "🟡"; break

        result = {
            "phase": "FAILURE_ANALYSIS",
            "analysis": analysis,
            "followup_task": followup_task,
            "traffic_light": traffic_light,
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
            "main_files": [p.name for p in sorted(self.root.glob("*.py"))[:20]],
            "has_tests": (self.root / "tests").exists(),
            "has_git": (self.root / ".git").exists(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        }

    def _extract_code_overview(self, max_files: int = 25) -> str:
        """AST-basierte Übersicht aller .py Dateien (Modul-Docstring + Klassen + Funktionen)."""
        import ast as _ast

        py_files = sorted(self.root.glob("*.py"))[:max_files]
        sections = []

        for f in py_files:
            try:
                src = f.read_text()
                tree = _ast.parse(src)
            except Exception:
                continue

            items: list[str] = []
            doc = _ast.get_docstring(tree)
            if doc:
                first_line = doc.strip().splitlines()[0][:130]
                items.append(f'  """{first_line}"""')

            for node in tree.body:
                if isinstance(node, _ast.ClassDef):
                    methods = [
                        m.name for m in node.body
                        if isinstance(m, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                    ]
                    items.append(
                        f"  class {node.name}: {', '.join(methods[:8])}"
                        + (f" (+{len(methods)-8})" if len(methods) > 8 else "")
                    )
                elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    args = [a.arg for a in node.args.args if a.arg != "self"]
                    items.append(f"  def {node.name}({', '.join(args)})")

            if items:
                size_kb = f.stat().st_size / 1024
                sections.append(f"\n📄 {f.name} ({size_kb:.1f} KB):")
                sections.extend(items[:20])
                if len(items) > 20:
                    sections.append(f"  ... +{len(items)-20} weitere")

        return "\n".join(sections) if sections else "(kein Python-Code gefunden)"

    def _read_focused_files(self, task: str, max_files: int = 4,
                            max_chars: int = 5000) -> str:
        """Liest volle Inhalte der task-relevanten Dateien.

        Heuristik: Filenamen im Task-Text erwähnt + core-files als Fallback.
        """
        core_files = ["terminal.py", "workflow_agent.py", "validator2.py",
                      "ossifikat_audit_bridge.py"]

        # 1. Im Task explizit erwähnte Dateien
        mentioned: list[str] = []
        task_lower = task.lower()
        for p in self.root.glob("*.py"):
            if p.name.lower() in task_lower or p.stem.lower() in task_lower:
                mentioned.append(p.name)

        # 2. Bei /vibelike, /quelibrium, /ossifikat → entsprechende Dateien priorisieren
        if "/vibelike" in task_lower or "vibelike" in task_lower:
            mentioned.extend(["terminal.py", "workflow_agent.py"])
        if "validator" in task_lower:
            mentioned.append("validator2.py")
        if "ossifikat" in task_lower:
            mentioned.append("ossifikat_audit_bridge.py")

        # 3. Dedupe + Fallback
        selected = list(dict.fromkeys(mentioned + core_files))[:max_files]

        sections = []
        for fname in selected:
            f = self.root / fname
            if not f.exists():
                continue
            try:
                content = f.read_text()
            except Exception:
                continue

            total = len(content)
            if total > max_chars:
                content = content[:max_chars] + f"\n... [gekürzt — Datei hat insgesamt {total:,} chars]"

            sections.append(f"\n═══ {fname} ═══\n{content}")

        return "\n".join(sections) if sections else ""

    def _self_heal_test_failure(self, briefing, plan, execution, verification,
                                  failure, max_cycles: int = 2):
        """Mikro-Heal-Loop für Test-Failures mit 🟢-Ampel: 7b patcht die
        geänderten Files basierend auf Test-Output, schreibt direkt, re-verifiziert.
        Kein User-Gate (selbstheilend). Max N Cycles.

        Returns: (final_verification, heal_log, success_bool).
        """
        heal_log = []
        files_changed = list(execution.get("files_written", []))
        if not files_changed:
            return verification, [{"status": "skipped",
                                   "reason": "keine files_written"}], False

        current_verification = verification
        current_followup = failure.get("followup_task", "")

        for cycle in range(1, max_cycles + 1):
            if current_verification.get("tests_passed"):
                return current_verification, heal_log, True

            print("\n" + "█"*70)
            print(f"🔧 TEST-FAILURE MIKRO-HEAL CYCLE {cycle}/{max_cycles}")
            print("█"*70)
            print(f"Fix-Anweisung: {current_followup[:200]}")

            # Aktuellen Code der geänderten Files lesen
            current_code_blocks = []
            for fpath in files_changed:
                p = Path(fpath)
                if not p.exists():
                    continue
                try:
                    content = p.read_text()
                except Exception:
                    continue
                current_code_blocks.append(
                    f"## Datei: {fpath}\n```python\n{content}\n```"
                )
            if not current_code_blocks:
                heal_log.append({"cycle": cycle, "status": "no_readable_files"})
                break

            files_text = "\n\n".join(current_code_blocks)
            test_out = (current_verification.get("output", "") +
                        "\n" + current_verification.get("stderr", ""))[-2000:]

            fix_prompt = f"""Du bist Senior Engineer. Tests sind nach einer Änderung fehlgeschlagen.
PATCHE DEN CODE — schreib NUR die Files neu die wirklich repariert werden müssen.

ORIGINALAUFGABE:
{briefing['task']}

FIX-ANWEISUNG aus Failure-Analyse:
{current_followup}

TEST-OUTPUT (letzte Zeilen):
{test_out}

DERZEITIGER CODE:
{files_text}

ANWEISUNG:
- Fix den konkreten Bug der die Tests bricht
- Behalte den Rest des Codes unverändert
- Output-Format: ## Datei: <absoluter pfad> + ```python``` Block für JEDES geänderte File
- Kein Fließtext, keine Erklärung — nur Code
"""
            print("\n[🤖 7b-Foreground patcht Code...]\n")
            fix_code = self.qwen.generate(fix_prompt, temperature=0.0, stream=True)

            fixed = self._parse_code(fix_code)
            if not fixed:
                heal_log.append({"cycle": cycle, "status": "no_files_parsed"})
                break

            # Sicherheit: nur Files schreiben die schon in files_changed waren
            allowed = {str(Path(p).resolve()) for p in files_changed}
            safe_changes = [c for c in fixed
                            if str(Path(c["path"]).resolve()) in allowed]
            if not safe_changes:
                heal_log.append({"cycle": cycle, "status": "no_safe_paths",
                                 "rejected": [c["path"] for c in fixed]})
                break

            written = self._write_code(safe_changes)
            print(f"\n✅ {len(written)} File(s) gepatcht:")
            for f in written:
                print(f"   - {f}")

            # Tests erneut laufen lassen
            print("\n[🧪 Re-Verification nach Patch...]")
            new_verification = self.phase_verification(execution)

            heal_log.append({
                "cycle": cycle,
                "files_patched": written,
                "tests_passed": new_verification.get("tests_passed", False),
            })

            current_verification = new_verification
            if new_verification.get("tests_passed"):
                return new_verification, heal_log, True

            # Wenn weiterer Cycle nötig: neue Failure-Analyse für gezielte Anweisung
            if cycle < max_cycles:
                new_failure = self.phase_failure_analysis(
                    briefing, execution, new_verification
                )
                current_followup = new_failure.get("followup_task", current_followup)
                # Wenn die neue Ampel nicht mehr 🟢 ist → Mikro-Heal abbrechen,
                # damit der Makro-Loop übernehmen kann.
                if new_failure.get("traffic_light") != "🟢":
                    heal_log.append({"cycle": cycle, "status": "escalated",
                                     "new_traffic_light": new_failure.get("traffic_light")})
                    break

        return current_verification, heal_log, False

    def _self_heal_execution(self, planned_changes, plan, briefing,
                              static_report, review, max_cycles: int = 2):
        """Mikro-Heal-Loop: bei StaticValidator 🔴 die betroffenen Files vom 7b
        neu generieren lassen, re-validieren. Max N Cycles.

        Returns: (new_planned_changes, new_static_report, heal_log).
        """
        heal_log = []
        current_changes = list(planned_changes)
        current_static = static_report

        for cycle in range(1, max_cycles + 1):
            if current_static.verdict != "🔴":
                break

            high = [f for f in current_static.findings if f.severity == "high"]
            medium = [f for f in current_static.findings if f.severity == "medium"]

            affected: set = set()
            for f in high + medium:
                loc = (f.location or "").split(":")[0].strip()
                if loc and loc.lower() != "plan":
                    affected.add(loc)

            if not affected:
                heal_log.append({"cycle": cycle, "status": "skipped",
                                 "reason": "findings ohne File-Lokalisierung"})
                break

            print("\n" + "█"*70)
            print(f"🔧 SELF-HEAL CYCLE {cycle}/{max_cycles}")
            print("█"*70)
            print(f"Probleme in: {sorted(affected)}")

            affected_changes = [
                c for c in current_changes
                if any(str(c["path"]).endswith(p) or p in str(c["path"])
                       for p in affected)
            ]
            if not affected_changes:
                heal_log.append({"cycle": cycle, "status": "skipped",
                                 "reason": "keine planned_changes zu Findings-Pfaden"})
                break

            findings_text = "\n".join(
                f"- [{f.severity.upper()}] {f.check} @ {f.location}: {f.message}"
                for f in high + medium
            )
            review_hint = ""
            if review and "🔴" in review:
                review_hint = f"\n\nZUSÄTZLICHE LLM-CRITIC HINWEISE:\n{review[:800]}"

            files_to_fix = "\n\n".join(
                f"## Datei: {c['path']}\n```python\n{c['content']}\n```"
                for c in affected_changes
            )
            fix_prompt = f"""Du bist Senior Engineer. Im generierten Code wurden Probleme gefunden.
SCHREIBE NUR DIE BETROFFENEN FILES NEU.

ORIGINALAUFGABE:
{briefing['task']}

GEFUNDENE PROBLEME (deterministischer Static-Validator):
{findings_text}{review_hint}

DERZEITIGER CODE DER BETROFFENEN FILES:
{files_to_fix}

ANWEISUNG:
- Fix JEDES gelistete Problem (insbesondere severity HIGH)
- Behalte den Rest des Codes — gib NUR die betroffenen Files zurück
- Output-Format: ## Datei: <path> + ```python``` Block
- Kein Fließtext, keine Erklärungen
"""
            print("\n[🤖 7b-Foreground heilt Code...]\n")
            fix_code = self.qwen.generate(fix_prompt, temperature=0.0, stream=True)

            fixed = self._parse_code(fix_code)
            if not fixed:
                heal_log.append({"cycle": cycle, "status": "no_files_parsed"})
                break

            fixed_paths = {c["path"] for c in fixed}
            current_changes = [c for c in current_changes
                               if c["path"] not in fixed_paths] + fixed

            new_static = self.static_validator.validate_code(
                current_changes, plan.get("plan", "")
            )
            print("\n" + "─"*70)
            print(f"🔧 STATIC VALIDATOR nach Heal-Cycle {cycle}")
            print("─"*70)
            print(new_static.render())
            print("─"*70)

            heal_log.append({
                "cycle": cycle,
                "old_verdict": current_static.verdict,
                "new_verdict": new_static.verdict,
                "files_rewritten": sorted(fixed_paths),
            })
            current_static = new_static

        return current_changes, current_static, heal_log

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
            review_prompt = f"""Du bist ein adversarialer Code-Reviewer. Deine EINZIGE Aufgabe: finde konkrete Bugs.

AUFGABE:
{task}

PLAN (Soll-Zustand):
{plan.get('plan', '')[:1500]}

GENERIERTER CODE:
{code}

REGELN (strikt):
- Beginne mit GENAU einer Zeile: "🟢" oder "🟡 <ein-Satz-Grund>" oder "🔴 <ein-Satz-Grund>"
- Danach MAXIMAL 5 konkrete Befunde. Jeder Befund:
   "<datei>:<zeile> | <was-ist-falsch> | <warum-bug>"
- VERBOTEN: "✅"-Listen, "Implementiert X korrekt"-Sätze, Best-Practice-Lyrik,
   Wiederholung des Plans, Stil-Hinweise ohne konkrete Zeile
- Wenn du keinen konkreten Bug findest: NUR "🟢" ausgeben, sonst NICHTS

Was zählt als konkreter Bug:
- Plan-Abweichung (Plan sagt X, Code macht Y)
- Crash-Pfad (NPE, leere Liste, Encoding, Race)
- Falsche Annahme (z.B. API ohne Auth limitiert, Pfad existiert nicht)
- Test prüft nicht was er behauptet
- Security: tatsächlicher unsafe input, kein Theoretisches

Was NICHT zählt:
- "Könnte besser kommentiert sein"
- "Folgt PEP 8"
- "Hat try-except"
- Allgemeine Anmerkungen ohne Code-Zeile
"""
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

            # Mikro-Heal bei 🟢-Ampel: direkt patchen statt Macro-Loop
            if failure.get("traffic_light") == "🟢":
                new_verification, micro_log, healed = self._self_heal_test_failure(
                    briefing, planning, execution, verification, failure
                )
                self.current_workflow["phases"]["test_failure_self_heal"] = {
                    "success": healed,
                    "cycles": micro_log,
                }
                if healed:
                    # Verification ersetzen, weiter zu Phase 5
                    verification = new_verification
                    self.current_workflow["phases"]["verification"] = verification
                    print("\n🟢 Mikro-Heal erfolgreich — Workflow läuft normal weiter.\n")
                else:
                    # Mikro-Heal hat nicht geholfen → in Makro-Loop fallen
                    print("\n🟡 Mikro-Heal hat nicht gereicht — eskaliere zu Macro-Loop.\n")

            # Workflow-Log schreiben (auch die abgebrochene Iteration)
            with open(self.workflow_log, "a") as f:
                f.write(json.dumps(self.current_workflow, default=str) + "\n")

        # Wenn Mikro-Heal die Tests fixen konnte, NICHT in den Macro-Loop fallen
        if not verification.get("tests_passed"):

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
