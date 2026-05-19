# Vibelike — Meeting-Vorlage

**Erstellt:**  2026-05-19
**Empfänger:** Opus Web (Architektur-Diskussion)
**Status:**   ~10k Zeilen Python, post-Sprint nach Hardening-Phase
**Ziel:**     Architektur-Status + offene Entscheidungen + nächste Schritte

---

## 1. Executive Summary (1 min)

Vibelike ist ein **lokaler LLM-Workflow-Agent** der 6-Phasen-Development orchestriert
(Briefing → Strategy → Detail-Plan → Execution → Verification → Commit). Läuft auf
einem AMD RX 7600 / 8 GB VRAM mit Ollama + qwen3:8b/qwen2.5-coder-Modellen.

Eingebettet:
- **Quelibrium**: Code-Retrieval mit Chaos-Resonance-Field (882 Wikipedia/RFC-Docs)
- **Ossifikat**: Triple-Knowledge-Graph mit Widerspruchs-Audits

Aktueller Stand: **Workflow läuft, Halluzinationen sind weitgehend kontrolliert**,
aber die Architektur hat einen **fundamentalen Drift** — alle Tasks werden in
"Implementation-Workflow" gezwungen, auch reine Analyse-Aufgaben. Eben behoben mit
Phase-0-Task-Classifier + Template-Routing.

**Distinktiv:**
- 3-Layer-Validierung (Code + Plan + Knowledge-Graph) — Production-Ready
- Deterministischer Static-Validator parallel zum LLM-Critic
- Self-Healing-Loops bei Test-Failures + Halluzinationen
- Konzept "inkonsistence" für widerspruchs-getriebene Workflow-Orchestrierung
  (siehe inkonsistence.md — noch nicht implementiert)

---

## 2. Architektur-Überblick

```
                  ┌──────────────────────────────────┐
                  │   terminal.py — CLI Entry Point  │
                  │   (QwenCoder, CodeRetriever)     │
                  └────────────────┬─────────────────┘
                                   ↓
        ┌──────────────────────────────────────────────────┐
        │   workflow_agent.py — 6-Phase Orchestrator       │
        │   ├─ Phase 0: Task-Klassifikator (NEU)           │
        │   ├─ Templates: ANALYSIS | IMPLEMENTATION        │
        │   ├─ phase_briefing / planning / execution …    │
        │   └─ Self-Heal-Loops, änderungen-Regenerate     │
        └──┬───────────┬───────────┬───────────────────────┘
           │           │           │
       ┌───┴────┐  ┌───┴────┐  ┌───┴────┐
       │Quelibr.│  │Ossifik.│  │Validat.│
       │Retrev. │  │ Audit  │  │ V2+SV  │
       └────────┘  └────────┘  └────────┘
```

**LLM-Setup (3 Rollen, Ollama):**
- `qwen3:8b` (5.2 GB) — Reasoning (Briefing/Strategy/Plan/Failure-Analysis)
- `qwen2.5-coder:latest` (4.7 GB) — Code-Gen (Execution, Self-Heal)
- `qwen2.5-coder:1.5b` (1.0 GB) — Critic (parallel-Validator)

VRAM-Constraint: 8 GB → Ollama swappt Reasoning↔Coder zwischen Phasen (~5-10s Latenz).

---

## 3. Komponenten-Status

| Komponente | Größe | Status | Bemerkung |
|------------|-------|--------|-----------|
| `terminal.py` | 631 LOC | ✅ stabil | QwenCoder + CodeRetriever |
| `workflow_agent.py` | 1921 LOC | 🟡 funktioniert, groß | Refactor-Kandidat |
| `validator2.py` | 636 LOC | ✅ production-ready | 3-Layer, ~66k lines/sec |
| `static_validator_v2.py` | 1260 LOC | ⚠️ ungenutzt? | Konkurriert mit validator2.py |
| `static_validator.py` | 473 LOC | ⚠️ legacy | Vorgänger von validator2 |
| `task_classifier.py` | 196 LOC | ✅ neu | Phase 0 |
| `ossifikat_audit_bridge.py` | 161 LOC | ✅ stabil | Bridge zu ossifikat |
| `harvest*.py` | 1180 LOC | ❓ unklar | Wikipedia-Harvest für Quelibrium |
| Tests | 1494 LOC | ✅ alle grün | 4 Test-Suites, Integration covered |

**Code-Volumen total:** 10.080 LOC Python, davon ~1.5k Tests.

---

## 4. Was im letzten Sprint passiert ist (20 Commits)

Diese Liste ist chronologisch — älteste zuerst. Sie zeigt den Rhythmus von
**Problem entdecken → Fix → neues Problem** im Hardening-Prozess.

| # | Commit | Was |
|---|--------|-----|
| 1 | d4d5cbf | ChaosRetrieval-Unpacking-Bug fix |
| 2 | b365728 | PosixPath JSON-Serialization fix (Phase 1) |
| 3 | 3ed94dd | Streaming für Qwen-Output |
| 4 | 8ee061a | Default-Modell auf 1.5b (VRAM-fit für stable start) |
| 5 | 2048f26 | Validator-Prompts tighten — "checkbox-bullshit" raus |
| 6 | 1cff033 | StaticValidator deterministisch parallel zum LLM-Critic |
| 7 | a673845 | Retrieval nativ in Planning-Phasen integriert |
| 8 | beb62e4 | validator2.py: high-impact Improvements (Regex-Engine, AST-Visitor) |
| 9 | b1a5014 | validator2.py: comprehensive Test-Suite (35 Tests, alle grün) |
| 10 | 8b48e13 | Ossifikat-Audits integriert (3-Layer-Pipeline) |
| 11 | 6e6bc06 | 3-Layer-Pipeline: End-to-End + Interface + Performance Tests |
| 12 | 7871257 | Complete stack integration test (vibelike + quelibrium + ossifikat) |
| 13 | 2077d25 | 'änderungen'-Loop endlich functional (war No-Op) |
| 14 | dba5f2d | **Briefing liest jetzt echten Code** (vorher nur Filenames) |
| 15 | 7f8ed8e | Validator-Regurgitation-Filter + Plan-File-Existence-Check |
| 16 | 512c011 | Authoritative File List + Emoji-Normalisierung + Hallu-Detector |
| 17 | 03ecfa6 | **3 separate Modelle** (Reasoning/Code/Critic) statt 1 |
| 18 | ce1b7e8 | Hallu-Detector: NEUE-Dateien-Section korrekt ausschließen |
| 19 | 60ab346 | inkonsistence.md/.py — Konzept-Notiz Healthpoint-Architektur |
| 20 | e02b2b2 | **Phase 0 Klassifikator + Templates (ANALYSIS/IMPLEMENTATION)** |

**Theme des Sprints:** Halluzinationen + Task-Mismatch bekämpfen. Was begann als
"warum erfindet Qwen Dateinamen?" endete bei "Workflow zwingt Analyse-Tasks in
Implementation-Pipeline" — fundamentaler als ursprünglich gedacht.

---

## 5. Offene Probleme & Reibungspunkte

### 5.1 🔴 Critical

| ID | Problem | Status |
|----|---------|--------|
| P1 | **1.5b Critic ist zu schwach** — echoed Input, leakt Prompt-Templates | Hardening (Filter) statt Lösung |
| P2 | **Vault enthält 0 Projekt-Code** — 882 docs sind nur Wikipedia/RFC/PEP | Workaround durch direct file read; harvester für Projekt-Code fehlt |
| P3 | **2 konkurrierende Validatoren** — static_validator.py vs validator2.py vs static_validator_v2.py | Aufräumen: einen behalten, andere entfernen |

### 5.2 🟡 Architektur-Schulden

| ID | Problem | Bemerkung |
|----|---------|-----------|
| A1 | workflow_agent.py = 1921 LOC monolith | Phasen sollten in eigene Module |
| A2 | Templates noch primitiv (2 von 5 implementiert) | BUG_FIX, REFACTOR, EXPLAIN fehlen |
| A3 | Kein globaler "Healthpoint" — jede Phase prüft lokal | inkonsistence.md skizziert dies |
| A4 | änderungen-Loop pro Phase isoliert | Cross-Phase-Feedback fehlt |
| A5 | Ollama-Modell-Swap-Latenz (~5-10s) zwischen Phasen | Schnittstelle nicht swap-aware |

### 5.3 🟢 Tactical

| ID | Problem | Bemerkung |
|----|---------|-----------|
| T1 | UI ist plain stdin/stdout | User schlug Streamlit-Hybrid vor (separate Branch?) |
| T2 | Phase-Outputs ständig im Terminal sichtbar | "Collapsible dropdowns" gewünscht — nicht trivial in CLI |
| T3 | Logging fragmentiert (workflows.jsonl, execution.db, queue.db) | Konsolidierung sinnvoll? |
| T4 | Test-Coverage gut, aber keine CI | GitHub Actions / pre-commit Hook? |
| T5 | task_classifier.py JSON-Parse kann fehlschlagen | Fallback ist IMPLEMENTATION → suboptimal |

---

## 6. Performance-Daten

Gemessen am `test_complete_stack_integration.py` + `test_ossifikat_pipeline.py`:

| Metrik | Wert | Anmerkung |
|--------|------|-----------|
| Code-Vault-Search | 1.7-19.4 ms | Quelibrium ChaosRetrieval, 882 docs |
| validator2 single file | 2.96 ms | ~200 LOC Python |
| validator2 multi-file | 3.93k files/sec | 10 Dateien |
| Ossifikat-Audit-Bridge | 0.35 ms | run_all_audits |
| validate_full() Overhead | <1% | DB-Vorhandensein |
| Briefing-Phase (qwen3:8b) | ~30-90s | Stream-Dauer + Validator-Parallel |
| Strategy-Phase (qwen3:8b) | ~40-120s | + Vault-Retrieval (Wikipedia-Müll) |
| Detail-Plan (qwen3:8b) | ~60-180s | je nach Komplexität |
| Modell-Swap (Ollama) | 5-10s | qwen3:8b ↔ coder:latest |

**Bottleneck:** LLM-Inference + Modell-Swaps. Alles andere ist Mikrosekunden.

---

## 7. Architektur-Entscheidungen die anstehen

### Entscheidung 1: Welcher Static-Validator bleibt?
- `static_validator.py` (473 LOC, legacy)
- `static_validator_v2.py` (1260 LOC, ungenutzt?)
- `validator2.py` (636 LOC, in Verwendung)

**Frage:** Konsolidieren oder einer als Migrations-Brücke?

### Entscheidung 2: Vault-Strategie
- Aktuell: 882 Wikipedia/RFC/PEP-Docs für Code-Retrieval = mostly noise
- Option A: Lokaler Code-Harvester (Projekt-Files in Vault einbetten)
- Option B: Vault nur für CS-Konzepte, lokaler Code via direct read (aktuell)
- Option C: Vault loswerden für Workflow, beibehalten für Quelibrium-Standalone

**Frage:** Welcher Weg? Code-Harvester wäre ~200 LOC + Embedding-Run.

### Entscheidung 3: Critic-Strategie
- Aktuell: qwen2.5-coder:1.5b → zu schwach, echoed
- Option A: qwen3:1.7b (gerade gepullt, neuste Generation, vergleichbar groß)
- Option B: qwen2.5:3b (größer, fits gerade noch in VRAM)
- Option C: Kein LLM-Critic, nur deterministische Checks
- Option D: Cloud-API (OpenAI/Anthropic) als optionaler Critic

**Frage:** A oder B testen, oder gleich C/D? VRAM ist eng.

### Entscheidung 4: Workflow-Templates ausbauen
- Aktuell: ANALYSIS + IMPLEMENTATION
- Fehlend: BUG_FIX, REFACTOR, EXPLAIN
- Roadmap: jeweils ~80 LOC pro Template

**Frage:** Welche Templates haben höchste Priorität? Wahrscheinlich BUG_FIX.

### Entscheidung 5: inkonsistence-Konzept umsetzen?
- Skizziert in inkonsistence.md (~20 KB Konzept + ~8 KB Code-Stubs)
- Würde fundamentale Refactor sein (Healthpoint + Gates + Reintegration)
- Aktueller Workflow hat Bruchstücke davon, aber kein zentrales Modell

**Frage:** Ist das für Vibelike-Workflow überhaupt das richtige Modell, oder
gehört es in ein separates Projekt?

### Entscheidung 6: UI-Strategie
- CLI bleibt primary?
- Streamlit-Hybrid (siehe frühere Diskussion) für "Live Dashboard"?
- TUI-Library (rich/textual)?

**Frage:** Lohnt es sich UI zu investieren, oder bleibt das Tool CLI-only?

---

## 8. Roadmap-Vorschläge

### Kurzfristig (1-2 Tage)
1. **Critic-Modell wechseln** — qwen3:1.7b ist downloaded, einbauen + testen
2. **static_validator.py + static_validator_v2.py aufräumen** — entweder mergen oder löschen
3. **Vault aus Workflow-Pipeline entfernen** (oder ehrlich labeln) — bringt aktuell nur Confusion

### Mittelfristig (1-2 Wochen)
4. **BUG_FIX-Template** implementieren (Briefing → Root-Cause → Patch → Verify)
5. **Lokaler Code-Harvester** für Vault (sinnvoll machen statt deaktivieren)
6. **workflow_agent.py modularisieren** — Phasen in eigene Module

### Langfristig (offen)
7. **inkonsistence-Architektur** — separates Projekt oder Vibelike-Refactor?
8. **Streamlit-Dashboard** als Observer-Tool (Hybrid CLI+Web)
9. **CI Pipeline** mit pre-commit + GitHub Actions

---

## 9. Fragen für das Meeting

### Verständnis
- Was sind die wichtigsten **Use-Cases**, die Vibelike abdecken soll? (Solo-Dev?
  Team? Open Source?)
- Welche **Modell-Qualität** ist realistisch erwartbar mit dem Hardware-Budget?
- Ist Vibelike eher **Werkzeug** (User-driven) oder **Agent** (autonomous)?

### Architektur
- Lohnt sich das **inkonsistence-Konzept** als nächste Iteration, oder ist das
  zu früh / nicht passend für den Workflow?
- Single-Healthpoint vs. verteilte Goals — welcher Style passt zu LLM-Workflows?
- **Quelibrium**-Integration: nur als Retriever oder tiefer (Embeddings im Workflow)?

### Modell-Strategie
- Local-only oder hybrid local+cloud?
- Welche Modelle für welche Rollen? (Reasoning/Code/Critic)
- Wie umgehen mit der **VRAM-Limitation** auf 8 GB?

### Skalierung
- Wenn das Projekt wächst — wo sind die ersten Schmerzpunkte?
- Threading / Concurrency: ist das nötig oder Premature Optimization?
- Persistenz / State-Recovery: brauchen wir das (Workflow-Restart nach Crash)?

### Strategisch
- Vibelike als Open-Source-Tool? Privates?
- Ossifikat-Knowledge-Graph: wie wichtig für Workflow vs. Standalone?
- Welche **Erfolgs-Metrik** macht Sinn? (Zeit pro Task? Code-Quality? User-Tasks/Tag?)

---

## 10. Appendix

### A. Datei-Liste (alphabetisch)

```
config.py                          (Konfiguration)
harvest.py                         (Wikipedia/RFC/PEP-Harvester für Vault)
harvest_scheduler.py               (Scheduler für Harvest)
harvest_worker.py                  (Worker für Harvest)
inkonsistence.md / .py             (Konzept-Notiz Healthpoint-Architektur)
ossifikat_audit_bridge.py          (Bridge Ossifikat → validator2)
run_tests.py                       (Test-Runner)
static_validator.py                (Legacy, 473 LOC)
static_validator_v2.py             (Ungenutzt?, 1260 LOC)
task_classifier.py                 (Phase 0, neu)
terminal.py                        (CLI Entry, QwenCoder, Retriever)
test_*.py                          (4 Test-Suites)
tools_harvester.py                 (Tool-Doc-Harvester)
validator2.py                      (3-Layer-Validator, in Verwendung)
workflow_agent.py                  (6-Phase-Orchestrator, 1921 LOC)
MEETING_VIBELIKE_ANALYSIS.md       (dieses Dokument)
```

### B. Key-Patterns aus dem Code

```python
# 1. 3-Layer-Validation
validator.validate_full(changes, plan, ossifikat_db=db)
# → ExtendedReport mit Code+Plan+Knowledge-Graph findings

# 2. Self-Healing-Loop
if static_report.verdict == "🔴":
    planned_changes = self._self_heal_execution(...)

# 3. änderungen-Regenerate
for iteration in range(max_iterations):
    output = generate_with_feedback(...)
    decision = self._ask_approval("Strategie")
    if decision["action"] == "change":
        feedback_history.append(decision["changes"])

# 4. Authoritative File List (Anti-Halluzination)
auth = self._authoritative_file_list()
prompt = f"VERBINDLICH: {auth}\n... Aufgabe: {task}\nERINNERUNG: {auth}"

# 5. Task-Klassifikator (Phase 0)
classification = self.classifier.classify(task, project_files)
template = "ANALYSIS" if classification["type"] == "ANALYSIS" else "IMPLEMENTATION"
```

### C. Distinkte Konzepte für Diskussion

1. **3-Layer-Validation** (Code + Plan + Knowledge-Graph) — funktioniert, produziert echte Findings
2. **Deterministic + LLM Critic parallel** — robuste Fail-Detection
3. **Self-Healing-Phases** — Workflow korrigiert sich selbst bei Static-Validator-Fehlern
4. **Task-Klassifikator als Phase 0** — verhindert Task-Mismatch
5. **inkonsistence-Modell** (Konzept, nicht implementiert) — Healthpoint + Silent-Point-Gates

### D. Nicht-Code-Artefakte

- `data/code_archive.monolith` — Vault-Storage (882 docs)
- `data/code_embedding_cache.pkl` — Embedding-Cache
- `logs/workflows.jsonl` — Workflow-History
- `logs/execution.db` — Execution-State
- `logs/queue.db` — Request-Queue
- `logs/analysis-*.md` — Generierte Analyse-Reports (neu, durch ANALYSIS-Template)
- `ossifikat/data/ossifikat.db` — Knowledge-Graph

---

## Schlussbemerkung

**Wo wir gerade stehen:** Vibelike funktioniert, hat sich im letzten Sprint
deutlich stabilisiert (Halluzinationen kontrolliert, Templates landen Tasks
in der richtigen Pipeline). Aber das Tool ist an einem Punkt wo **architektonische
Entscheidungen** wichtiger werden als weitere Bug-Fixes:

- Wollen wir hin zum **autonomen Coding-Agent** oder zum **strukturierten
  Dev-Assistenten**?
- Wie umgehen mit der **Modell-Realität** (lokal limitiert vs. Cloud teuer)?
- Ist das **inkonsistence-Konzept** ein Nordstern oder ein Ablenkmanöver?

Das sind die Fragen die wir im Meeting klären sollten.
