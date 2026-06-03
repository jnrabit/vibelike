# vibelike + ossifikat als Entwicklungs-Unterbau für chaos_engine

*Fähigkeits-Analyse · Stand 2026-06-03*
*Ausrichtung: vibelike + ossifikat als Substrat für das Projekt chaos_engine (Substrat-/Physik-Research) — (A) Ossifikation der Entwicklungsgeschichte jetzt, (B) Agenten-Tasks viel später.*

---

## 0. TL;DR

| Baustein | Stand | Aufwand bis nutzbar (für dieses Ziel) |
|---|---|---|
| **Ossifikat als Geschichts-/Fakten-Store** | ✅ Kern fertig | klein (Ingest-Pfad + Prädikat-Schema) |
| **Auto-Extraktion aus Doku/Commits** (`QwenExtractor`) | ✅ gebaut, ⚠️ nicht verdrahtet | klein |
| **Temporale Abfrage (`query_at`) + Audit** | ✅ fertig | — |
| **vibelike-Workflow als Task-Runner** | ✅ stark (2 reale Features, 42 Tests grün) | mittel — aber „später" |
| **vibelike-Workflow auf FREMDES Repo (chaos_engine)** | ⚠️ self-repo-verdrahtet | mittel (`project_root`-Parametrisierung) |

**Für (A) ist fast alles da** — ossifikat ist exakt das richtige Werkzeug; es fehlt nur die Ingest-Brücke chaos_engine→ossifikat. **Für (B)** ist der Workflow stark, muss aber erst auf fremde Repos zeigbar werden.

---

## 1. ossifikat — der Geschichts-Unterbau (für A)

**Was es ist:** Ein **temporaler, append-only, menschlich-ratifizierter Triple-Store** (`ossifikat/ossifikat/`). Fakten als `(subject, predicate, object)` + Confidence/Source/Hash. Staging → Bestätigung → Ossifikation.

### Fähigkeiten (verifiziert im Code)

| Fähigkeit | Modul / API | Relevanz für chaos_engine-Historie |
|---|---|---|
| **Staging → Ossifikation** | `store.add_staging()` → `store.confirm()` | Jeder Fakt startet weich (Staging), härtet erst nach Bestätigung — „Ossifikation" wörtlich |
| **Auto-Extraktion aus Text** | `extractor.QwenExtractor` (Ollama/qwen) | Commits / Design-Docs / Run-Befunde rein → S-P-O-Tripel, ohne Handarbeit |
| **Temporale Abfrage** | `store.query_at(timestamp)` | „Was wussten/entschieden wir zum Zeitpunkt T" — rekonstruiert den Wissensstand pro Punkt |
| **Retraktion statt Löschung** | `store.retract()` / `is_retracted()` | Befunde werden zurückgezogen, nie gelöscht — Geschichte bleibt. (Muster: „S3b korrigierte zwei frühere Schlüsse") |
| **Audit auf Widersprüche** | `audit/checks/` | `functional_conflicts`, `orphan_retracts`, `unclassified_predicates` — fängt Inkonsistenzen in der wachsenden Wissensbasis |
| **Tamper-evidence** | `content_hash` + `confirmation_hash` (SHA256) | Append-only, git-auditierbar; jede Behauptung + Ratifizierung nachweisbar |
| **CLI + programmatische API** | `cli.py` (`ossifikat review`), `OssifikatStore` | Interaktive Bestätigung + voll skriptbar |

**Triple-Schema** (`schema.py`): `id, subject, predicate, object, confidence, source, staging, created_at, updated_at, content_hash`.
**Confirmation-Schema**: `triple_hash, confirmed_by, confirmed_at, confirmation_type, confirmation_hash, note`.

**Befund:** Für (A) ist der Kern **fertig und passgenau** — ein temporaler, retraktions-fähiger, audit-geprüfter Fakten-Store ist genau das Werkzeug für eine Forschungs-Historie, die sich laufend selbst korrigiert.

---

## 2. vibelike-Workflow — der Task-Runner (für B, später)

**Was es schon kann** (`workflow_agent.py`, ~3200 Z.): 6-Phasen-Workflow Briefing → Strategie → Detail-Plan → Execution → Verify → Commit. Task-Typen: ANALYSIS, EXPLAIN, IMPLEMENTATION, BUG_FIX, REFACTOR. Per-Step-Git-Commits, Failure-Loop. In dieser Session zwei reale Features gebaut (`chaosgarten/handshake.py`, `chaosgarten/reactions.py`, 42 Tests grün).

**Modell-Setup:** `qwen3:8b` (Reasoning), `claude-sonnet-4-6` (Code-Gen, API), `qwen2.5-coder:1.5b` (Critic).

**Härtungs-Schichten** (das Differenzierende):
- **Healthpoint** — versiegelter Ziel-Anker, Anti-Drift pro Phase
- **Regression-Guard** — AST-Symbol-Verlust + Größen-Kollaps, deterministisch
- **Static-Validator** (`validator2.py`) — Security/Quality/Plan-Drift-Patterns; erkennt jetzt auch deklarierte NEUE DATEIEN
- **Grammar-Decoding** — Ollama Structured Outputs (Schema→GBNF) zwingt Klassifikator + Critic in valides JSON
- **Verdict-Aggregation** — Determinismus (Tests + Static + Regression) überstimmt halluzinierende LLM-Judges
- **MONOLITH** — immer-geladener autoritativer Projekt-Anker + auto-generiertes Engine-Skelett

**Ehrliche Lücke für dein Ziel:** vibelike ist **auf sein eigenes Repo verdrahtet** (`self.root = Path(__file__).parent`, MONOLITH vibelike-spezifisch, Selfcode-Harvest + Datei-Listen zeigen auf vibelike). Um Tasks **auf chaos_engine** zu fahren, braucht es:
- parametrisierbaren `project_root` (statt hardcoded)
- ein chaos_engine-eigenes `MONOLITH.md` (Invarianten der Substrat-Engine)
- Selfcode-Harvest gegen chaos_engines Quellen

Machbar (saubere eine-Naht-Änderung), heute nicht vorhanden — passt zu „Agenten erst viel später".

---

## 3. Wie vibelike + ossifikat heute verbunden sind

vibelike speist ossifikat schon — aber **flach**, via `adapters/terminal_adapter.py`:
- `store_query_response()` — Retrieval-Q&A als auto-bestätigte Tripel (`predicate="retrieved_answer"`)
- `store_hardware_state()` — Hardware-State als Tripel
- `get_query_history()` — liest die Q&A-Historie

Das ist **Telemetrie, nicht Entwicklungsgeschichte.** Der `QwenExtractor` (Auto-Extraktion aus Doku/Commits) ist gebaut, aber **im Workflow nirgends verdrahtet**.

---

## 4. Was für dein Ziel fehlt (konkret)

### (A) Ossifikation der chaos_engine-Geschichte — der nächste Schritt
Ein **Ingest-Pfad** chaos_engine-Artefakte → ossifikat:
1. **Quellen:** git-Commits, `ENGINE_FUSION_DESIGN.md`, `SUBSTRAT_TEMPLATES (*).md`, `netz_modell_wachpunkt.md`, Run-Befunde (S3b/S4…)
2. → `QwenExtractor` extrahiert S-P-O → `add_staging`
3. → `ossifikat review` (bestätigen/verwerfen) → ossifiziert
4. → `query_at` (Zeitreisen), `audit` (Widerspruchs-Checks)

Kleines, klar abgegrenztes Stück: Store + Extractor existieren — es fehlt nur **das Ingest-Skript + ein Prädikat-Schema für Entwicklungs-Fakten** (z.B. `entschied`, `befund`, `komponente_hat`, `revidiert`, `ersetzt`).

### (B) Agenten — später
`project_root`-Parametrisierung + per-Projekt-MONOLITH + Selfcode-Harvest gegen chaos_engine.

---

## 5. Verweise (Code-Anker)

- **Ossifikat-Store:** `ossifikat/ossifikat/store.py` (`add_staging`, `confirm`, `retract`, `query`, `query_at`)
- **Extractor:** `ossifikat/ossifikat/extractor.py` (`QwenExtractor`)
- **Audit:** `ossifikat/ossifikat/audit/checks/` (orphan_retracts, functional_conflicts, unclassified_predicates)
- **Schema:** `ossifikat/ossifikat/schema.py` (`Triple`, `Confirmation`)
- **CLI:** `ossifikat/ossifikat/cli.py` (`ossifikat review`)
- **vibelike↔ossifikat heute:** `adapters/terminal_adapter.py`
- **Workflow:** `workflow_agent.py` (`WorkflowAgent.run_workflow`)
- **chaos_engine:** `/home/jnrabit/chaos_engine/` (Research-Projekt; `ENGINE_FUSION_DESIGN.md`, `SUBSTRAT_TEMPLATES (*).md`)
