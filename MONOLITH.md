# MONOLITH.md — Projekt-Fundament von vibelike
*Unveränderlicher, autoritativer Anker. Wird bei JEDEM Briefing in den Kontext geladen.*
*Regel: Was hier als „NICHT ÄNDERN" / Invariante steht, ist gesetzt — nicht hinterfragen, nicht umbauen.*

---

## 1. 🚫 INVARIANTEN / VERBOTE

- **`framework/` = vendored Quelibrium-Engine.** NIE ändern. Mathematisch fundiert (8D-Lorenz-Chaos, RK4, Lyapunov, Shannon-Entropie), C++/`.so`-gebunden, ABI-stabil. Wird nur *benutzt*, nie modifiziert.
- **`choose/` = Vendor-Dependency** (atom.py, bundle.py, choice.py). Nicht modifizieren — Integration erfolgt über die bestehende API, nicht durch Eingriff.
- **Modell-Setup ist fix:**
  - `qwen3:8b` — Reasoning (Briefing, Strategie, Plan, Klassifikation)
  - `claude-sonnet-4-6` — Code-Generierung (Frontier-API, semantische Instruktionstreue)
  - `qwen2.5-coder:1.5b` — paralleler Critic
  - Tausch nur über Env-Vars (`VIBELIKE_*`), nicht im Code hartkodieren.
- **Hardware:** AMD RX 7600 / 8 GB VRAM, KEIN CUDA. Embedding/Harvest immer `--device cpu`. Lokale Inferenz ist auf ~7b-Klasse gedeckelt.
- **Grundgesetz:** *Guards fangen Zerstörung, nicht „plausibel-falsch".* Determinismus verifiziert Größe/Syntax/Symbole/Security — NICHT ob der Code semantisch das Richtige tut. Korrektheit braucht das Frontier-Modell, nicht mehr Guards.

---

## 2. 🏗️ VENDORED ENGINE (`framework/quelibrium/`) — Black-Box-Kontrakte

Nur die öffentliche Nutzung zählt. Interna sind tabu (siehe Invarianten).

- **`core/protocol.py :: Protocol`** — Brücke zur C++-Engine (`libquelibrium.so`).
  - `get_hardware_state()` → dict (Lorenz-Koordinaten, Entropie, Temperatur)
  - `get_lorenz_params()` → dict (rho, sigma, beta, …)
  - `raw_search(query_vec, density)` → **KAPUTT**: liefert query-unabhängig dieselben Docs mit dist=0 (C++-Bug). NICHT nutzen — stattdessen ChaosRetrieval bzw. numpy-cosine.
  - `archive` (Liste der Docs), `_matrix` / `_id_map` (Vektor-Matrix für numpy-cosine).
- **`intelligence/retrieval.py :: ChaosRetrieval`** — `search(query_vec, top_k)` → `[(doc_id, distance), …]`. **Primärer und einziger semantisch korrekter Retrieval-Pfad.**
  - `RiemannianWarp`, `ThompsonSampler` — Retrieval-Mathematik (Warp via Lorenz-State, Explorations-Sampling).
- **`intelligence/resonance.py :: ResonanceField`** — Resonanz-Kopplung (Hypercube-Topologie) für ChaosRetrieval.
- **`core/vault.py :: Vault`** — verschlüsselter Store: LZMA + Chaos-XOR über JSON-Liste. Das ist das `.monolith`-Dateiformat (`data/code_archive.monolith`). `MonolithVault = Vault` (Alias).

**Live-Signaturen (auto aus `framework/` generiert — Drift-Check, bei jedem Briefing aktuell):**
<!-- ENGINE_SKELETON_AUTO -->

---

## 3. ⚙️ 6-PHASEN-WORKFLOW (`workflow_agent.py :: WorkflowAgent`)

1. **Briefing** — Reasoning analysiert Aufgabe + ECHTEN Projektcode (parallel validiert)
2. **Planning-Strategie** — allgemeines Vorgehen (parallel validiert)
3. **Planning-Detail** — konkrete Durchführung (parallel validiert + Static-Validator)
4. **Execution** — Code-Gen + Dry-Run-Diff (Regression-Guard + Static-Validator vor dem Write)
5. **Verify** — Tests laufen automatisch; bei Fail → Failure-Analysis → Loop zurück zu Phase 1
6. **Commit** — pro Teilschritt aus dem Detail-Plan ein eigener Git-Commit

**Task-Routing (Phase 0 Klassifikation):**
- `ANALYSIS` → Briefing → Report-Datei → END (kein Code)
- `EXPLAIN` → Briefing → Konsolen-Antwort → END (kein Report-File)
- `BUG_FIX` → überspringt das Strategie-Gate (lokaler Fix braucht kein „allgemeines Vorgehen")
- `IMPLEMENTATION` / `REFACTOR` → voller 6-Phasen-Lauf

---

## 4. 🛡️ SAFETY-LAYER (was jede Schicht fängt)

- **Healthpoint** (`healthpoint.py`): versiegelter Ziel-Anker pro Workflow, an Phasengrenzen gegen-geprüft. Fängt **Phasen-Drift** (Output entfernt sich vom versiegelten Ziel). Warn-only.
- **Regression-Guard** (`_check_regression`, vor dem Write): fängt **destruktive Überschreibungen** — AST-Symbol-Verlust + Größen-Kollaps. Deterministisch; stoppt was alle LLM-Gates durchließen (z.B. 642-Zeilen-Selbstzerstörung).
- **Static-Validator** (`validator2.py :: StaticValidatorV2`): deterministische Patterns (Syntax, Imports, Security, Performance, Quality, Plan/Code-Drift). Keine LLM-Halluzination.
- **Paralleler Critic** (`qwen2.5-coder:1.5b`): adversarialer Reviewer, gibt NUR `🟢` / `🟡 <Satz>` / `🔴 <Satz>`. Bei Claude-Codegen ist der Code-Review-Critic deaktiviert (weak-reviewt-strong = Rauschen).

---

## 5. 🔎 RETRIEVAL / CODE-VAULT

- **Vault-Inhalt** (~1729 Docs): Wikipedia-CS (DE+EN), RFCs, PEPs, Tool-Docs, `PROJEKT_WISSEN_LEGACY` (alt) + **`PROJEKT_SELFCODE`** (671 AST-Chunks des eigenen Codes, via `harvest.py --phase selfcode`).
- **`terminal.py :: CodeRetriever.search(query, k, source_boost=None)`**: ChaosRetrieval primär; numpy-cosine als korrekter Fallback (NICHT der kaputte raw_search). `QueryTranslator` (gemma2:2b) übersetzt DE→EN vor dem Embedding.
- **`source_boost`**: opt-in Re-Ranking nach Doc-Quelle. `{"PROJEKT_SELFCODE": 0.6}` zieht eigenen Code vor generische Wiki-Artikel — automatisch aktiv bei ANALYSIS/EXPLAIN-Briefings.
- **Achtung:** `framework/` ist aus dem Selfcode-Harvest ausgeschlossen (vendored). Engine-Fragen → dieser MONOLITH ist die Quelle, nicht das Retrieval.

---

## 6. 🧠 HART ERKÄMPFTE ERKENNTNISSE (das „Warum")

- **Small-Model-Decke:** ~7b-Modelle scheitern nicht an Format/Refusal/Kontext, sondern an **semantischer Instruktionstreue** — sie liefern flüssigen, format-korrekten, plausiblen Code, der die Anforderung verfehlt. Darum läuft Code-Gen über Claude (Frontier), Reasoning/Critic bleiben lokal.
- **Containment ≠ Korrektheit:** Die Guards dämmen Schaden ein (Zerstörung, Security, Drift), erzeugen aber keine Korrektheit. „Ist das was der User wollte" ist nicht deterministisch verifizierbar.
- **Bekannte Anti-Patterns (aktiv abgewehrt):**
  - Selbstzerstörung: ganze Datei durch winzigen Stub ersetzen (Größen-Kollaps) → Regression-Guard.
  - Regurgitation: der Critic/Output schreibt den Input ab statt zu prüfen → gefiltert.
  - Halluzinierte Dateinamen: erfundene Module (`workflow_manager.py`, `vibelike.py`) → Authoritative-File-List-Sandwich + Halluzinations-Check.
- **Ehrlichkeit vor Politur:** Lieber „weiß ich nicht / Datei existiert nicht" als eine plausible Erfindung. Erfundene Fakten als Fundament sind teurer als eine offene Lücke.
