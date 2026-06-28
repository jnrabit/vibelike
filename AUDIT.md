# 🔍 Codebase-Audit — `vibelike` / hótr̥

> **Stand:** 2026-06-28 · **Scope:** gesamtes `~/vibelike` · **Methode:** statische Analyse
> (Struktur, LOC, Imports, AST-Funktionsgrößen, Tests, CI) + Laufzeit-Stichproben
> (Vault-Load, Config-Auflösung, Retrieval). Befunde aus vendored Code (`framework/`,
> `ossifikat/`) sind als solche markiert.

---

## 0. Executive Summary

Ambitioniertes **lokal-first agentisches Coding-/Wissens-System** mit echter Anti-Drift-
und Grounding-Architektur. Solide **deterministische Sicherheitsnetze** (CI, doctor,
Regression-Guard, Static-Validator). Online, testgrün (98 passed), beide Vaults laden.

**Zwei größte Hebel:** (1) drei **Monolithen** (`workflow_agent.py` 3.587, `terminal.py`
1.875, `harvest.py` 1.776 LOC) sind untestbar — der `workflow/`-Scaffold existiert zum
Splitten, ist aber unverdrahtet; (2) **Scaffold-Entscheidung** (`models/`, `workflow/`
mit 0 Live-Imports) — Schein-Fortschritt auflösen. Tote Zonen sind sauber abgetrennt
(gitignored), Security-Grundgerüst steht, Härtung offen.

---

## 1. Projekt-Überblick

| | |
|---|---|
| **Umfang (eigener Code)** | 139 Python-Module, **~27.572 LOC** |
| **Vendored** | `framework/quelibrium` 1.049 LOC + `libquelibrium.so` (C++) · `ossifikat/` 1.357 LOC (Submodule) |
| **Entry-Points** | `vibelike-terminal`, `-harvest`, `-tools`, `-harvest-worker`, `-harvest-scheduler` + Web (FastAPI :8800, Retrieval-Daemon :8810) |
| **Dependencies** | 15 (schwer: `sentence-transformers`/torch, `anthropic`, `fastapi`, `mistral-common`, `numba`, `cryptography`) |
| **Config** | 47 Pydantic-Settings-Felder, env-Prefix `VIBELIKE_` |
| **Repo** | `github.com/jnrabit/vibelike` (öffentlich), Branch `main`, CI grün, Submodule `ossifikat` |

---

## 2. Architektur & Datenfluss

```
Input
  │
  ▼ TaskClassifier  (claude-haiku via Anthropic-API)
  ├─ EXPLAIN/ANALYSIS ──► QUERY-MODE
  │     • Dual-Vault-Retrieval (Quelibrium-Engine / ChaosRetrieval)
  │         ├ Code-Vault     1.733 docs
  │         └ Wissens-Vault  258.873 docs   (per Cosine "fair gemerged")
  │     • QueryTranslator (DE→EN) + QueryDecomposer (Multi-Aspekt)
  │     • build_system_prompt → Top-4 Quellen (je 450 Z.) in System-Prompt
  │     • qwen3:8b (lokal Generalist) antwortet, geerdet
  │
  └─ IMPL/BUG_FIX/REFACTOR ──► WORKFLOW (workflow_agent, 6 Phasen)
        briefing → planning_strategy → planning_detailed → execution → verify → commit
        • Idiom-Router (semantisch, 36 Idioms)  • PredicateRegistry (deterministische Gates)
        • Regression-Guard + Static-Validator (Pre-Write)  • Healthpoint (Anti-Drift-Anker)
        • Idiom↔Ossifikat-Feedback-Schleife (lernt aus erfolgreichen Läufen)
        • Codegen: deepseek-coder:6.7b (lokal) ODER Claude (Cloud), je Ausführungs-Modus
```

**Grounding:** Ossifikat-Triple-Store — `verbürgte` Fakten haben Vorrang vor Vault-Quellen.
**Modi:** `deepseek-max` (alles lokal) · `mitte` (Claude plant/reviewt, deepseek codet) ·
`default` (Claude codet, deepseek validiert). **Council/P3:** optionaler Multi-Modell-Modus
(Claude/Gemini/Mistral), 4 `run_council`-Varianten.

---

## 3. Modul-Landschaft

| Bereich | Module | Status |
|---|---|---|
| **Kern-Orchestrierung** | `workflow_agent.py` (3.587), `terminal.py` (1.875), `agent_loop.py` (444) | ⚠️ Monolithen |
| **Retrieval** | `framework/quelibrium` (C++ `.so`), `vault_router`, `query_translator`, `query_decomposer`, `retrieval_service` | vendored Black-Box |
| **Harvest** | `harvest.py` (1.776), `tools_harvester` (546), `harvest_worker`, `harvest_scheduler` | groß |
| **Grounding** | `ossifikat/` (Submodule), `adapters/` (harvest/tools/terminal → Triples) | ✅ live |
| **Workflow-Logik** | `hotr/` (PredicateRegistry, WorkflowMemory), `choose/` (Predicate-Voting), `validator2.py`, `idiom_*`, `regression_guard` | ✅ live |
| **Infra** | `reqqueue/` (Queue, 512), `sandbox/` (Namespace-Exec), `tools/` (Registry), `logdb/` (499), `web/` (Auth+PTY) | ✅ live |
| **Scaffolds** | `models/` (ModelBackend-Abstraktion), `workflow/` (Phasen-Split) | 🟡 **0 Live-Imports** |
| **Archiv/Experiment** | `attic/` (6), `experiments/` (13), `chaosgarten/` (7), `choose_tests/` (7) | 💀 **0 Live-Imports**, gitignored |

---

## 4. Code-Qualität — Tiefenbefunde

### 4.1 Monolithen & Komplexitäts-Hotspots
Drei Dateien tragen ~7.200 LOC. Die Komplexität konzentriert sich in **Riesen-Funktionen**:

| Datei | Größte Funktion(en) | LOC |
|---|---|---|
| `workflow_agent.py` | `phase_execution()` · `_run_implementation_template()` · `phase_analysis_report()` · `phase_planning_detailed()` | 196 · 187 · 181 · 171 |
| `terminal.py` | `async main()` (REPL-Loop) · `_is_valid_answer()` · `analyze_deep()` | 262 · 104 · 100 |
| `harvest.py` | `harvest_tool_docs()` · `harvest_selfcode()` | 266 · 119 |

→ Funktionen >150 LOC sind weder unit-testbar noch isoliert nachvollziehbar.

### 4.2 Scaffolds (Schein-Fortschritt-Risiko)
- `models/` (ModelBackend/OllamaBackend) — **0 externe Imports**; die 4 Coder-Klassen in
  `terminal.py` (QwenCoder/ClaudeCoder/GeminiCoder/MistralCoder) sind unverändert.
- `workflow/` (base/code_analyzer/prompt_builder) — **0 externe Imports**; dupliziert
  Methoden aus `workflow_agent.py`, ersetzt sie nicht.
- `errors.py` — inzwischen **live** (verdrahtet über die Local-First-Fallback-Kette).

### 4.3 Toter / deaktivierter Code im Live-Pfad
- `terminal.py::analyze_deep()` (~100 LOC) — **definiert, nie aufgerufen** (Deep-Analysis-
  Aufruf auskommentiert, `# TODO: neu implementieren` Z.1797).
- `attic/`, `experiments/`, `chaosgarten/`, `choose_tests/` — 33+ Dateien, alle 0 Live-Imports.

### 4.4 Import-Fragilität
- **16 Module** mit `try: from vibelike.X … except ImportError: from X …`-Fallback —
  das Paket ist nicht sauber als `vibelike` importierbar, sondern verlässt sich auf
  dual-path-Hacks. **2 Module** mit `sys.path.insert`.
- `ossifikat`-Importe inzwischen konsistent `from ossifikat.store import …` (single),
  funktioniert da Submodule pip-editable installiert ist.
- **Lehre:** `pythonpath=.` in `pytest.ini` nötig, weil Root-Module (`errors`, `doctor`,
  `regression_guard` …) nicht Teil des `vibelike`-Pakets sind — strukturelle Inkonsistenz.

### 4.5 Hartkodierte Pfade (Portabilität)
- `config.py` — Wissens-Vault/Cache-Fallback auf `/home/jnrabit/collect/…` (env-überschreibbar)
- `framework/quelibrium/core/paths.py` — `ROOT = "/home/jnrabit/vibelike"` (vendored, fix)
- Daten-Substrat liegt **außerhalb des Repos** (`/home/jnrabit/collect/data/`) → nicht
  versioniert, anfällig für Drift durch parallele Sessions.

### 4.6 TODO/FIXME-Dichte
Nur **6 Marker** im Live-Code (sauber). Relevante: `agent_tools.py:144` (Sandbox nicht an
Agent-Tools verdrahtet), `terminal.py:1611/1797` (FileTool + Deep-Analysis deferred),
`workflow_agent.py:327` (relevanter Code nicht an Phase übergeben).

---

## 5. Retrieval-Pipeline (Kern)

- **Engine:** `framework/quelibrium` — C++ `libquelibrium.so` (8D-Chaos / Cortex /
  Thermal), Python-Wrapper `Protocol`. Pro Vault eine `Protocol`-Instanz (Archive +
  Embedding-Cache). **Black-Box** — nicht im Audit-Scope re-verifizierbar.
- **Dual-Vault:** `CodeRetriever.search()` (`terminal.py:315`) fragt Code- + Wissens-Engine
  je Query ab, merged per Cosine. `source_boost` für Projektcode-Priorisierung.
- **Vorverarbeitung:** QueryTranslator (DE→EN, da Vault EN-lastig), QueryDecomposer.
- **⚠️ Dokumentierter Vorbefund** (frühere Analyse, nicht hier re-verifiziert): C++
  `raw_search` war query-unabhängig (dist=0), `ChaosRetrieval` ist der tragfähige Pfad.
  → Vor Retrieval-Arbeit re-verifizieren.
- **Embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, **unnormalisiert**).

---

## 6. Tests & CI

- **21 Test-Dateien** (12 `tests/` + 9 Root) · **98 passed / 1 skipped / 0 failed**
- **Abgedeckt:** adapters, agent_loop, doctor, idiom_feedback, model_fallback, queue,
  regression_guard, requests, sandbox, tools, p3_parallel, action_decider
- **🔴 Lücke:** die drei Monolithen (`workflow_agent`, `terminal`, `harvest`) haben
  **keine** direkten Unit-Tests — zu groß/verflochten.
- **CI** (GitHub Actions): install → `doctor --fast` → pytest → regression-guard (report-only)
- **doctor** (lokaler Selbst-Check): syntax · config-Imports · Kern-Imports · regression
- **Pre-Commit-Hook:** Regression-Guard blockt unautorisierten Symbol-Verlust (`--no-verify`-Escape)

---

## 7. Security

| Element | Stand |
|---|---|
| `web/auth.py` (93 LOC) | Token + Capability-Tiers (read-only / Tier-1 …) |
| `web/terminal_ws.py` (146 LOC) | PTY-Terminal hinter Auth, `start_new_session=True` |
| `crypto.py` (192 LOC) | stable hashing / sealing |
| env-Key-Zugriff | 20 Module |
| Secret-Hygiene | `.env`/`opencode.json` (Live-Keys) aus History gepurged; Gemini-Key inaktiv; Fake-Test-Keys (`sk-1234…`) triggern kein GitHub-Scanning |
| **🟡 offen** | systemd-Isolation, ACL, Spend-Cap, Key-Rotation (Tasks #37/#38) |

---

## 8. Hardware & Performance

- **AMD RX 7600 / 8 GB VRAM**, **kein ROCm-torch** → `torch.cuda.is_available()=False` →
  Embeddings + manche Ops auf **CPU** (260k-Re-Embed = ~21 min).
- `qwen3:8b` (~6 GB Laufzeit) + `deepseek:6.7b` (~6 GB) **koexistieren nicht** → Ollama
  swappt beim Wechsel Wissen↔Code (~5–10 s Reload). Default-`keep_alive=30m`.

---

## 9. Stärken

1. **Deterministisches Sicherheitsnetz**: CI + doctor + Regression-Guard + Static-Validator
   — fängt Klassen von Fehlern, die LLM-Gates durchlassen (Symbol-Verlust, Datei-Kollaps,
   Config-Drift, Import-Brüche).
2. **Anti-Halluzinations-Architektur**: MONOLITH-Anker, authoritative Dateilisten,
   Healthpoint-Drift-Check, Ossifikat-Grounding, Grounding-Direktiven bei schwachen Quellen.
3. **Lokal-first mit Cloud-Fallback-Kette** (Quota → lokal) — härtet gegen Cloud-Fragilität.
4. **Selbst-lernend angelegt**: Idiom↔Ossifikat-Feedback-Schleife (geschlossener Kreis).
5. **Saubere Config-Schicht** (Pydantic, 47 Felder, env-überschreibbar) + getypte Errors.

---

## 10. Risiken & Empfehlungen (priorisiert)

| Prio | Risiko | Empfehlung |
|---|---|---|
| 🔴 **hoch** | 3 Monolithen, Riesen-Funktionen, **untestbar** | `workflow/`-Scaffold nutzen → `workflow_agent` in Phasen-Module splitten + Phasen-Tests; `terminal.main()` REPL extrahieren |
| 🟡 mittel | Scaffolds `models/`+`workflow/` ungenutzt | **verdrahten** (Phase 2) ODER explizit als Roadmap-Stub markieren — nicht als „done" liegen lassen |
| 🟡 mittel | Retrieval-Engine Black-Box + `raw_search`-Vorbefund | dokumentierten Befund **re-verifizieren** vor Retrieval-Arbeit; Engine-Verhalten in Tests pinnen |
| 🟡 mittel | Daten außerhalb Repo, hartkodierte Pfade, parallele Sessions | Daten-Pfade zentral via env; **eine aktive Session** zur Vermeidung von Daten-/Config-Drift |
| 🟡 mittel | Import-Fragilität (16 dual-Fallbacks, `pythonpath=.`) | Paket-Layout bereinigen — Root-Module ins `vibelike`-Paket ziehen |
| 🟢 niedrig | totes `analyze_deep` + Archiv-Zonen im Tree | entfernen oder explizit nach `attic/` |
| 🟢 niedrig | Cloud-Klassifikation (haiku) — local-first-Abweichung | optional `VIBELIKE_ANALYSIS_MODEL=qwen3:8b` |
| 🟢 niedrig | Security-Härtung #37/#38 offen | systemd-Isolation + Spend-Cap vor breiterem Exposure |
| 🟢 niedrig | kein ROCm | ROCm-torch für GPU-Embeddings (Harvest-Speed) |

---

## 11. Anhang — Metriken

```
Eigener Python-Code      : 139 Module, 27.572 LOC
Größte Module            : workflow_agent.py 3.587 · terminal.py 1.875 · harvest.py 1.776
Vendored                 : framework/ 1.049 LOC + .so · ossifikat/ 1.357 LOC
Config-Felder            : 47 (env-Prefix VIBELIKE_)
Tests                    : 21 Dateien, 98 passed / 1 skipped / 0 failed
Dead-Zonen               : attic(6) experiments(13) chaosgarten(7) choose_tests(7) — 0 Live-Imports
Scaffolds (0 Imports)    : models/ workflow/
Import-Fallback-Module   : 16 · sys.path-Hacks: 2
TODO/FIXME (Live)        : 6
Vaults                   : Code 1.733 docs · Wissen 258.873 docs (188k Basis + 70k ARXIV)
Modelle                  : deepseek-coder:6.7b (Code) · qwen3:8b (Wissen) · claude-haiku (Klassifik., API)
Hardware                 : AMD RX 7600, 8 GB VRAM, kein ROCm → CPU-Embeddings
```
