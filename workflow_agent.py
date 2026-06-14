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
from agent_loop import AgentLoop
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "ossifikat"))


from task_classifier import TaskClassifier
from agent_loop import AgentLoop


class WorkflowAgent:
    """Orchestriert einen 6-Phasen-Workflow über den primitiven AgentLoop."""

    def __init__(self):
        # Der WorkflowAgent nutzt den AgentLoop für alle Aktionen.
        self.loop = AgentLoop()

        # TaskClassifier nutzt den Analyzer-Coder vom AgentLoop (Lazy-loaded bei Bedarf)
        # Verhindert doppelte Model-Initialisierungen
        self.classifier = TaskClassifier(self.loop.analyzer_coder)

        self.root = Path(__file__).parent
        self.workflow_log = self.root / "logs" / "workflows.jsonl"
        self.workflow_log.parent.mkdir(parents=True, exist_ok=True)


    async def run_workflow(self, task: str, search_mode: str = "balanced"):
        """
        Führt den gesamten 6-Phasen-Workflow als eine Sequenz von primitiven
        Schritten über den AgentLoop aus.
        """
        print("\n" + "="*70)
        print(f"🚀 Starte Workflow für: {task}")
        print("="*70)

        # PHASE 1: BRIEFING
        print("\nPHASE 1: BRIEFING")
        briefing_result = await self.loop.step(
            query=f"Erstelle ein Briefing für die Aufgabe '{task}'",
            # Parameter für das 'generate_briefing' Tool
            params={"task": task, "search_mode": search_mode}
        )
        if "[ERR]" in briefing_result:
            print(f"❌ Workflow abgebrochen in Phase 1 (Briefing): {briefing_result}")
            return

        approval = self._ask_approval("Briefing")
        if approval["action"] != "approve":
            print("❌ Workflow vom Benutzer abgebrochen.")
            return

        # PHASE 2: STRATEGIE
        print("\nPHASE 2: STRATEGIE")
        strategy_result = await self.loop.step(
            query="Erstelle eine Strategie basierend auf dem Briefing",
            params={"briefing": briefing_result}
        )
        if "[ERR]" in strategy_result:
            print(f"❌ Workflow abgebrochen in Phase 2 (Strategie): {strategy_result}")
            return

        approval = self._ask_approval("Strategie")
        if approval["action"] != "approve":
            print("❌ Workflow vom Benutzer abgebrochen.")
            return
        
        # PHASE 3: DETAIL-PLAN
        print("\nPHASE 3: DETAIL-PLAN")
        plan_result = await self.loop.step(
            query="Erstelle einen detaillierten Plan basierend auf der Strategie",
            params={"strategy": strategy_result}
        )
        if "[ERR]" in plan_result:
            print(f"❌ Workflow abgebrochen in Phase 3 (Detail-Plan): {plan_result}")
            return
            
        approval = self._ask_approval("Detail-Plan")
        if approval["action"] != "approve":
            print("❌ Workflow vom Benutzer abgebrochen.")
            return

        # PHASE 4: EXECUTION
        print("\nPHASE 4: EXECUTION")
        code_result = await self.loop.step(
            query="Generiere Code basierend auf dem Plan",
            params={"plan": plan_result, "relevant_code": ""} # TODO: relevanten Code übergeben
        )
        if "[ERR]" in code_result:
            print(f"❌ Workflow abgebrochen in Phase 4 (Execution): {code_result}")
            return
            
        print("\n--- Generierter Code ---")
        print(code_result)
        # Hier würde normalerweise der Code auf die Festplatte geschrieben (Dry Run)
        
        approval = self._ask_approval("Code-Generierung")
        if approval["action"] != "approve":
            print("❌ Workflow vom Benutzer abgebrochen.")
            return

        # PHASE 5: VERIFY
        print("\nPHASE 5: VERIFY")
        test_result = await self.loop.step(query="Führe die Verifizierungs-Tests aus")
        if "[ERR]" in test_result:
            print(f"❌ Workflow abgebrochen in Phase 5 (Verify): {test_result}")
            return

        print(f"Testergebnisse: {test_result}")
        if "passed" not in test_result.lower():
            print("🔥 Tests fehlgeschlagen. Breche den Workflow ab.")
            return

        # PHASE 6: COMMIT (Placeholder)
        print("\nPHASE 6: COMMIT")
        print("✅ Alle Phasen erfolgreich. Code würde jetzt committet werden.")


    # =========================================================================
    # PARALLELE VALIDIERUNG (Critic)
    # =========================================================================

    # Grammar-constrained decoding (Ollama format → GBNF): zwingt den Critic in
    # valides JSON mit verdict ∈ {green,yellow,red}. Killt "Validator-Format unklar"
    # an der Wurzel — die choose-Heuristik (_classify_validator_first_line) wird Fallback.
    _CRITIC_SCHEMA = {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["green", "yellow", "red"]},
            "issues": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        "required": ["verdict"],
    }

    def _start_validation(self, phase_name: str, output: str, context: str) -> concurrent.futures.Future:
        """Startet Validator im Hintergrund. Gibt Future zurück (nicht blockierend)."""
        def _run() -> str:
            validator_prompt = f"""Du bist ein adversarialer Reviewer. Deine EINZIGE Aufgabe: finde, was schiefgehen kann.

KONTEXT:
{context}

ZU REVIEWEN ({phase_name}):
{output}

Antworte AUSSCHLIESSLICH als JSON in genau dieser Form:
{{"verdict": "green", "issues": []}}

- verdict: "green" = nichts Konkretes zu bemängeln; "yellow" = Bedenken; "red" = ernstes Problem
- issues: 0-3 KONKRETE Kritikpunkte als Strings (leeres Array wenn green)
- VERBOTEN: den Input oben abschreiben, paraphrasieren oder zusammenfassen
- VERBOTEN: Floskeln ("gut/korrekt/implementiert", PEP-8/Best-Practice-Lyrik)
- Unsicher oder nichts Konkretes → {{"verdict": "green", "issues": []}}

GUTE Kritikpunkte (so):
- "Annahme dass GitHub API ohne Auth nutzbar — bei >60 req/h hard limit"
- "Plan erwähnt 'vibelike.py' aber Datei existiert nicht im Projekt"
- "Tests behaupten 'race conditions abgedeckt' aber kein Concurrency-Test im Plan"

SCHLECHTE Kritikpunkte (nicht so):
- "Implementiert Error-Handling mit try-except"   ← Beschreibung, keine Kritik
- "### PLAN: 1. Dateien... 2. Tests..."          ← Plan abgeschrieben, sofort STOP
- "Folgt PEP 8 Style"                            ← Floskel
"""
            return self.validator_qwen.generate(validator_prompt, temperature=0.4,
                                                fmt=self._CRITIC_SCHEMA)

        return self._executor.submit(_run)

    def _strip_regurgitation(self, validator_output: str, reviewed: str) -> str:
        """Erkennt Echo (Validator schreibt Input ab) und ersetzt durch Verdict + Marker.

        Whitespace-normalisierte Substring-Suche. Bei Echo:
          - Behalte ersten Satz (bis . ! ?) als Verdict-Zeile
          - Ersetze Rest mit '[Echo unterdrückt]'
        """
        if not validator_output or not reviewed:
            return validator_output

        # Echo-Detection (Whitespace + Markdown normalisiert) UND Wort-Overlap.
        # Substring-Check fängt exakte Echos, Wort-Overlap fängt leicht
        # paraphrasierte Echos (1.5b-Modell entfernt manchmal **/`*` etc).
        def normalize_strict(s):
            """Whitespace, Markdown-Symbole, Backticks weg."""
            s = re.sub(r"[*`_~]", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def significant_words(s):
            """Wörter ≥5 Zeichen ODER *.py-Dateinamen (case-insensitive)."""
            return set(re.findall(r"\w+\.py|\w{5,}", s.lower()))

        reviewed_norm = normalize_strict(reviewed)
        val_norm = normalize_strict(validator_output)

        echo_detected = False

        # 1. Substring-Check auf normalisiertem Text (≥60 chars Chunk)
        if len(reviewed_norm) >= 60:
            for i in range(0, len(reviewed_norm) - 60, 30):
                chunk = reviewed_norm[i:i+60]
                if chunk in val_norm:
                    echo_detected = True
                    break

        # 2. Wort-Overlap (fängt paraphrasierte Echos)
        if not echo_detected:
            val_words = significant_words(val_norm)
            if len(val_words) >= 5:  # nur prüfen bei genug Wörtern
                rev_words = significant_words(reviewed_norm)
                overlap = len(val_words & rev_words) / len(val_words)
                if overlap > 0.6:  # >60% bedeutender Wörter aus reviewed
                    echo_detected = True

        # 3. Markdown-Header in Folge-Zeilen → Plan-Echo
        lines = validator_output.splitlines()
        if not echo_detected:
            for line in lines[1:]:
                stripped = line.lstrip()
                if stripped.startswith(("### ", "## ", "#### ", "**")) and len(stripped) > 8:
                    echo_detected = True
                    break

        def first_sentence(text: str, max_chars: int = 200) -> str:
            """Erste Sinneinheit: bis zum ersten . ! ? (mindestens 20 chars rein)."""
            text = text.strip()
            for sep in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
                idx = text.find(sep)
                if 20 < idx < max_chars:
                    return text[:idx + 1].rstrip()
            # Fallback: harter Cut an Wortgrenze
            if len(text) <= max_chars:
                return text
            cut = text.rfind(" ", 20, max_chars)
            return text[:cut].rstrip() if cut > 20 else text[:max_chars].rstrip()

        if echo_detected:
            # Verdict-Zeile + Echo-Marker statt halber Text
            partial = f"{first_sentence(validator_output, 200)} [Echo unterdrückt]"
        else:
            # Kein Echo — gesamten Output behalten, nur Defensive-Cap bei 800
            partial = validator_output.strip()
            if len(partial) > 800:
                partial = first_sentence(partial, 800) + " [... gekürzt]"

        partial = partial.strip() or "🟢"

        # Emoji-Normalisierung via `choose` — Predicate-Eskalation
        out_lines = partial.splitlines()
        if out_lines:
            classification = self._classify_validator_first_line(out_lines[0].strip())
            out_lines[0] = self._normalize_first_line(out_lines[0].strip(), classification)
            partial = "\n".join(out_lines)

        return partial

    # ─── choose-basierte Critic-Emoji-Klassifikation ─────────────────────────
    # Erste Integration des `choose`-Atoms: Predicate-Eskalation statt if/elif.
    # Vorteile: deterministisch, testbar isoliert, Undecidable-Case explizit.

    _NEGATIVE_PREFIXES = ("❌", "✗", "🚫", "⛔", "💥")
    _WARNING_PREFIXES = ("⚠️", "⚠", "❗", "❓", "?")
    _POSITIVE_PREFIXES = ("✅", "✓", "✔", "👍")
    _TRAFFIC_LIGHT_PREFIXES = ("🟢", "🟡", "🔴")

    def _classify_validator_first_line(self, line: str) -> str:
        """Klassifiziert via choose-Atom. Return: predicate-name oder 'unknown'."""
        from choose import choose, Predicate, PredicateBundle, Verdict, Decided

        def _accepts(prefixes):
            return lambda candidate: (
                Verdict.ACCEPT if candidate.startswith(prefixes) else Verdict.DEFER
            )

        predicates = [
            # Wenn schon korrekt formatiert: cheap erst raussortieren
            Predicate(name="traffic_light", evaluate=_accepts(self._TRAFFIC_LIGHT_PREFIXES), cost_hint=1),
            Predicate(name="positive",      evaluate=_accepts(self._POSITIVE_PREFIXES),      cost_hint=10),
            Predicate(name="negative",      evaluate=_accepts(self._NEGATIVE_PREFIXES),      cost_hint=10),
            Predicate(name="warning",       evaluate=_accepts(self._WARNING_PREFIXES),       cost_hint=10),
        ]
        bundle = PredicateBundle(predicates)
        result = choose(bundle, candidates=[line])

        if isinstance(result.outcome, Decided):
            return result.deciding_predicate
        return "unknown"

    def _extract_traffic_light(self, text: str) -> str:
        """Findet die Ampel-Aussage in einem Analyse-Text via choose.

        Multi-Kandidaten: jede Zeile ist ein Kandidat.
        Predicate-Priorität: 🟢 > 🔴 > 🟡 — die erste Zeile, die das
        höchst-priorisierte Emoji enthält, gewinnt. Wenn keine Zeile eine
        Ampel enthält → Undecidable → konservativer Default 🟡.

        Returns: '🟢' | '🟡' | '🔴'
        """
        from choose import choose, Predicate, PredicateBundle, Verdict, Decided

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return "🟡"

        def _contains(emoji):
            return lambda line: Verdict.ACCEPT if emoji in line else Verdict.DEFER

        predicates = [
            Predicate(name="green",  evaluate=_contains("🟢"), cost_hint=1),
            Predicate(name="red",    evaluate=_contains("🔴"), cost_hint=2),
            Predicate(name="yellow", evaluate=_contains("🟡"), cost_hint=3),
        ]
        bundle = PredicateBundle(predicates)
        result = choose(bundle, candidates=lines)

        if isinstance(result.outcome, Decided):
            return {"green": "🟢", "red": "🔴", "yellow": "🟡"}[result.deciding_predicate]
        return "🟡"  # Undecidable → konservativer Default

    def _normalize_first_line(self, line: str, classification: str) -> str:
        """Transformiert die erste Validator-Zeile in 🟢/🟡/🔴-Format."""
        if classification == "traffic_light":
            return line  # schon korrekt
        if classification == "positive":
            return "🟢"
        if classification == "negative":
            stripped = line.lstrip("❌✗🚫⛔💥 ").strip()
            return f"🔴 {stripped}" if stripped else "🔴 Validator-Output unverständlich (Format-Verstoß)"
        if classification == "warning":
            stripped = line.lstrip("⚠️⚠❗❓? ").strip()
            return f"🟡 {stripped}" if stripped else "🟡 Validator unsicher"
        # unknown — Undecidable-Pfad
        return f"🟡 Validator-Format unklar: {line[:80]}"

    def _render_validation(self, validation_future: concurrent.futures.Future,
                             reviewed: str = "") -> str:
        """Holt Validator-Ergebnis ab, filtert Regurgitation, rendert es."""
        print("\n[🔍 Validator läuft parallel...]")
        try:
            result = validation_future.result(timeout=300)
        except Exception as e:
            result = f"[Validator-Fehler: {e}]"

        # Primär: schema-gezwungenes JSON rendern (verdict→Emoji). Fällt das aus
        # (kein valides JSON), greift der Heuristik-Pfad mit Echo-Unterdrückung.
        is_err = result.startswith("[Validator-Fehler")
        rendered = None if is_err else self._render_critic_json(result)
        if rendered is not None:
            result = rendered
        elif reviewed and result and not is_err:
            result = self._strip_regurgitation(result, reviewed)

        print("\n" + "─"*70)
        print("🔍 PARALLELE VALIDIERUNG (unabhängiger Critic)")
        print("─"*70)
        print(result)
        print("─"*70)
        return result

    def _render_critic_json(self, raw: str):
        """Rendert den schema-gezwungenen JSON-Critic zu '🟢'/'🟡 <issue>'-Format.

        Return: gerenderter String, oder None wenn raw kein valides Critic-JSON ist
        (→ Aufrufer nutzt den Heuristik-Fallback).
        """
        try:
            m = re.search(r"\{.*\}", raw or "", re.DOTALL)
            data = json.loads(m.group(0)) if m else None
        except Exception:
            data = None
        if not isinstance(data, dict) or "verdict" not in data:
            return None
        emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(str(data["verdict"]).lower())
        if not emoji:
            return None
        issues = [str(i).strip() for i in (data.get("issues") or []) if str(i).strip()]
        if emoji == "🟢" or not issues:
            return emoji
        return "\n".join([f"{emoji} {issues[0]}"] + issues[1:3])

    # =========================================================================
    # USER-INTERAKTION (Approval + Feedback-basiertes Regenerieren)
    # =========================================================================

    # ─── choose-basierte Approval-Klassifikation ─────────────────────────────
    # Predicate-Eskalation für User-Input. ACCEPT/REJECT/DEFER ist hier
    # explizit: 'unknown' (alle Defer) führt zur Wiederholung, nicht zu
    # stillem Default.

    _APPROVE_VARIANTS = frozenset({"ja", "yes", "y", "j"})
    _REJECT_VARIANTS = frozenset({"nein", "no", "n"})
    _CHANGE_PATTERN = re.compile(r"^(änderung\w*|ä|a)([:.\s]|$)", re.IGNORECASE)
    _CHANGE_EXTRACT = re.compile(r"^(änderung\w*|ä|a)\s*[:.\s]\s*(.*)$", re.IGNORECASE)

    def _classify_approval_input(self, raw: str) -> str:
        """Klassifiziert User-Approval-Input via choose.

        Returns: 'approve' | 'reject' | 'change' | 'unknown'
        """
        from choose import choose, Predicate, PredicateBundle, Verdict, Decided

        low = raw.lower().strip()

        def _exact_match(values):
            return lambda candidate: (
                Verdict.ACCEPT if candidate in values else Verdict.DEFER
            )

        def _change_match(candidate):
            return Verdict.ACCEPT if self._CHANGE_PATTERN.match(candidate) else Verdict.DEFER

        predicates = [
            # Cheap exact-string-matches zuerst
            Predicate(name="approve", evaluate=_exact_match(self._APPROVE_VARIANTS), cost_hint=1),
            Predicate(name="reject",  evaluate=_exact_match(self._REJECT_VARIANTS),  cost_hint=1),
            # Teurer: regex-basierte Change-Erkennung
            Predicate(name="change",  evaluate=_change_match, cost_hint=10),
        ]
        bundle = PredicateBundle(predicates)
        result = choose(bundle, candidates=[low])

        if isinstance(result.outcome, Decided):
            return result.deciding_predicate
        return "unknown"

    def _extract_change_text(self, raw: str) -> str:
        """Extrahiert Inline-Text nach 'änderungen:' (Original-Case bewahrt)."""
        m = self._CHANGE_EXTRACT.match(raw)
        return m.group(2).strip() if m else ""

    def _ask_approval(self, what: str) -> dict:
        """Fragt User nach Approval. Unterstützt inline-Feedback: 'änderungen: <text>'.

        Returns dict with action: 'approve' | 'reject' | 'change' (+ 'changes' on change).
        Nutzt `choose` für die Eingabe-Klassifikation: ACCEPT/REJECT/DEFER,
        Undecidable führt zur expliziten Wiederholung (kein silent fallthrough).
        """
        while True:
            raw = input(f"\n👤 {what} ok? (ja/nein/änderungen): ").strip()
            action = self._classify_approval_input(raw)

            if action == "approve":
                return {"action": "approve"}
            if action == "reject":
                return {"action": "reject"}
            if action == "change":
                inline = self._extract_change_text(raw)
                if inline:
                    return {"action": "change", "changes": inline}
                changes = input(f"Welche Änderungen an der {what}? ").strip()
                if changes:
                    return {"action": "change", "changes": changes}
                print("Keine Änderungen angegeben.")
                continue

            # Undecidable — explizite Wiederholung statt stillem Default
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

    def _retrieve(self, query: str, k: int = 3, max_snippet: int = 500,
                  source_boost: dict = None) -> str:
        """Holt Kontext aus dem Vault (Wikipedia/RFCs/PEPs + eigener Projektcode).

        Standard (source_boost=None): allgemeines CS-Wissen, NICHT als Quelle für
        Datei-/Funktionsnamen nutzen. Mit source_boost={"PROJEKT_SELFCODE": 0.6}
        rankt der per --phase selfcode geharvestete eigene Code oben — dann sind
        Datei-/Funktionsnamen autoritativ (echte Quellen, keine Halluzination).
        """
        if not self.retriever:
            return ""
        try:
            docs, _, _ = self.retriever.search(query, k=k, source_boost=source_boost)
            if not docs:
                return ""
            boosting_selfcode = bool(source_boost
                                     and source_boost.get("PROJEKT_SELFCODE", 1.0) < 1.0)
            if boosting_selfcode:
                lines = [
                    "📂 SEMANTISCH RELEVANTER PROJEKTCODE (Vektor-Retrieval, echte Quellen):",
                    "(Autoritativ für Datei-/Funktionsnamen — ergänzt die voll geladenen Dateien)",
                ]
            else:
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

    # Typ-spezifische Briefing-Framings: jeder Task-Typ kriegt eine eigene
    # Rolle + Sektionsstruktur + Abschluss-Header. Nur ANALYSIS/EXPLAIN haben
    # den "## ERKENNTNISSE"-Block (den _split_analysis_synthesis braucht).
    _BRIEFING_FRAMINGS: dict[str, dict[str, str]] = {
        "ANALYSIS": {
            "role": "Du bist ein Senior Code-Architekt. Analysiere diese Aufgabe.",
            "body": """Antworte mit einer Analyse in ZWEI Teilen. BEIDE Teile sind PFLICHT — die
Detailanalyse (Teil A) MUSS vor der Synthese (Teil B) stehen.

## TEIL A — DETAILANALYSE (6 Sektionen, alle ausfüllen)

1. Verstehen Sie die Aufgabe korrekt?
2. Welche KONKRETEN Dateien (aus der Liste oben!) sind betroffen?
3. Wie passt es ins bestehende System? (echte Klassen/Funktionen aus der Übersicht)
4. Gibt es Abhängigkeiten oder Konflikte?
5. Welche Risiken sehen Sie?
6. **Was ist DISTINKT an diesem Projekt?** Nenne 1-2 Patterns oder Module
   die du in anderen Codebases selten siehst — mit Code-Zitat aus dem
   Star-File. Wenn nichts auffällt, schreib "nichts ungewöhnlich".

## TEIL B — Schließe AM ENDE mit GENAU dieser Header-Zeile ab:

## ERKENNTNISSE

**TL;DR:**
- [3-5 Stichpunkte mit den wichtigsten Befunden, je 1 Zeile]

**Kernerkenntnisse:**
[Was ist konkret und nicht-offensichtlich? Keine Floskeln.]

**Empfohlene nächste Schritte:**
- [konkrete, umsetzbare Actions — keine "sorgfältig prüfen"-Floskeln]
- [nenne Datei + Funktion wenn relevant]

**Offene Fragen:**
- [was konntest du nicht beantworten? Welche Info fehlt?]

WICHTIG: Teil A zuerst (alle 6 Sektionen), dann Teil B mit "## ERKENNTNISSE".""",
        },
        "IMPLEMENTATION": {
            "role": "Du bist ein Senior Software-Engineer und planst eine CODE-ÄNDERUNG.",
            "body": """Liefere ein präzises Umsetzungs-Briefing. KEINE Analyse-Synthese,
KEIN ERKENNTNISSE-Block — du bereitest eine Implementierung vor.

1. **Ziel:** Was genau soll am Ende funktionieren? (1-2 Sätze)
2. **Betroffene Dateien:** Welche existierenden Dateien (aus der Liste!) werden
   geändert, welche NEU angelegt? Pro Datei: was ändert sich.
3. **Einbettung:** An welche existierenden Klassen/Funktionen dockt es an?
   (echte Namen aus der Übersicht)
4. **Abhängigkeiten & Konflikte:** Was könnte brechen? Imports, Signaturen, Aufrufer.
5. **Risiken & Edge-Cases:** Worauf bei der Umsetzung achten?

Schließe mit:
## UMSETZUNGS-SKIZZE
- [3-5 konkrete Schritte in Reihenfolge — je Datei:Funktion]""",
        },
        "BUG_FIX": {
            "role": "Du bist ein erfahrener Debugging-Engineer und behebst einen BUG.",
            "body": """Fokus: Ursache finden, kleinstmöglicher Fix. KEIN neues Feature,
KEINE Analyse-Synthese, KEINE Umbauten über den Fix hinaus.

1. **Symptom:** Was geht schief? (1 Satz, aus der Aufgabe abgeleitet)
2. **Vermutete Fehlerstelle:** Welche Datei:Funktion (aus der Liste/Übersicht)?
   Begründe anhand des geladenen Codes.
3. **Root-Cause-Hypothese:** WARUM passiert der Fehler? Konkrete Zeile/Logik benennen.
4. **Minimaler Fix:** Kleinste Änderung die das Symptom behebt.
5. **Regressions-Risiko:** Was könnte der Fix kaputt machen? Was muss getestet werden?

Schließe mit:
## FIX-ANSATZ
- Datei:Funktion + 1-2 Zeilen was konkret geändert wird""",
        },
        "REFACTOR": {
            "role": "Du bist ein Senior-Engineer und planst ein REFACTORING.",
            "body": """Verhalten bleibt IDENTISCH, nur die Struktur ändert sich.
KEIN neues Feature, KEINE Verhaltensänderung.

1. **Ist-Struktur:** Wie ist der relevante Code aktuell organisiert? (echte Namen)
2. **Soll-Struktur:** Was wird extrahiert / zusammengelegt / umbenannt?
3. **Verhaltens-Invarianten:** Was darf sich NICHT ändern? (öffentliche Signaturen,
   Rückgabewerte, Seiteneffekte)
4. **Betroffene Aufrufer:** Wer nutzt den Code? Was muss mitgezogen werden?
5. **Risiken:** Wo droht versehentliche Verhaltensänderung?

Schließe mit:
## REFACTOR-SKIZZE
- [Schritte in sicherer Reihenfolge — je Datei:Funktion]""",
        },
    }

    def _briefing_framing(self, task_type: str) -> dict[str, str]:
        """Wählt Rolle + Sektionsstruktur für den Briefing-Prompt.

        EXPLAIN teilt sich das ANALYSIS-Framing (beide reine Wissens-Outputs),
        unbekannte Typen fallen auf IMPLEMENTATION zurück.
        """
        if task_type == "EXPLAIN":
            task_type = "ANALYSIS"
        return self._BRIEFING_FRAMINGS.get(task_type, self._BRIEFING_FRAMINGS["IMPLEMENTATION"])

    def phase_briefing(self, task: str, task_type: str = "IMPLEMENTATION") -> dict:
        """Phase 1: Analyse der Aufgabe + ECHTER PROJEKTCODE.

        task_type steuert das Briefing-Framing (Rolle + Sektionen + Abschluss):
        ANALYSIS/EXPLAIN liefern eine Synthese mit ## ERKENNTNISSE, die
        Code-schreibenden Typen (IMPLEMENTATION/BUG_FIX/REFACTOR) liefern eine
        umsetzungsorientierte Skizze.
        """
        print("\n" + "="*70)
        print("PHASE 1: BRIEFING")
        print("="*70)
        print(f"\n📝 Aufgabe: {task}\n")

        # Sammle Projektinfo + ECHTEN CODE (gegen Halluzinationen)
        project_info = self._gather_project_info()
        print("[📂 Lese Projektcode...]")
        code_overview = self._extract_code_overview()
        focused_files = self._read_focused_files(task)
        authoritative = self._authoritative_file_list()
        print(f"   Übersicht: {code_overview.count('📄')} Dateien strukturiert")
        print(f"   Volle Inhalte: {focused_files.count('═══')//2} Dateien gelesen\n")

        # MONOLITH: unveränderlicher Projekt-Anker, IMMER (alle Task-Typen) als
        # Fundament oben im Prompt — erdet das Modell über Invarianten, vendored
        # Engine (Black-Box) und das 'Warum', bevor es Code sieht.
        monolith = self._load_monolith()
        monolith_block = (f"\n═══════════════════════════════════════════════════════════════════\n"
                          f"📜 PROJEKT-FUNDAMENT (MONOLITH — unveränderliche Grundlage):\n"
                          f"═══════════════════════════════════════════════════════════════════\n"
                          f"{monolith}\n") if monolith else ""
        if monolith:
            print(f"[📜 MONOLITH geladen: {monolith.count(chr(10))+1} Zeilen]\n")

        # ANALYSIS/EXPLAIN: semantisch relevante eigene Code-Chunks aus dem Vault
        # (Selfcode-Harvest), Projektcode geboostet. Ergänzt die keyword-basierten
        # focused_files um function-level Treffer, die der Keyword-Match verfehlt.
        selfcode_ctx = ""
        if task_type in ("ANALYSIS", "EXPLAIN"):
            selfcode_ctx = self._retrieve(task, k=5,
                                          source_boost={"PROJEKT_SELFCODE": 0.6})
            if selfcode_ctx:
                print("[🔎 Semantisch relevanter Projektcode aus Vault geholt]\n")
        selfcode_block = (f"\nSEMANTISCH RELEVANTER PROJEKTCODE (Vektor-Retrieval):\n"
                          f"{selfcode_ctx}\n") if selfcode_ctx else ""

        # Typ-spezifisches Framing (Rolle + Sektionen + Abschluss)
        framing = self._briefing_framing(task_type)

        # Qwen analysiert — Authoritative File List ZUERST + ZULETZT (Sandwich)
        analysis_prompt = f"""{framing['role']}

═══════════════════════════════════════════════════════════════════
🚨 VERBINDLICHE DATEILISTE — DAS SIND DIE EINZIGEN EXISTIERENDEN .py DATEIEN:
═══════════════════════════════════════════════════════════════════
{authoritative}

⚠️  Jeder andere Dateiname (z.B. "workflow_manager.py", "vibelike.py", "plugin_manager.py")
    ist eine HALLUZINATION und macht deine Analyse unbrauchbar.
═══════════════════════════════════════════════════════════════════
{monolith_block}
AUFGABE:
{task}

PROJEKTSTRUKTUR (Metadata):
{json.dumps(project_info, indent=2, default=str)}

CODE-ÜBERSICHT (AST-extrahiert):
{code_overview}

VOLLER CODE relevanter Dateien:
{focused_files}
{selfcode_block}
═══════════════════════════════════════════════════════════════════
🚨 ERINNERUNG — verwende NUR diese Dateinamen:
{authoritative}
═══════════════════════════════════════════════════════════════════

{framing['body']}

═══════════════════════════════════════════════════════════════════
🚨 Wenn du eine Datei nennst die nicht in der Liste oben steht — STOP, prüfe nochmal.
═══════════════════════════════════════════════════════════════════"""

        print("[🤖 Qwen analysiert (mit ECHTEM Code)...]\n")
        analysis = self.analyzer_qwen.generate(analysis_prompt, temperature=0.3, stream=True)

        # Parallel: Validator startet, nachdem Stream fertig ist
        validation_future = self._start_validation("BRIEFING", analysis, f"AUFGABE: {task}")

        # Validation einsammeln (User-Lesezeit überlappt mit Validator-Run)
        validation = self._render_validation(validation_future, reviewed=analysis)

        # Anti-Halluzinations-Check: erfundene Dateinamen in der Analyse?
        hallucinated = self._detect_hallucinated_files(analysis)
        if hallucinated:
            print("\n" + "🔴"*35)
            print("🔴 HALLUZINATIONS-WARNUNG: Briefing erwähnt nicht-existente Dateien:")
            for fname in hallucinated:
                print(f"🔴   - {fname}")
            print("🔴 → Bei nächster Phase mit 'änderungen' korrigieren lassen!")
            print("🔴"*35)

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
        authoritative = self._authoritative_file_list()

        feedback_history: list[str] = []
        previous_strategy = ""
        max_iterations = 3

        for iteration in range(1, max_iterations + 1):
            feedback_block = self._build_feedback_block(
                feedback_history, previous_strategy, "Strategie"
            )

            strategy_prompt = f"""Du bist ein Senior Software-Architekt. Erstelle eine STRATEGISCHE Planung für die Aufgabe.

═══════════════════════════════════════════════════════════════════
🎯 ZIEL (UNVERHANDELBAR — wird im Plan-Check verifiziert):
{briefing['task']}
═══════════════════════════════════════════════════════════════════
⚠️  KEINE ZIEL-SUBSTITUTION. Wenn das Ziel eine konkrete kleine
    Aufgabe nennt (z.B. "einen Check ergänzen"), plane GENAU DAS —
    nicht eine umfassende Architektur-Initiative "stattdessen".
⚠️  Die Schlüsselbegriffe aus der Aufgabe MÜSSEN in der Strategie
    wörtlich auftauchen. Skalierung, Plattform, "Infrastruktur" sind
    KEINE gültigen Ersatzziele.
═══════════════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════════════
🚨 VERBINDLICHE DATEILISTE — DAS SIND DIE EINZIGEN EXISTIERENDEN .py DATEIEN:
═══════════════════════════════════════════════════════════════════
{authoritative}

⚠️  Jeder andere Dateiname (z.B. "workflow_manager.py", "vibelike.py") = HALLUZINATION.
═══════════════════════════════════════════════════════════════════
{feedback_block}
ANALYSE (aus Briefing):
{briefing['analysis']}

CODE-ÜBERSICHT:
{code_overview}

{retrieval_ctx}

Diese Phase ist HIGH-LEVEL - noch KEINE konkreten Dateien/Funktionen.
WICHTIG: Wenn du Dateinamen erwähnst, ausschließlich aus der Liste oben.

Beantworte:
1. ANSATZ: Welche grundsätzliche Strategie? (z.B. neuer Service, Erweiterung, Refactoring)
2. ARCHITEKTUR: Welche Komponenten/Pattern verwenden? (z.B. Plugin-System, Adapter, Decorator)
3. ALTERNATIVEN: Welche Alternativen gibt es? Warum diese Wahl?
4. TRADE-OFFS: Vor- und Nachteile des gewählten Ansatzes
5. ABHÄNGIGKEITEN: Welche externen Libraries/APIs nötig?
6. RISIKEN: Was könnte schiefgehen? (technisch & inhaltlich)
7. AUFWAND: Grob - Stunden? Tage? Wochen?

Format: Strukturiert, aber NICHT zu detailliert. Konzentriere dich auf das WAS und WARUM, noch nicht auf das WIE.

═══════════════════════════════════════════════════════════════════
🎯 ERINNERUNG — das Ziel war:
{briefing['task']}
Wenn deine Strategie das nicht direkt adressiert: STOP, du driftest.
═══════════════════════════════════════════════════════════════════"""

            label = f"Strategie (Iter {iteration}, NEU mit Feedback)" if feedback_history else "Strategie"
            print(f"\n[🤖 Qwen entwickelt {label}...]\n")
            strategy = self.analyzer_qwen.generate(strategy_prompt, temperature=0.2, stream=True)

            # Parallel: Validator startet
            validation_future = self._start_validation(
                "PLANNING-STRATEGIE",
                strategy,
                f"BRIEFING-ANALYSE:\n{briefing['analysis']}"
            )
            validation = self._render_validation(validation_future, reviewed=strategy)

            # Anti-Halluzinations-Check
            hallucinated = self._detect_hallucinated_files(strategy)
            if hallucinated:
                print("\n" + "🔴"*35)
                print("🔴 HALLUZINATIONS-WARNUNG: Strategie erwähnt nicht-existente Dateien:")
                for fname in hallucinated:
                    print(f"🔴   - {fname}")
                print("🔴 → Empfehlung: 'änderungen' mit Hinweis auf echte Dateinamen")
                print("🔴"*35)

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
        authoritative = self._authoritative_file_list()

        feedback_history: list[str] = []
        previous_plan = ""
        max_iterations = 3

        for iteration in range(1, max_iterations + 1):
            feedback_block = self._build_feedback_block(
                feedback_history, previous_plan, "Detail-Plan"
            )

            detail_prompt = f"""Du bist ein Senior Software Engineer. Erstelle den DETAILLIERTEN Durchführungsplan
basierend auf der genehmigten Strategie.

═══════════════════════════════════════════════════════════════════
🎯 ZIEL (UNVERHANDELBAR — wird im Plan-Check verifiziert):
{briefing['task']}
═══════════════════════════════════════════════════════════════════
⚠️  KEINE ZIEL-SUBSTITUTION. Wenn das Ziel eine konkrete Prüfung
    (z.B. "None-Vergleiche flaggen") nennt, plane GENAU DIESE — nicht
    eine andere Sicherheits-/Qualitäts-Prüfung "stattdessen".
⚠️  Die Schlüsselbegriffe aus der Aufgabe MÜSSEN im Plan wörtlich
    auftauchen. Sonst ist der Plan ungültig.
═══════════════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════════════
🚨 VERBINDLICHE DATEILISTE — DAS SIND DIE EINZIGEN EXISTIERENDEN .py DATEIEN:
═══════════════════════════════════════════════════════════════════
{authoritative}

⚠️  Modifikationen → NUR diese Dateien. Neue Dateien → mit Begründung anlegen.
⚠️  Jeder andere als-existierend behauptete Dateiname = HALLUZINATION.
═══════════════════════════════════════════════════════════════════
{feedback_block}
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

Format: Strukturierter Plan, lesbar wie eine TODO-Liste. Sei präzise.

═══════════════════════════════════════════════════════════════════
🎯 ERINNERUNG — das Ziel war:
{briefing['task']}
Wenn dein Plan das nicht direkt umsetzt: STOP, du driftest.
═══════════════════════════════════════════════════════════════════"""

            label = f"Detail-Plan (Iter {iteration}, NEU mit Feedback)" if feedback_history else "Detail-Plan"
            print(f"\n[🤖 Qwen erstellt {label}...]\n")
            plan = self.analyzer_qwen.generate(detail_prompt, temperature=0.1, stream=True)

            # Parallel: Validator startet
            validation_future = self._start_validation(
                "PLANNING-DETAIL",
                plan,
                f"AUFGABE: {briefing['task']}\n\nGENEHMIGTE STRATEGIE:\n{strategy['strategy']}"
            )
            validation = self._render_validation(validation_future, reviewed=plan)

            # Deterministischer Plan-Check (Struktur + Spezifität)
            plan_report = self.static_validator.validate_plan(plan, plan_kind="detail")
            if plan_report.findings:
                print("\n" + "─"*70)
                print("🔧 STATIC PLAN-CHECK (deterministisch)")
                print("─"*70)
                print(plan_report.render())
                print("─"*70)

            # Anti-Halluzinations-Check
            hallucinated = self._detect_hallucinated_files(plan, exclude_new_section=True)
            if hallucinated:
                print("\n" + "🔴"*35)
                print("🔴 HALLUZINATIONS-WARNUNG: Detail-Plan erwähnt nicht-existente Dateien:")
                for fname in hallucinated:
                    print(f"🔴   - {fname}")
                print("🔴 → Empfehlung: 'änderungen' mit Hinweis auf echte Dateinamen")
                print("🔴"*35)

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
                "hallucinated_files": list(hallucinated) if hallucinated else [],
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

    # Stabiler Codegen-Instruktions-Block — identisch über alle Codegen-Calls
    # (Execution + Retries) → geht als gecachter cache_prefix in generate().
    _CODEGEN_INSTRUCTIONS = """Du bist ein Experten-Code-Generator. Implementiere basierend auf der ORIGINALAUFGABE und dem PLAN im User-Input.

ANFORDERUNGEN:
1. Schreib produktionsreife Code
2. Folge dem bestehenden Coding-Style
3. Inkludiere Error-Handling
4. Schreib Tests (pytest-Format)
5. Kommentiere nur wenn nötig

OUTPUT-FORMAT:

Für jede BESTEHENDE Datei (im User-Input unter "BESTEHENDE DATEIEN" gezeigt)
schreibst du einen oder mehrere SEARCH/REPLACE-Blocks. Das System
wendet sie auf die Datei an — du musst NICHT die ganze Datei kopieren.

Format pro Block:
## Datei: <pfad>
```python
<<<<<<< SEARCH
<exakter Code-Snippet aus der Datei, byte-genau>
=======
<neuer Code-Snippet>
>>>>>>> REPLACE
```

Regeln:
- SEARCH-Snippet muss genau 1× in der Datei vorkommen (sonst Anchor erweitern).
- Whitespace und Einrückung exakt übernehmen.
- Mehrere Änderungen → mehrere SEARCH/REPLACE-Blocks (auch in einer Datei).

Für NEUE Dateien (nicht gelistet) schreibst du den vollständigen Inhalt:
## Datei: <pfad>
```python
<kompletter Datei-Inhalt>
```

## Tests: <pfad>
```python
<kompletter Test-Inhalt>
```

Generiere kompletten, lauffähigen Code."""

    def _apply_review_patch(self, draft: str, review_out: str) -> tuple:
        """Wendet Claudes SEARCH/REPLACE-Patch-Blocks auf qwens Draft an (in-memory).

        Claude gibt im patch-Fall nur die Diffs aus (kleiner Output = Token-Spar) —
        der volle Datei-Inhalt wird lokal aus dem Draft + Patch rekonstruiert.
        Gibt (gepatchter_draft, anzahl_angewandt) zurück. Schlägt ein SEARCH-Snippet
        nicht an (Whitespace-Mismatch), bleibt der Draft an der Stelle — der Bug wird
        dann von der Verify-Phase (Tests) gefangen.
        """
        pairs = re.findall(
            r"<{5,}\s*SEARCH\s*\n(.*?)\n={5,}\s*\n(.*?)\n>{5,}\s*REPLACE",
            review_out or "", re.DOTALL)
        out, applied = draft, 0
        for search, replace in pairs:
            if search and search in out:
                out = out.replace(search, replace, 1)
                applied += 1
        return out, applied

    def phase_execution(self, briefing: dict, plan: dict) -> dict:
        """Phase 3: Code-Generierung mit Dry-Run + parallelem Code-Reviewer + User-Gate."""
        print("\n" + "="*70)
        print("PHASE 3: EXECUTION (Dry-Run + Code-Review)")
        print("="*70)

        existing_context = self._build_existing_files_context(plan.get("plan", ""))

        # Variabler Teil (Task/Plan/Kontext); der stabile Instruktions-Block geht
        # als gecachter Präfix → Prompt-Caching über Codegen-Retries (Stufe B).
        execution_prompt = f"""ORIGINALAUFGABE:
{briefing['task']}

PLAN:
{plan['plan']}

{existing_context}"""

        # MONOLITH (Invarianten/Engine-Grounding) + Instruktionen als gecachter
        # Präfix: >1024 Tokens → Anthropic cached real über Codegen-Calls einer
        # Session; erdet zugleich den Code-Generator (framework/ tabu etc.).
        codegen_prefix = f"{self._load_monolith()}\n\n{self._CODEGEN_INSTRUCTIONS}"
        if self.reviewer is not None:
            # "Ehrliche Mitte": qwen-coder Draft → Claude Review (bless/refine/rewrite,
            # mit Vollmacht den Draft zu verwerfen → Anti-Anchoring).
            print("[🤖 qwen-coder schreibt Draft...]\n")
            draft = self.qwen.generate(execution_prompt, temperature=0.1, stream=False,
                                       cache_prefix=self._CODEGEN_INSTRUCTIONS)
            print("[🔎 Claude reviewt (bless/patch/rewrite)...]\n")
            review_prompt = (
                f"{execution_prompt}\n\n"
                f"KANDIDATEN-IMPLEMENTIERUNG (von einem kleineren lokalen Modell):\n"
                f"```\n{draft}\n```\n\n"
                f"Prüfe den Kandidaten gegen ORIGINALAUFGABE + PLAN. BEVORZUGE PATCHEN vor Neuschreiben:\n"
                f"- Schon korrekt & vollständig → erste Zeile 'VERDICT: bless', sonst NICHTS weiter.\n"
                f"- ≥50% korrekt (Struktur stimmt, einzelne Bugs) → 'VERDICT: patch', danach NUR "
                f"SEARCH/REPLACE-Blocks für die konkreten Fehler (gegen den Kandidaten-Code oben), "
                f"NICHT die ganze Datei. Format je Fix:\n"
                f"<<<<<<< SEARCH\n<exakter Ausschnitt aus dem Kandidaten>\n=======\n<korrigiert>\n>>>>>>> REPLACE\n"
                f"- <50% korrekt / grundlegend falsch → 'VERDICT: rewrite', danach die korrekte "
                f"Implementierung komplett im ## Datei:-Format.\n"
                f"Erste Zeile EXAKT eine der drei VERDICT-Zeilen."
            )
            review_out = self.reviewer.generate(review_prompt, temperature=0.1, stream=True,
                                                 cache_prefix=codegen_prefix)
            m = re.search(r"VERDICT:\s*(bless|patch|rewrite)", review_out or "", re.IGNORECASE)
            verdict_word = m.group(1).lower() if m else "rewrite"
            if verdict_word == "bless":
                code = draft  # qwens Draft ist schon das Endergebnis — kein Claude-Output nötig
            elif verdict_word == "patch":
                code, n_applied = self._apply_review_patch(draft, review_out)
                print(f"\n[🔧 {n_applied} Patch-Block(e) auf Draft angewandt]")
            else:  # rewrite
                code = review_out
            print(f"[🔎 Review-Verdict: {verdict_word}]")
            if self.current_workflow is not None:
                self.current_workflow.setdefault("mitte", {})["review_verdict"] = verdict_word
        else:
            print("[🤖 Qwen schreibt Code...]\n")
            code = self.qwen.generate(execution_prompt, temperature=0.1, stream=True,
                                      cache_prefix=codegen_prefix)

        # Parse OHNE zu schreiben (Dry-Run)
        planned_changes = self._parse_code(code)

        # SEARCH/REPLACE-Patch-Status (Aider-Stil) berichten
        sr_total = sum(c.get("sr_blocks", 0) for c in planned_changes)
        sr_errors_flat = [
            f"{Path(c['path']).name}: {err}"
            for c in planned_changes for err in c.get("sr_errors", [])
        ]
        if sr_total or sr_errors_flat:
            print(f"\n🩹 PATCH-MODUS: {sr_total} SEARCH/REPLACE-Block(s)")
            if sr_errors_flat:
                print(f"   🔴 {len(sr_errors_flat)} fehlgeschlagene Anchor(s):")
                for e in sr_errors_flat[:8]:
                    print(f"      - {e}")

        # Parallel: LLM-Code-Reviewer startet (nach Stream-Ende)
        review_future = self._start_code_review(code, plan, briefing['task'])

        # Strukturierter Diff
        print(f"\n📦 GEPLANTE ÄNDERUNGEN ({len(planned_changes)} Dateien):")
        print("="*70)
        self._show_diff(planned_changes, full=False)

        # 2-Schichten Validierung: Code + Plan
        static_report = self.static_validator.validate_full(
            planned_changes,
            plan.get("plan", ""),
        )

        print("\n" + "─"*70)
        print("🔧 STATIC VALIDATOR (Code + Plan)")
        print("─"*70)

        if static_report.findings:
            print(f"\n  {len(static_report.findings)} findings")
            for f in static_report.findings[:5]:
                severity_symbol = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(f.severity, "⚪")
                print(f"    {severity_symbol} {f.check:30s} @ {f.location}")
            if len(static_report.findings) > 5:
                print(f"    ... (+{len(static_report.findings)-5} more)")
        else:
            print("  ✅ Keine Findings (sauberer Code & Plan)")

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

        # Regression-Guard: stoppt destruktive Überschreibungen vor dem Write
        regression = self._check_regression(planned_changes, plan.get("plan", ""))
        result["regression_check"] = regression
        if regression["verdict"] != "🟢":
            print("\n" + "="*70)
            print(f"{regression['verdict']} REGRESSION-GUARD")
            print("="*70)
            for issue in regression["issues"]:
                print(f"  {issue['kind']:14s} {Path(issue['file']).name}: {issue['detail']}")
        if regression["verdict"] == "🔴":
            print("\n🛑 HARD-STOP: Regression-Guard hat unautorisierten Symbol-Verlust erkannt.")
            print("   Keine Files geschrieben. Plan + Output prüfen.")
            self.current_workflow["aborted_at"] = "EXECUTION_REGRESSION"
            return result

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

    def phase_verification(self, execution: dict, task_type: str = "IMPLEMENTATION") -> dict:
        """Phase 4: Automatische Test-Verifikation.

        Bei REFACTOR sind grüne Tests der Beweis für Verhaltens-Invarianz —
        fehlende Tests bedeuten dann, dass die Invarianz NICHT bewiesen ist.
        """
        print("\n" + "="*70)
        print("PHASE 4: VERIFICATION")
        print("="*70)

        if task_type == "REFACTOR":
            print("[🔒 REFACTOR — Tests müssen UNVERÄNDERT grün bleiben (Verhaltens-Invarianz)]")

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
                if task_type == "REFACTOR":
                    print("\n✅ ALLE TESTS BESTANDEN — Verhalten unverändert (Invarianz bewiesen)\n")
                else:
                    print("\n✅ ALLE TESTS BESTANDEN (100%)\n")
            else:
                if task_type == "REFACTOR":
                    print("\n🔴 REFACTOR NICHT verhaltensneutral — Tests sind nicht mehr grün:\n")
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
        analysis = self.analyzer_qwen.generate(analysis_prompt, temperature=0.3, stream=True)

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

        # Ampel aus Analyse extrahieren via choose (Multi-Kandidaten über Zeilen).
        # Predicate-Priorität: 🟢 > 🔴 > 🟡 (Heal-Optimismus zuerst, Heal-Pessimismus
        # als zweite Stufe, neutral als drittletzte Option, sonst konservativer 🟡-Default).
        traffic_light = self._extract_traffic_light(analysis)

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

    def _authoritative_file_list(self) -> str:
        """Liste ALLER .py-Dateien im Projekt-Root — als verbindliche Quelle der Wahrheit."""
        files = sorted(p.name for p in self.root.glob("*.py"))
        return "\n".join(f"  - {f}" for f in files)

    def _load_monolith(self) -> str:
        """MONOLITH.md — unveränderlicher Projekt-Anker, in JEDES Briefing geladen.

        Dokumentiert Invarianten, vendored Engine (Black-Box), Architektur,
        Safety-Layer und das 'Warum' fester Entscheidungen. Der Marker
        <!-- ENGINE_SKELETON_AUTO --> wird beim Laden durch ein frisch aus
        framework/ erzeugtes AST-Skelett ersetzt — so kann die Engine-Doku
        nicht von den Quell-Signaturen driften. Gecacht; graceful "" wenn fehlt.
        """
        if self._monolith_cache is not None:
            return self._monolith_cache
        path = self.root / "MONOLITH.md"
        try:
            text = path.read_text(encoding="utf-8") if path.exists() else ""
        except Exception:
            text = ""
        if text:
            marker = "<!-- ENGINE_SKELETON_AUTO -->"
            skeleton = self._build_engine_skeleton()
            if marker in text:
                text = text.replace(marker, skeleton or "(framework/ nicht gefunden)")
            elif skeleton:
                text = f"{text}\n{skeleton}"
        self._monolith_cache = text
        return self._monolith_cache

    def _build_engine_skeleton(self) -> str:
        """Live-AST-Skelett der vendored Engine (framework/quelibrium/).

        Bei jedem MONOLITH-Load frisch erzeugt → kann nicht von den realen
        Klassen/Methoden-Signaturen abweichen (Drift-Check). Nutzt dieselbe
        _extract_skeleton-Logik wie die focused_files.
        """
        fw = self.root / "framework" / "quelibrium"
        if not fw.exists():
            return ""
        blocks: list[str] = []
        for f in sorted(fw.rglob("*.py")):
            if f.name == "__init__.py":
                continue
            skel = self._extract_skeleton(f)
            if not skel or skel.startswith("(no top-level"):
                continue
            rel = f.relative_to(self.root)
            blocks.append(f"── {rel} ──\n{skel}")
        if not blocks:
            return ""
        return "```\n" + "\n\n".join(blocks) + "\n```"

    # ─── choose-basierte Halluzinations-Detektion ─────────────────────────────
    # Per-Datei Predicate-Eskalation: in_root → in_tree → declared_new → REJECT.
    # Undecidable bedeutet hier "hallucinated".

    _NEW_FILES_SECTION_PATTERN = re.compile(
        r"(?:NEUE\s+DATEIEN|NEW\s+FILES)(.*?)"
        r"(?=\n\s*(?:\d+\.\s+)?(?:FUNKTIONEN|FUNCTIONS|"
        r"CODE-?FLOW|TESTS|IMPORTS|INTEGRATION|ROLLBACK|ESTIMATED|####|###|\Z))",
        re.IGNORECASE | re.DOTALL,
    )
    _FILE_MENTION_PATTERN = re.compile(r"\b([a-zA-Z_][\w\-]*\.py)\b")
    _FENCED_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)

    @classmethod
    def _strip_fenced_code(cls, text: str) -> str:
        """Entfernt ```...``` Blöcke — Datei-Erwähnungen darin sind
        Code-Beispiele (z.B. String-Argumente an scan_line('test.py', ...)),
        keine Datei-Claims. Lauf-5-Befund: 'test.py' nur in fenced blocks
        → False-Positive-Hard-Stop verhinderte Phase 3.
        """
        return cls._FENCED_BLOCK_PATTERN.sub("", text or "")

    def _classify_file_mention(self, fname: str, root_files: frozenset,
                                 tree_files: frozenset,
                                 declared_new: frozenset) -> str:
        """Klassifiziert einen Datei-Namen via choose.

        Returns: 'in_root' | 'in_tree' | 'declared_new' | 'hallucinated'
        """
        from choose import choose, Predicate, PredicateBundle, Verdict, Decided

        def _accepts_in(values):
            return lambda candidate: (
                Verdict.ACCEPT if candidate in values else Verdict.DEFER
            )

        predicates = [
            # cheap: direkt im Projekt-Root
            Predicate(name="in_root",      evaluate=_accepts_in(root_files),    cost_hint=1),
            # cheap: irgendwo im Baum (rglob)
            Predicate(name="in_tree",      evaluate=_accepts_in(tree_files),    cost_hint=2),
            # context-aware: als "NEUE DATEIEN" deklariert
            Predicate(name="declared_new", evaluate=_accepts_in(declared_new), cost_hint=10),
        ]
        bundle = PredicateBundle(predicates)
        result = choose(bundle, candidates=[fname])

        if isinstance(result.outcome, Decided):
            return result.deciding_predicate
        return "hallucinated"  # Undecidable → Halluzination

    def _detect_hallucinated_files(self, text: str, exclude_new_section: bool = False) -> list[str]:
        """Findet *.py Namen im Text, die NICHT im Projekt existieren.

        Nutzt `choose` für die Per-Datei-Klassifikation:
        in_root / in_tree / declared_new / hallucinated.

        Args:
            text: Text der durchsucht wird
            exclude_new_section: Wenn True, in NEUE-DATEIEN-Section erwähnte
                Dateien gelten als 'declared_new' (nicht halluziniert).
        """
        root_files = frozenset(p.name for p in self.root.glob("*.py"))
        tree_files = frozenset(p.name for p in self.root.rglob("*.py"))

        # NEUE-DATEIEN-Section noch im Original-Text suchen (vor Fence-Strip)
        declared_new: frozenset[str] = frozenset()
        if exclude_new_section:
            new_section_match = self._NEW_FILES_SECTION_PATTERN.search(text)
            if new_section_match:
                declared_new = frozenset(
                    m.group(1)
                    for m in self._FILE_MENTION_PATTERN.finditer(new_section_match.group(1))
                )

        # Datei-Erwähnungen NUR außerhalb von ```fenced blocks``` zählen
        # (Code-Beispiele enthalten oft 'test.py' o.ä. als String-Argument).
        scan_text = self._strip_fenced_code(text)
        mentioned = {m.group(1) for m in self._FILE_MENTION_PATTERN.finditer(scan_text)}

        # Per Datei klassifizieren via choose
        hallucinated = []
        for fname in sorted(mentioned):
            classification = self._classify_file_mention(
                fname, root_files, tree_files, declared_new
            )
            if classification == "hallucinated":
                hallucinated.append(fname)

        return hallucinated

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

    _TOPIC_FILES = {
        "validator": "validator2.py",
        "classifier": "task_classifier.py",
        "template": "task_classifier.py",
        "terminal": "terminal.py",
        "ui": "terminal.py",
        "choose": "choose/atom.py",
        "predicate": "choose/atom.py",
        "harvest": "harvest.py",
    }

    # MSA-Glied 1: Block-Gate-Schema (grammar-constrained Relevanz-Vote)
    _BLOCK_GATE_SCHEMA = {
        "type": "object",
        "properties": {"blocks": {"type": "array", "items": {
            "type": "object",
            "properties": {"file": {"type": "string"}, "relevant": {"type": "boolean"}},
            "required": ["file", "relevant"]}}},
        "required": ["blocks"],
    }

    def _select_context_blocks(self, task: str, max_files: int = 4) -> list:
        """MSA-Filterstufe: rankt Projektdateien per Retrieval (Tier 0) und siebt
        sie per grammar-gegatetem 1.5b-Vote (Tier 1). ADDITIV — bei Leere/Fehler
        gibt's das Tier-0-Ranking zurück, nie eine leere Liste durch Über-Filtern.
        Returns: rel_path-Liste (z.B. ['terminal.py', 'choose/atom.py']).
        """
        if not self.retriever:
            return []
        try:
            docs, _, _ = self.retriever.search(task, k=8,
                                               source_boost={"PROJEKT_SELFCODE": 0.6})
        except Exception:
            return []
        # Tier 0: rel_path aus Selfcode-IDs, Reihenfolge = Relevanz, dedupe
        ranked: list[str] = []
        for d in docs:
            did = str(d.get("id", ""))
            if not did.startswith("SELFCODE-"):
                continue
            rel = did[len("SELFCODE-"):].split("::", 1)[0]
            if rel and rel not in ranked and (self.root / rel).exists():
                ranked.append(rel)
        ranked = ranked[:max(max_files, 4)]
        if not ranked:
            return []
        # Tier 1: grammar-gegateter Relevanz-Vote (additiv)
        gated = self._gate_blocks(task, ranked)
        return (gated or ranked)[:max_files]

    def _gate_blocks(self, task: str, files: list) -> list:
        """Gebündelter 1.5b-Vote mit hartem Schema. Behält Ranking-Reihenfolge.
        Fehlender Vote → behalten (additiv). Parse-Fehler → [] (Aufrufer nimmt Tier 0)."""
        listing = "\n".join(f"- {f}" for f in files)
        prompt = (f"Aufgabe: {task}\n\nKandidaten-Dateien:\n{listing}\n\n"
                  f"Welche Dateien sind für die Aufgabe relevant? Antworte als JSON "
                  f'{{"blocks":[{{"file":"<exakter Name oben>","relevant":true|false}}]}} '
                  f"— genau ein Eintrag pro Kandidat.")
        try:
            raw = self.validator_qwen.generate(prompt, temperature=0.0,
                                               fmt=self._BLOCK_GATE_SCHEMA)
            m = re.search(r"\{.*\}", raw or "", re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
            votes = {b["file"]: bool(b.get("relevant"))
                     for b in data.get("blocks", []) if isinstance(b, dict) and "file" in b}
        except Exception:
            return []
        # fehlender Vote → True (nie den Schlüssel-Block durch Stille verlieren)
        return [f for f in files if votes.get(f, True)]

    def _read_focused_files(self, task: str,
                            star_budget: int = 6000,
                            skeleton_budget: int = 1200,
                            max_supporting: int = 3) -> str:
        """Ein 'Star-File' in voller Länge + 2-3 Skeleton-Files (Signaturen).

        Topic-Routing: das Schlüsselwort mit dem spezifischsten Treffer wird
        zum Star, der Rest läuft als AST-Skeleton mit (klasse/def + erster
        docstring-Zeile). Default-Star: workflow_agent.py.
        """
        task_lower = task.lower()

        # MSA-Glied 1: semantischer Block-Selektor (Retrieval + grammar-gegateter
        # Vote) wählt Star + Supporting nach Relevanz. ADDITIV — bei leerem
        # Ergebnis fällt es aufs bisherige Keyword-Routing zurück.
        selected: list[str] = []
        if self.block_select_enabled and self.retriever:
            selected = self._select_context_blocks(task, max_files=max_supporting + 1)

        if selected:
            star = selected[0]
            supporting = [f for f in selected[1:max_supporting + 1] if (self.root / f).exists()]
            print(f"[🧱 Block-Selektor: {star}" +
                  (f" + {', '.join(supporting)}" if supporting else "") + "]")
        else:
            # Fallback: Keyword-Routing (Substring > Topic > Default)
            star = "workflow_agent.py"
            for p in self.root.glob("*.py"):
                if p.stem.lower() in task_lower and len(p.stem) > 3:
                    star = p.name
                    break
            else:
                for keyword, fname in self._TOPIC_FILES.items():
                    if keyword in task_lower:
                        star = fname
                        break

            # Supporting NUR Topic-Treffer. KEIN blindes Anhaengen von
            # workflow_agent.py — das hat Briefings in Workflow-Design driften lassen.
            supporting = []
            for keyword, fname in self._TOPIC_FILES.items():
                if keyword in task_lower and fname != star and fname not in supporting:
                    supporting.append(fname)
                    if len(supporting) >= max_supporting:
                        break
            if not supporting and star == "workflow_agent.py":
                for fallback in ("validator2.py", "terminal.py"):
                    if fallback != star and fallback not in supporting:
                        supporting.append(fallback)
                    if len(supporting) >= max_supporting:
                        break

        sections: list[str] = []
        star_path = self.root / star
        if star_path.exists():
            content = star_path.read_text()
            if len(content) > star_budget:
                content = content[:star_budget] + f"\n... [gekürzt — {len(content):,} chars total]"
            sections.append(f"\n═══ {star} (VOLL) ═══\n{content}")

        for fname in supporting:
            f = self.root / fname
            if not f.exists():
                continue
            skeleton = self._extract_skeleton(f)
            if len(skeleton) > skeleton_budget:
                skeleton = skeleton[:skeleton_budget] + "\n... [skeleton gekürzt]"
            sections.append(f"\n═══ {fname} (SKELETON) ═══\n{skeleton}")

        return "\n".join(sections) if sections else ""

    def _extract_skeleton(self, path: Path) -> str:
        """AST-basiertes Skeleton: Klassen + Funktionen + erste docstring-Zeile."""
        try:
            import ast
            tree = ast.parse(path.read_text())
        except Exception:
            return f"(skeleton extraction failed for {path.name})"

        lines: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                doc = (ast.get_docstring(node) or "").split("\n", 1)[0]
                lines.append(f"class {node.name}:" + (f"  # {doc}" if doc else ""))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        sig = self._format_signature(sub)
                        sdoc = (ast.get_docstring(sub) or "").split("\n", 1)[0]
                        lines.append(f"    def {sub.name}{sig}" + (f"  # {sdoc}" if sdoc else ""))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = self._format_signature(node)
                doc = (ast.get_docstring(node) or "").split("\n", 1)[0]
                lines.append(f"def {node.name}{sig}" + (f"  # {doc}" if doc else ""))
        return "\n".join(lines) if lines else "(no top-level classes/functions)"

    @staticmethod
    def _format_signature(func) -> str:
        import ast
        args = [a.arg for a in func.args.args]
        return f"({', '.join(args)})"

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
            _tt = (self.current_workflow or {}).get("task_type", "IMPLEMENTATION")
            new_verification = self.phase_verification(execution, task_type=_tt)

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

    # ─── choose-basierte Best-Attempt-Auswahl (Multi-Kandidaten) ─────────────
    # Erste echte Multi-Candidate-Nutzung: aus N Heal-Iterationen die BESTE
    # picken (statt blind die letzte zu nehmen). Verhindert Regression wenn
    # ein späterer Heal-Cycle den Code schlechter macht als ein früherer.

    def _choose_best_heal_attempt(self, attempts: list[dict]) -> dict:
        """Wählt aus N Heal-Iterationen die qualitativ beste via choose.

        Multi-Kandidaten-Pattern: jede Iteration ist ein Kandidat, Predicates
        eskalieren über Qualitätsstufen. Auf Ties wird der neuere bevorzugt
        (candidates newest-first sortiert).

        Args:
            attempts: list von {"changes": [...], "static": Report, "cycle": int}

        Returns: einer der attempts-Dicts (immer ein gültiger).
        """
        from choose import choose, Predicate, PredicateBundle, Verdict, Decided, Undecidable

        # Newest-first: bei gleichem Verdict gewinnt der neuere Versuch
        candidates = list(reversed(attempts))

        def _verdict_is(target):
            return lambda att: (
                Verdict.ACCEPT if att["static"].verdict == target else Verdict.DEFER
            )

        def _no_high_severity(att):
            return (
                Verdict.ACCEPT
                if not any(f.severity == "high" for f in att["static"].findings)
                else Verdict.DEFER
            )

        predicates = [
            Predicate(name="green_verdict",    evaluate=_verdict_is("🟢"),    cost_hint=1),
            Predicate(name="yellow_verdict",   evaluate=_verdict_is("🟡"),    cost_hint=5),
            Predicate(name="no_high_severity", evaluate=_no_high_severity, cost_hint=10),
        ]
        bundle = PredicateBundle(predicates)
        result = choose(bundle, candidates=candidates)

        if isinstance(result.outcome, Decided):
            return result.outcome.candidate

        # Undecidable: alle Attempts haben 🔴 mit high-severity Findings.
        # Fallback: neuestes (= candidates[0]).
        return candidates[0]

    def _self_heal_execution(self, planned_changes, plan, briefing,
                              static_report, review, max_cycles: int = 2):
        """Mikro-Heal-Loop: bei StaticValidator 🔴 die betroffenen Files vom 7b
        neu generieren lassen, re-validieren. Max N Cycles.

        Nutzt `choose` (Multi-Kandidaten) am Ende: aus allen Iterationen
        wird die qualitativ beste gewählt — verhindert Regression wenn ein
        späterer Cycle den Code schlechter macht als ein früherer.

        Returns: (new_planned_changes, new_static_report, heal_log).
        """
        heal_log = []
        current_changes = list(planned_changes)
        current_static = static_report

        # Track ALL attempts inkl. Original — für choose-basierte Auswahl am Ende
        attempts = [{"changes": list(current_changes),
                     "static": current_static,
                     "cycle": 0}]

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

            # Diese Iteration als Kandidat für choose-basierte Auswahl tracken
            attempts.append({"changes": list(current_changes),
                             "static": current_static,
                             "cycle": cycle})

        # Multi-Kandidaten-Wahl via choose: beste Iteration über alle Cycles
        best = self._choose_best_heal_attempt(attempts)
        if best["cycle"] != attempts[-1]["cycle"]:
            print(f"\n🎯 choose-Auswahl: Iteration #{best['cycle']} ist besser als "
                  f"letzte (#{attempts[-1]['cycle']}) — verwende diese")
            heal_log.append({"chose": best["cycle"],
                             "rejected_latest": attempts[-1]["cycle"],
                             "reason": "earlier iteration scored better"})
        return best["changes"], best["static"], heal_log

    _SR_BLOCK_PATTERN = re.compile(
        r"<{5,}\s*SEARCH\s*\n(.*?)\n={5,}\s*\n(.*?)\n>{5,}\s*REPLACE",
        re.DOTALL,
    )

    @classmethod
    def _extract_sr_blocks(cls, content: str) -> list[tuple[str, str]]:
        """Parst Aider-Stil SEARCH/REPLACE-Blocks aus einem Code-Block."""
        return [
            (m.group(1), m.group(2))
            for m in cls._SR_BLOCK_PATTERN.finditer(content or "")
        ]

    @staticmethod
    def _apply_sr_blocks(original: str, blocks: list[tuple[str, str]]) -> tuple[str, list[str]]:
        """Wendet SR-Blocks sequenziell an. Strict-Match: SEARCH muss exakt 1× vorkommen.
        Returns (new_content, errors).
        """
        text = original
        errors = []
        for i, (search, replace) in enumerate(blocks, 1):
            count = text.count(search)
            if count == 1:
                text = text.replace(search, replace, 1)
            elif count == 0:
                preview = search[:60].replace("\n", "⏎")
                errors.append(f"Block#{i}: SEARCH nicht gefunden — '{preview}…'")
            else:
                errors.append(f"Block#{i}: SEARCH {count}× im Text (ambig) — Anchor zu klein")
        return text, errors

    def _parse_code(self, code: str) -> list:
        """Parse Code-Output, gibt Liste von {path, content, exists} zurück. SCHREIBT NICHT.

        Unterstützt zwei Output-Formate:
        - Vollständiger Datei-Inhalt (für NEUE Dateien)
        - SEARCH/REPLACE-Blocks (für EXISTIERENDE Dateien) — Aider-Stil:
              <<<<<<< SEARCH
              <exact existing snippet>
              =======
              <new snippet>
              >>>>>>> REPLACE
          Wird auf den realen Datei-Inhalt angewendet; sr_errors signalisieren
          nicht-matchende oder ambige Anchors.
        """
        changes = []
        lines = code.split("\n")
        current_file = None
        current_code = []
        in_code_block = False

        def _flush():
            if not current_file:
                return
            path = (self.root / current_file.strip()).resolve()
            content = "\n".join(current_code)
            sr_blocks = self._extract_sr_blocks(content)
            change = {"path": str(path), "exists": path.exists()}
            if sr_blocks:
                if path.exists():
                    original = path.read_text()
                    new_content, sr_errors = self._apply_sr_blocks(original, sr_blocks)
                    change["content"] = new_content
                    change["sr_blocks"] = len(sr_blocks)
                    change["sr_errors"] = sr_errors
                else:
                    change["content"] = content
                    change["sr_blocks"] = len(sr_blocks)
                    change["sr_errors"] = [
                        "SEARCH/REPLACE-Block für nicht-existierende Datei — bitte vollen Inhalt liefern"
                    ]
            else:
                change["content"] = content
            changes.append(change)

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

    def _build_existing_files_context(self, plan_text: str) -> str:
        """Extrahiert in plan_text genannte existierende .py-Dateien und baut
        einen 'BESTEHENDE DATEIEN'-Kontextblock mit vollem Inhalt + Symbol-
        Checkliste. Gibt leeren String zurück wenn keine existieren.

        Notwendig damit der Code-Gen additiv arbeitet statt Mini-Stubs zu
        schreiben (Lauf-3/4-Befund: 650→26/52 Zeilen Destruktion).
        """
        import re as _re
        candidates = set(_re.findall(r"[\w/\.\-]+\.py", plan_text or ""))
        blocks = []
        for rel in sorted(candidates):
            p = (self.root / rel).resolve()
            try:
                p.relative_to(self.root.resolve())
            except ValueError:
                continue
            if not p.is_file():
                continue
            try:
                content = p.read_text()
            except Exception:
                continue
            if len(content) > 60_000:
                continue
            syms = self._top_level_symbols(content)
            sym_line = (
                ", ".join(sorted(syms)) if syms else "(Datei hat aktuell SyntaxError — bitte reparieren)"
            )
            n_lines = len(content.splitlines())
            blocks.append(
                f"### {rel} ({n_lines} Zeilen)\n"
                f"ZU ERHALTENDE SYMBOLE: {sym_line}\n"
                f"```python\n{content}\n```"
            )
        if not blocks:
            return ""
        return (
            "BESTEHENDE DATEIEN (additiv erweitern, NICHT überschreiben):\n"
            + "\n\n".join(blocks)
            + "\n\n"
        )

    @staticmethod
    def _top_level_symbols(content: str):
        import ast
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        names.add(tgt.id)
        return names

    def _check_regression(self, planned_changes: list, plan_text: str) -> dict:
        """Pre-write-Check: erkennt destruktive Überschreibungen existierender Dateien.

        🔴: top-level Symbol-Verlust (Klasse/Funktion/Konstante) ohne explizite
            Plan-Erwähnung mit Entfernungs-Verb.
        🟡: ≥50% Zeilen-Reduktion bei existierender Datei ≥20 Zeilen.
        """
        issues = []
        plan_lower = (plan_text or "").lower()
        removal_verbs = ("remove", "entfern", "löschen", "delete", "wegwerfen")

        for change in planned_changes:
            if not change.get("exists"):
                continue
            path = Path(change["path"])
            try:
                old_content = path.read_text()
            except OSError:
                continue
            new_content = change["content"]
            old_n = len(old_content.splitlines())
            new_n = len(new_content.splitlines())

            if path.suffix == ".py":
                old_syms = self._top_level_symbols(old_content)
                new_syms = self._top_level_symbols(new_content)
                if old_syms is not None and new_syms is not None:
                    lost = old_syms - new_syms
                    unauthorized = {
                        s for s in lost
                        if not (s.lower() in plan_lower
                                and any(v in plan_lower for v in removal_verbs))
                    }
                    if unauthorized:
                        issues.append({
                            "file": str(path),
                            "kind": "symbol_loss",
                            "detail": f"{len(unauthorized)} top-level Symbol(e) verschwunden: "
                                      f"{sorted(unauthorized)[:6]}",
                        })

            if old_n >= 20 and new_n < old_n * 0.5:
                issues.append({
                    "file": str(path),
                    "kind": "size_collapse",
                    "detail": f"{old_n} → {new_n} Zeilen "
                              f"({100*(1-new_n/old_n):.0f}% Reduktion)",
                })

        if not issues:
            return {"verdict": "🟢", "issues": []}
        if any(i["kind"] == "symbol_loss" for i in issues):
            return {"verdict": "🔴", "issues": issues}
        return {"verdict": "🟡", "issues": issues}

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
        """Startet parallelen Code-Reviewer (zweiter Qwen als Critic).

        Übersprungen bei Frontier-Code-Gen (self.code_review_enabled == False):
        ein 1.5b-Modell, das Claude-Code reviewt, produziert nur False-Noise.
        Die deterministischen Guards (Static-Validator, Regression-Guard) bleiben.
        """
        if not self.code_review_enabled:
            return None
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
        if review_future is None:  # bei Frontier-Code-Gen übersprungen
            return ""
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

    # =========================================================================
    # TEMPLATES — Phase-Sequenzen pro Task-Typ
    # =========================================================================

    def _split_analysis_synthesis(self, analysis: str) -> tuple[str, str]:
        """Trennt Haupt-Analyse von der ERKENNTNISSE-Synthese-Section.

        Returns: (main_analysis, synthesis_block)  — synthesis_block ist '' wenn fehlt.
        """
        # Suche '## ERKENNTNISSE' Header — auch wenn am Start des Strings (kein newline davor)
        match = re.search(r"(?:^|\n)#{1,3}\s*ERKENNTNISSE\s*(?:\n|$)", analysis, re.IGNORECASE)
        if not match:
            # Alternative Schreibweisen: **ERKENNTNISSE** als Header
            match = re.search(r"(?:^|\n)\*\*ERKENNTNISSE.*?\*\*\s*(?:\n|$)", analysis, re.IGNORECASE)
        if not match:
            return analysis, ""

        # match.start() ist position des newline (oder 0 wenn am Anfang)
        cut = match.start()
        if analysis[cut:cut+1] == "\n":
            cut += 1  # newline ueberspringen
        return analysis[:cut].rstrip(), analysis[cut:].strip()

    def phase_analysis_report(self, briefing: dict, classification: dict | None = None,
                              write_file: bool = True) -> dict:
        """Phase ANALYSE: Finalisiert das Briefing als strukturierten Analyse-Report.

        Kein Plan, kein Execute — die Analyse IST das Endprodukt.
        Inhalt: Klassifikation, Analyse-Text, Validator-Critique, Halluzinations-Check.
        Code-Übersicht als Anhang am Ende (nicht als Hauptinhalt).
        Speichert Report als Markdown unter logs/analysis-<id>.md.

        write_file=False (EXPLAIN): kein persistiertes Report-Artefakt — die
        Antwort wurde im Briefing-Stream schon ausgegeben, nur Konsolen-Hinweis.
        """
        print("\n" + "="*70)
        print("PHASE ANALYSIS REPORT — Finalisierung")
        print("="*70)

        analysis = briefing.get("analysis", "")
        validator_critique = briefing.get("validation", "")
        task = briefing.get("task", "")
        code_overview = briefing.get("code_overview", "")
        focused_files = briefing.get("focused_files", "")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Erkenntnisse-Section aus Analyse extrahieren (PFLICHT-Section vom Briefing-Prompt)
        main_analysis, synthesis = self._split_analysis_synthesis(analysis)

        # Halluzinations-Check auf Analyse-Text
        hallucinated_files = self._detect_hallucinated_files(analysis)

        # Klassifikations-Block (wenn übergeben)
        classification_block = ""
        if classification:
            classification_block = f"""## Task-Klassifikation
- **Typ:** {classification.get('type', 'unbekannt')}
- **Confidence:** {classification.get('confidence', 0):.0%}
- **Begründung:** {classification.get('reasoning', '—')}

"""

        # Halluzinations-Block
        hallu_block = ""
        if hallucinated_files:
            hallu_block = f"""## ⚠️ Halluzinations-Hinweis

Folgende Dateinamen wurden in der Analyse erwähnt, existieren aber **nicht** im Projekt:

{chr(10).join(f'- `{f}`' for f in hallucinated_files)}

Diese Hinweise sollten kritisch überprüft werden.

"""
        else:
            hallu_block = "## ✅ Halluzinations-Check\n\nKeine erfundenen Dateinamen in der Analyse erkannt.\n\n"

        # Validator-Block (kann sehr kurz sein, das ist OK)
        validator_block = ""
        if validator_critique and validator_critique != "🟢":
            validator_block = f"""## Adversarialer Critic-Feedback

{validator_critique}

"""
        elif validator_critique == "🟢":
            validator_block = "## Adversarialer Critic-Feedback\n\n🟢 Kein Einspruch.\n\n"

        # Project-Metadata-Block
        project_files = sorted(p.name for p in self.root.glob("*.py"))
        meta_block = f"""## Projekt-Metadaten

- **Root:** `{self.root}`
- **Python-Dateien:** {len(project_files)}
- **Tests vorhanden:** {(self.root / "tests").exists()}
- **Git-Repo:** {(self.root / ".git").exists()}

"""

        # Synthesis-Block prominent oben (TL;DR + Erkenntnisse + Next Steps)
        if synthesis:
            synthesis_block = f"""## 🎯 Erkenntnisse & nächste Schritte

{synthesis}

---

"""
        else:
            synthesis_block = ("## ⚠️ Hinweis\n\n"
                                "Das Briefing-Modell hat keine **ERKENNTNISSE**-Sektion "
                                "produziert. Die Detailanalyse unten enthält die Befunde, "
                                "aber keine destillierte Synthese.\n\n---\n\n")

        # Detailanalyse-Block (skip wenn leer — z.B. wenn Modell NUR Synthese lieferte)
        if main_analysis.strip():
            detail_block = f"## Detailanalyse\n\n{main_analysis}\n\n"
        else:
            detail_block = ("## ⚠️ Detailanalyse fehlt\n\nDas Briefing-Modell hat "
                            "direkt mit der Synthese begonnen — keine strukturierte "
                            "Detailanalyse vorhanden.\n\n")

        report_md = f"""# Analyse-Report — {timestamp}

## Aufgabe
> {task}

{classification_block}{synthesis_block}{meta_block}{detail_block}{validator_block}{hallu_block}---

## Anhang A: Code-Übersicht (AST-extrahiert)

<details>
<summary>Strukturelle Übersicht aller .py-Dateien im Projekt (zum Aufklappen)</summary>

```
{code_overview}
```

</details>

## Anhang B: Voll geladene Dateien (für Briefing-Kontext)

<details>
<summary>Inhalte der task-relevanten Dateien (zum Aufklappen)</summary>

```
{focused_files[:8000]}
{('... [gekürzt — gesamt ' + str(len(focused_files)) + ' chars]') if len(focused_files) > 8000 else ''}
```

</details>

---
*Generiert: {datetime.now().isoformat()}*
*Workflow: vibelike Analyse-Template (Briefing → Report → END)*
"""

        # EXPLAIN: kein Datei-Artefakt — Antwort steht schon im Briefing-Stream
        if not write_file:
            print("\n✅ EXPLAIN beantwortet (kein Report-File — Antwort siehe oben).")
            if hallucinated_files:
                print(f"   ⚠️  Halluzinations-Hinweis: {len(hallucinated_files)} erfundene Dateien")
            print()
            return {
                "phase": "ANALYSIS_REPORT",
                "report_path": None,
                "completed": True,
                "timestamp": datetime.now().isoformat(),
                "hallucinated_files": hallucinated_files,
            }

        report_path = self.root / "logs" / f"analysis-{timestamp}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_md)

        # Console-Summary statt nur Filename
        print(f"\n✅ Analyse-Report gespeichert: {report_path.relative_to(self.root)}")
        print(f"   Größe: {report_path.stat().st_size:,} bytes")
        print(f"\n   Inhalt:")
        print(f"   • Aufgabe + Klassifikation")
        print(f"   • Projekt-Metadaten ({len(project_files)} Dateien)")
        print(f"   • Analyse-Text ({len(analysis):,} chars)")
        if hallucinated_files:
            print(f"   • ⚠️  Halluzinations-Warnung: {len(hallucinated_files)} erfundene Dateien")
        else:
            print(f"   • ✅ Halluzinations-Check: clean")
        print(f"   • Validator-Critique")
        print(f"   • Anhang A: AST-Übersicht ({code_overview.count(chr(10).join(['📄']))} Dateien)")
        print(f"   • Anhang B: Voll-Geladene Files ({focused_files.count('═══')//2} Dateien)\n")

        return {
            "phase": "ANALYSIS_REPORT",
            "report_path": str(report_path),
            "completed": True,  # für Workflow-Summary
            "timestamp": datetime.now().isoformat(),
            "hallucinated_files": hallucinated_files,
        }

    def run_workflow(self, task: str, iteration: int = 0, max_iterations: int = 3,
                     parent_id: str = None) -> dict:
        """Entry-Point: klassifiziert Task, routet zum passenden Template.

        Templates (jeder Typ hat eigenes Briefing-Framing + Workflow-Form):
          - ANALYSIS:       Briefing → Report-Datei → END (kein Code)
          - EXPLAIN:        Briefing → Konsolen-Antwort → END (kein Report-File)
          - IMPLEMENTATION: Voller 6-Phasen-Workflow (Brief→Strat→Plan→Exec→Verify→Commit)
          - BUG_FIX:        wie IMPLEMENTATION, aber OHNE Strategie-Gate (direkt Fix-Plan)
          - REFACTOR:       wie IMPLEMENTATION, Verify prüft Verhaltens-Invarianz
        """
        # PHASE 0: Task-Klassifikation
        classification = None
        if iteration == 0:  # nur beim ersten Lauf klassifizieren, nicht bei Retries
            print("\n" + "="*70)
            print("PHASE 0: TASK-KLASSIFIKATION")
            print("="*70)

            try:
                project_files = [p.name for p in sorted(self.root.glob("*.py"))[:15]]
                classification = self.classifier.classify(task, project_files)
                from task_classifier import confirm_classification
                task_type = confirm_classification(classification)
            except Exception as e:
                print(f"[WARN] Klassifikation fehlgeschlagen: {e} → fallback IMPLEMENTATION")
                task_type = "IMPLEMENTATION"
        else:
            # Bei Retry: nutze gespeicherten task_type oder default
            task_type = self.current_workflow.get("task_type", "IMPLEMENTATION") if self.current_workflow else "IMPLEMENTATION"

        # ROUTE: Template-Auswahl
        if task_type == "ANALYSIS":
            return self._run_analysis_template(task, iteration, parent_id, classification)
        elif task_type == "EXPLAIN":
            return self._run_analysis_template(task, iteration, parent_id, classification)
        else:
            # IMPLEMENTATION, BUG_FIX, REFACTOR → Vollworkflow
            return self._run_implementation_template(task, task_type, iteration, max_iterations, parent_id)

    def _run_analysis_template(self, task: str, iteration: int, parent_id: str | None,
                                 classification: dict | None = None) -> dict:
        """ANALYSIS-Template: Briefing → Report → END.

        EXPLAIN teilt sich diesen Pfad, schreibt aber keine Report-Datei —
        die Antwort steht bereits im Briefing-Stream.
        """
        task_type = (classification or {}).get("type", "ANALYSIS")
        is_explain = task_type == "EXPLAIN"
        wf_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.current_workflow = {
            "id": wf_id,
            "task": task,
            "task_type": task_type,
            "iteration": iteration,
            "parent_id": parent_id,
            "phases": {},
        }

        briefing = self.phase_briefing(task, task_type=task_type)
        # Briefing als "completed" markieren (kein User-Gate noetig)
        briefing["completed"] = True
        self.current_workflow["phases"]["briefing"] = briefing

        report = self.phase_analysis_report(briefing, classification=classification,
                                             write_file=not is_explain)
        self.current_workflow["phases"]["report"] = report

        # Log workflow
        with open(self.workflow_log, "a") as f:
            f.write(json.dumps(self.current_workflow, default=str) + "\n")

        verdict = self._compute_workflow_verdict()
        self.current_workflow["verdict"] = verdict
        label = "ERKLÄRUNG" if is_explain else "ANALYSE"
        v = verdict.get("verdict", "🟢")
        reason = verdict.get("reason", "")
        print("\n" + "=" * 70)
        if v == "🟢":
            print(f"✅ {label}-WORKFLOW ABGESCHLOSSEN — 🟢 {reason}")
        elif v == "🟡":
            print(f"⚠️  {label}-WORKFLOW ABGESCHLOSSEN — 🟡 {reason}")
        else:
            print(f"❌ {label}-WORKFLOW DURCHGELAUFEN, ZIEL NICHT ERREICHT — 🔴 {reason}")
        print("=" * 70)
        if report.get("report_path"):
            print(f"   Report: {report['report_path']}")
        print()
        return self.current_workflow

    def _check_healthpoint(self, phase_name: str, output: str) -> None:
        """Warn-only Drift-Check eines Phasen-Outputs gegen den versiegelten Ziel-Anker.

        Unterbricht den Workflow NICHT — meldet Drift sichtbar und loggt das Verdict.
        Judge ist das Reasoning-Modell (analyzer_qwen).
        """
        if not self.healthpoint_enabled or self.healthpoint is None:
            return
        try:
            from healthpoint import check_drift
            verdict = check_drift(self.healthpoint, phase_name, output or "", self.analyzer_qwen)
        except Exception as e:
            print(f"   [Healthpoint-Check übersprungen: {e}]")
            return

        if self.current_workflow is not None:
            self.current_workflow.setdefault("healthpoint_checks", []).append(
                {"phase": phase_name, "aligned": verdict.aligned, "drift": verdict.drift}
            )

        if verdict.aligned:
            print(f"\n   🎯 Healthpoint [{phase_name}]: 🟢 am Ziel")
        else:
            print("\n" + "🟠" * 35)
            print(f"🟠 HEALTHPOINT-DRIFT [{phase_name}]: {verdict.drift}")
            print("🟠 (nur Warnung — Workflow läuft weiter)")
            print("🟠" * 35)

    def _compute_workflow_verdict(self) -> dict:
        """Aggregiert Healthpoint-Drifts, Datei-Schreibvorgänge und Tests zu einem
        ehrlichen Workflow-Verdict. Fängt die Lücke, dass die bisherigen Layer-
        Validierungen (Static/Critic/Verification) bei 0 Änderungen alle 🟢 melden
        — der Lauf aber das versiegelte Ziel nicht erreicht hat.
        """
        wf = self.current_workflow or {}
        phases = wf.get("phases", {})
        task_type = wf.get("task_type", "IMPLEMENTATION")
        hp_checks = wf.get("healthpoint_checks", []) or []
        drift_phases = [c.get("phase", "?") for c in hp_checks if not c.get("aligned")]
        drift_count = len(drift_phases)

        execution = phases.get("execution", {})
        files_written = execution.get("files_written", []) or []
        files_written_count = len(files_written)
        tests_passed = phases.get("verification", {}).get("tests_passed")
        produces_code = task_type in ("IMPLEMENTATION", "BUG_FIX", "REFACTOR")

        # Deterministische Signale (kein LLM): Static-Validator + Regression-Guard.
        exec_static = (execution.get("static_validation") or {}).get("verdict")
        exec_regression = (execution.get("regression_check") or {}).get("verdict")
        # "Deterministischer Layer grün" = nirgends ein deterministisches 🔴 +
        # Tests bestanden + Dateien geschrieben. Überstimmt ein halluziniertes
        # LLM-Judge-🔴 (Healthpoint kann bei komplexem Output falsch urteilen).
        deterministic_green = (
            produces_code and files_written_count > 0 and tests_passed is True
            and exec_static != "🔴" and exec_regression != "🔴"
        )

        metrics = {
            "task_type": task_type,
            "healthpoint_drifts": drift_count,
            "drift_phases": drift_phases,
            "files_written": files_written_count,
            "tests_passed": tests_passed,
            "static": exec_static,
            "regression": exec_regression,
            "commit_done": bool(phases.get("commit")),
        }

        # Drift im PLANNING (Prosa) ≠ Drift im OUTPUT (Execution). Planning-Drift,
        # der im finalen, getesteten Code nicht ankommt, soll kein 🔴 erzwingen.
        execution_drift = "EXECUTION" in drift_phases
        code_landed = produces_code and files_written_count > 0 and tests_passed is True

        # 1. Code-Task ohne Datei-Änderungen → Ziel klar verfehlt
        if produces_code and files_written_count == 0:
            drift_note = (f"Healthpoint-Drifts: {drift_count}× ({', '.join(drift_phases)})"
                          if drift_count else "ohne Drift-Signal")
            return {"verdict": "🔴",
                    "reason": (f"{task_type}-Lauf ohne Datei-Änderungen — "
                               f"Ziel nicht erreicht ({drift_note})"),
                    "metrics": metrics}
        # 2. Drift IM Output (Execution) → ernst. ABER: wenn der deterministische
        #    Layer grün ist (Tests + Static + Regression), ist das EXECUTION-Drift-
        #    Signal vermutlich eine LLM-Judge-Halluzination → 🟡 statt 🔴.
        #    Determinismus überstimmt LLM-Meinung.
        if execution_drift:
            if deterministic_green:
                return {"verdict": "🟡",
                        "reason": (f"EXECUTION-Drift gemeldet ({', '.join(drift_phases)}), "
                                   f"aber deterministischer Layer grün (Tests + Static + "
                                   f"Regression) — Judge-Signal überstimmt, Sichtung empfohlen"),
                        "metrics": metrics}
            return {"verdict": "🔴",
                    "reason": (f"Output-Drift an EXECUTION ({drift_count}× an "
                               f"{', '.join(drift_phases)}) — Code verfehlt das "
                               f"versiegelte Ziel"),
                    "metrics": metrics}
        # 3. Code gelandet + Tests grün, Drift nur im Planning → 🟡 (Sichtung, kein 🔴):
        #    die Planungs-Prosa wanderte, aber der finale Output ist da und grün.
        if code_landed and drift_count > 0:
            return {"verdict": "🟡",
                    "reason": (f"Code geschrieben + Tests grün, aber Planning-Drift "
                               f"({drift_count}× an {', '.join(drift_phases)}) — "
                               f"Sichtung empfohlen"),
                    "metrics": metrics}
        # 4. Mehrfach-Drift OHNE gelandeten/getesteten Code → verfehlt
        if drift_count >= 2:
            return {"verdict": "🔴",
                    "reason": (f"Mehrfach-Drift ({drift_count}× an "
                               f"{', '.join(drift_phases)}) — Output verfehlt das "
                               f"versiegelte Ziel"),
                    "metrics": metrics}
        # 5. Einzel-Drift
        if drift_count == 1:
            return {"verdict": "🟡",
                    "reason": (f"Abschluss mit Drift-Warnung an {drift_phases[0]} — "
                               f"manuelle Sichtung empfohlen"),
                    "metrics": metrics}
        body = (f"{files_written_count} Datei(en) geschrieben"
                if produces_code else "Report erstellt")
        return {"verdict": "🟢",
                "reason": f"Sauberer Lauf — keine Drift-Warnungen, {body}",
                "metrics": metrics}

    def _print_workflow_verdict(self, verdict: dict) -> None:
        """Schreibt das Verdict an den Schluss-Block — typabhängige Klartext-Ausgabe."""
        v = verdict.get("verdict", "🟢")
        reason = verdict.get("reason", "")
        print("\n" + "=" * 70)
        if v == "🟢":
            print(f"✅ WORKFLOW ABGESCHLOSSEN — 🟢 {reason}")
        elif v == "🟡":
            print(f"⚠️  WORKFLOW ABGESCHLOSSEN — 🟡 {reason}")
        else:
            print(f"❌ WORKFLOW DURCHGELAUFEN, ZIEL NICHT ERREICHT — 🔴 {reason}")
        m = verdict.get("metrics", {})
        print(f"   Metriken: drifts={m.get('healthpoint_drifts')}, "
              f"files_written={m.get('files_written')}, "
              f"tests_passed={m.get('tests_passed')}, "
              f"task_type={m.get('task_type')}")
        print("=" * 70 + "\n")

    def _run_implementation_template(self, task: str, task_type: str,
                                       iteration: int, max_iterations: int,
                                       parent_id: str | None) -> dict:
        """IMPLEMENTATION-Template: Full 6-phase workflow (bisheriges Verhalten)."""
        wf_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        if iteration > 0:
            print("\n" + "█"*70)
            print(f"🔁 ITERATION {iteration}/{max_iterations} — neue Aufgabe aus Failure-Analyse")
            print("█"*70)

        self.current_workflow = {
            "id": wf_id,
            "task": task,
            "task_type": task_type,
            "iteration": iteration,
            "parent_id": parent_id,
            "phases": {}
        }

        # Healthpoint VOR dem Briefing versiegeln. Das versiegelte Ziel ist die
        # User-Aufgabe selbst — nicht die spaetere Briefing-Reformulierung. Sonst
        # kann das Briefing bereits driften, ohne dass wir es bemerken.
        if self.healthpoint_enabled and iteration == 0:
            from healthpoint import Healthpoint
            self.healthpoint = Healthpoint(goal=task)
            print(f"\n   🎯 Healthpoint versiegelt: {task[:80]}")

        # Phase 1: BRIEFING (typ-spezifisches Framing: IMPLEMENTATION/BUG_FIX/REFACTOR)
        briefing = self.phase_briefing(task, task_type=task_type)
        self.current_workflow["phases"]["briefing"] = briefing
        self._check_healthpoint("BRIEFING", briefing.get("analysis", ""))

        # Phase 2A: PLANNING - STRATEGIE
        # BUG_FIX überspringt das Strategie-Gate — ein lokaler Fix braucht kein
        # separates "allgemeines Vorgehen". Der FIX-ANSATZ aus dem Briefing dient
        # direkt als Strategie-Seed für den Detail-Plan.
        if task_type == "BUG_FIX":
            print("\n[⏭️  BUG_FIX: Strategie-Gate übersprungen — direkt zum Fix-Plan]")
            strategy = {
                "phase": "PLANNING_STRATEGY",
                "strategy": briefing.get("analysis", "") or "Direkter Fix laut Briefing.",
                "approved": True,
                "skipped": True,
            }
        else:
            strategy = self.phase_planning_strategy(briefing)
            if not strategy or not strategy.get("approved"):
                print("\n❌ Workflow abgebrochen (Strategie nicht genehmigt).\n")
                return self.current_workflow
        self.current_workflow["phases"]["planning_strategy"] = strategy
        if not strategy.get("skipped"):
            self._check_healthpoint("STRATEGIE", strategy.get("strategy", ""))

        # Phase 2B: PLANNING - DETAILPLAN
        planning = self.phase_planning_detailed(briefing, strategy)
        if not planning or not planning.get("approved"):
            print("\n❌ Workflow abgebrochen (Detail-Plan nicht genehmigt).\n")
            return self.current_workflow
        self.current_workflow["phases"]["planning_detailed"] = planning
        self._check_healthpoint("DETAILPLAN", planning.get("plan", ""))

        # Hard-Stop bei zwei unabhaengigen Signalen: Static-Plan-Check 🔴 UND
        # Healthpoint-Drift am Detail-Plan. Bei Konkurrenz beider Signale ist
        # das User-Gate eine zu weiche Schwelle (besonders bei langen Plaenen
        # leicht zu uebersehen). Drift+Halluzination im Plan = Execution faengt
        # schlechten Code an, also lieber jetzt abbrechen.
        plan_static_red = planning.get("static_validation", {}).get("verdict") == "🔴"
        last_hp = (self.current_workflow.get("healthpoint_checks") or [{}])[-1]
        hp_drift = last_hp.get("phase") == "DETAILPLAN" and not last_hp.get("aligned", True)
        hallucinated = planning.get("hallucinated_files") or []
        # Hard-Stop bei (a) Dual-Signal Static-Red + HP-Drift, ODER
        # (b) Halluzinations-Treffer im Plan. Erfundene Dateinamen heissen, der
        # Plan baut auf Phantomen — Execution wuerde garantiert ins Leere greifen.
        if (plan_static_red and hp_drift) or hallucinated:
            print("\n" + "🛑" * 35)
            if hallucinated:
                print("🛑 HARD-STOP: Halluzinierte Dateinamen im DETAILPLAN")
                for fname in hallucinated[:5]:
                    print(f"🛑   - {fname}")
                self.current_workflow["aborted_at"] = "DETAILPLAN_HALLUCINATION"
            else:
                print("🛑 HARD-STOP: Static-Plan-Check 🔴 + Healthpoint-Drift am DETAILPLAN")
                print(f"🛑   Drift-Grund: {last_hp.get('drift', '?')[:120]}")
                self.current_workflow["aborted_at"] = "DETAILPLAN_HARDSTOP"
            print("🛑 Execution wird NICHT gestartet — Plan ist ungeeignet.")
            print("🛑" * 35)
            verdict = self._compute_workflow_verdict()
            self.current_workflow["verdict"] = verdict
            self._print_workflow_verdict(verdict)
            self._executor.shutdown(wait=False)
            return self.current_workflow

        # Phase 3: EXECUTION (Dry-Run + Code-Review + User-Gate)
        execution = self.phase_execution(briefing, planning)
        self.current_workflow["phases"]["execution"] = execution
        if not execution.get("approved"):
            print("\n❌ Workflow abgebrochen (Code-Änderungen nicht genehmigt).\n")
            self._executor.shutdown(wait=False)
            return self.current_workflow

        # Final Master-Check: dient der erzeugte Code noch dem versiegelten Ziel?
        _exec_files = ", ".join(c.get("path", "?") for c in execution.get("planned_changes", []))
        self._check_healthpoint("EXECUTION", f"Geänderte Dateien: {_exec_files}\n\n"
                                + execution.get("code", "")[:1500])

        # Phase 4: VERIFICATION (REFACTOR: Fokus auf Verhaltens-Invarianz)
        verification = self.phase_verification(execution, task_type=task_type)
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

        verdict = self._compute_workflow_verdict()
        self.current_workflow["verdict"] = verdict
        self._print_workflow_verdict(verdict)

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
