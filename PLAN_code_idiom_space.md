# Code-Idiom-Embedding-Space für HOTR Phase Routing

## Status Quo

**HOTR aktuell:**
- 5 Task-Typen (ANALYSIS, IMPLEMENTATION, BUG_FIX, REFACTOR, EXPLAIN)
- 6 Phasen (BRIEFING → PLANNING_STRATEGIE → PLANNING_DETAIL → EXECUTION → VERIFY → COMMIT)
- Task-Typ bestimmt das **Briefing-Framing** (zB ANALYSIS kriegt ERKENNTNISSE-Block)
- Phasen-Übergänge: linear, aber mit User-Feedback-Schleifen

**Problem:** *Implizite* Idiom-Wahl in jeder Phase.
- CLASSIFY-Phase: "Wähle Predicate-Voting vs Pattern-Match?" → hardcoded heuristic
- RETRIEVE-Phase: "BM25 vs Dense vs Hybrid?" → statisch konfiguriert, nicht adaptive
- PLANNING-Phase: "Brauchst du Beam-Search oder First-Feasible?" → ad-hoc entschieden

## Ziel

**Code-Idiom-Space:** Ein *gefrorenes* Embedding-Lookup-Wörterbuch, das zur **Laufzeit** innerhalb jeder Phase die beste **Strategie/Implementation-Pattern** wählt — *ohne dynamisches LLM-Reasoning*.

### Beispiel-Flow

```
Task: "analysiere /vibelike" 
  ↓
TaskClassifier → ANALYSIS
  ↓
[BRIEFING PHASE]
  "Ich brauch ne ERKENNTNISSE-Sektion mit konkrete Findings"
  → Lookup im Space: "analysis_briefing::with_synthesis"
  → Idiom sagt: "Verwende 2-Teil-Struktur (Detail + Synthese)"
  ↓
[PLANNING_STRATEGIE PHASE]
  "Wie gehe ich komplexen Code an?"
  → Lookup: "strategy_analysis::hierarchical_decomposition"
  → Idiom sagt: "Top-down: Architecture → Module → Functions"
  ↓
[EXECUTION PHASE]
  "Wie präsentiere ich die Analyse?"
  → Lookup: "execution_analysis::report_generation"
  → Code-Pattern + Template
```

### Zweites Beispiel (Hybrid Scenario)

```
Task: "retrieval braucht besser recall, aber wir haben wenig compute"
  ↓
IMPLEMENTATION
  ↓
[PLANNING_DETAIL]
  "Retrieval-Strategie? (schnell vs recall-optimiert)"
  → Context: "große codebase, vague query"
  → Lookup: "retrieve::strategy_constrained_budget"
  → Idiom sagt: "Hybrid: BM25 (schnell, recall-ok) + reranker (teuer, aber targeted)"
  ↓
[EXECUTION]
  → Idiom gibt dir Python-Pattern für Hybrid-Retrieval
```

---

## Architektur

### 1. Core: `CodeIdiomSpace` (frozen dict)

```python
@dataclass
class CodeIdiom:
    idiom_id: str                    # "analysis::briefing::two_part"
    phase: str                       # "briefing"
    task_type: str | None            # "ANALYSIS" oder None (task-agnostic)
    embedding: np.ndarray            # (384,) fixed, hardcoded
    description: str                 # "zwei Teile: Detail + Synthese"
    tags: list[str]                  # ["analysis", "synthesis", "structured"]
    complexity_hint: str             # "O(readtime)" — user-facing metric
    tradeoff: str                    # "thoroughness vs brevity"
    patterns: dict[str, str]         # "python" / "markdown" / "pseudo" → snippet
    requires: list[str]              # ["ossifikat", "retriever", "validator"]
    metadata: dict                   # custom fields (cost, latency, etc)
```

### 2. Compile-Time: `idiom_compiler.py`

- **Input:** YAML-Config mit Idiomen (human-readable, mit beschreibenden Texten)
- **Process:**
  1. Lade SentenceTransformer lokal (Ollama via HTTP)
  2. Für jeden Idiom: encode `{description + tags}` → fixed embedding
  3. Validiere Duplikate, Format, Abhängigkeiten
  4. Schreib frozen dict als JSON: `code_idioms.json`
- **Output:** `code_idioms.json` (5-10 KB, hardcoded embedded space)

### 3. Runtime: `phase_idiom_router.py`

```python
class PhaseIdiomRouter:
    """Bei Phase-Eintritt: wählt beste Idiom via Embedding-Lookup."""
    
    def __init__(self, idiom_space_path: str = "code_idioms.json"):
        self.space = load_frozen_space(idiom_space_path)
        self.model = load_local_sbert("paraphrase-MiniLM-L6-v2")
    
    def route(
        self,
        phase: str,
        task_type: str,
        requirement: str,  # user's natural lang request
        context: dict = None,  # {"has_retriever": true, "budget": "high", ...}
    ) -> CodeIdiom:
        """
        1. Filter Space auf (phase, task_type)
        2. Encode requirement
        3. Cosine-sim gegen alle Idiome in subset
        4. Top-1 + confidence threshold
        """
        subset = self.space.filter(
            phase=phase,
            task_type=task_type  # or None (task-agnostic idioms)
        )
        req_emb = self.model.encode(requirement)
        candidates = [
            (idiom, cosine_sim(req_emb, idiom.embedding))
            for idiom in subset
        ]
        best_idiom, score = max(candidates, key=lambda x: x[1])
        
        if score < 0.5:  # confidence threshold
            print(f"[WARN] Low confidence ({score:.2f}) — using fallback idiom")
            return self.fallback_idiom(phase, task_type)
        
        return best_idiom
```

### 4. Integration in WorkflowAgent

```python
class WorkflowAgent:
    def __init__(self):
        # ... existing ...
        self.idiom_router = PhaseIdiomRouter()
    
    def phase_briefing(self, task_type: str, context_text: str):
        # Alte Logik: task_type → BRIEFING_FRAMINGS[task_type]["role/body"]
        # Neue Logik:
        idiom = self.idiom_router.route(
            phase="briefing",
            task_type=task_type,
            requirement=f"Briefing für {task_type}-Task",
            context={"context_docs": bool(context_text)}
        )
        # Idiom sagt z.B. "analysis::briefing::two_part"
        # → Nutze idiom.patterns["markdown"] für Prompting
        role = idiom.patterns.get("system_prompt", "...")
        # ... continue with qwen.generate(role + ...) ...
```

---

## Idioms: Erste Draft (Pro Phase)

### PHASE: BRIEFING

| Idiom ID | Task Type | Description | Complexity |
|-----------|-----------|-------------|-----------|
| `brief::analysis::two_part` | ANALYSIS | Detail-Analyse (6 sections) + Synthesis (ERKENNTNISSE-Block) | High |
| `brief::analysis::quick` | ANALYSIS | Shallow scan, nur TL;DR + Risks | Low |
| `brief::impl::structured` | IMPLEMENTATION | Goal → Files → Embedding → Deps → Risks | Medium |
| `brief::impl::minimal` | IMPLEMENTATION | Just the essentials (goal + affected files) | Low |
| `brief::bugfix::root_cause` | BUG_FIX | Symptom → Hypothesis → Minimal Fix → Regression Risks | Medium |
| `brief::refactor::scope` | REFACTOR | Old Structure → New Structure → Diff → Testing Plan | Medium |
| `brief::explain::interactive` | EXPLAIN | Q→A format, encourage follow-up questions | Low |

### PHASE: PLANNING_STRATEGIE

| Idiom ID | Task Type | Description | Complexity |
|-----------|-----------|-------------|-----------|
| `strat::analysis::hierarchical` | ANALYSIS | Top-down: Arch → Module → Function | High |
| `strat::analysis::risk_first` | ANALYSIS | Start with known risks, then explore | Medium |
| `strat::impl::dependency_first` | IMPLEMENTATION | Topological sort: what must be built first | High |
| `strat::impl::incremental` | IMPLEMENTATION | Micro-commits: 1 feature ≤ 1 small file | Low |
| `strat::plan::hybrid_search` | (generic) | When unclear: combine 2-3 strategies | Medium |

### PHASE: PLANNING_DETAIL

| Idiom ID | Context | Description | Complexity |
|-----------|---------|-------------|-----------|
| `plan::retrieve::bm25_only` | Low budget, large corpus | Keyword-based, O(1) latency | Low |
| `plan::retrieve::dense_only` | GPU available, small corpus | Semantic embeddings, recall-focused | High |
| `plan::retrieve::hybrid_rerank` | Mixed budget, quality important | BM25 + dense + cross-encoder reranker | Very High |
| `plan::classify::pattern_match` | Few known task types | if-elif-else chain, O(k) classes | Very Low |
| `plan::classify::predicate_voting` | Many overlapping categories | Multiple predicates vote, union resolver | High |
| `plan::classify::ensemble` | Mission-critical accuracy | Voting + fallback + human-in-loop | Very High |
| `plan::execute::dry_run_diff` | Safety critical | Generate → Format → Diff → Human approval | High |
| `plan::execute::auto_apply` | Low-risk refactoring | Generate → Apply directly | Very Low |

### PHASE: EXECUTION

| Idiom ID | Task Type | Description | Pattern Type |
|-----------|-----------|-------------|--------------|
| `exec::analysis::report_gen` | ANALYSIS | Markdown report with tables/code-blocks | markdown_template |
| `exec::impl::code_gen` | IMPLEMENTATION | Python/Go/Rust code + docstrings | code_snippet |
| `exec::impl::git_workflow` | IMPLEMENTATION | Per-step commits (atomic changes) | bash_script |
| `exec::test_gen::pytest` | BUG_FIX / IMPLEMENTATION | Pytest fixtures + assertions | python_test |
| `exec::test_gen::property_based` | IMPLEMENTATION (edge-case heavy) | Hypothesis-based fuzzing | python_test |

### PHASE: VERIFY

| Idiom ID | Description | Complexity |
|-----------|-------------|-----------|
| `verify::test_and_measure` | Run tests + measure coverage/perf | High |
| `verify::lint_only` | Type-check + linter (no test execution) | Low |
| `verify::fuzzing` | Long-running property-based testing | Very High |

---

## Implementation Roadmap

### Step 1: Config + Compiler (Deterministic, Offline)

**File:** `idiom_config.yaml`
```yaml
idioms:
  - id: "brief::analysis::two_part"
    phase: "briefing"
    task_type: "ANALYSIS"
    description: "Detailanalyse mit 6 Sektionen + Synthese-Block"
    tags: ["analysis", "synthesis", "structured", "thorough"]
    complexity_hint: "High"
    tradeoff: "Thoroughness vs Brevity — favors Thoroughness"
    requires: ["analyzer_qwen"]
    patterns:
      system_prompt: "Du bist ein Senior Code-Architekt..."
      response_format: |
        ## TEIL A — DETAILANALYSE
        1. Verstehen Sie die Aufgabe korrekt?
        ...
        ## TEIL B — SYNTHESE
        ## ERKENNTNISSE
        ...
```

**File:** `idiom_compiler.py`
```bash
# Einmalig:
python3 idiom_compiler.py --config idiom_config.yaml --model paraphrase-MiniLM-L6-v2 --out code_idioms.json

# Output: code_idioms.json (5-10 KB, frozen space mit embeddings)
```

### Step 2: Runtime Router

**File:** `phase_idiom_router.py`
- Load `code_idioms.json`
- Init local SentenceTransformer
- Expose `.route(phase, task_type, requirement, context) → CodeIdiom`

### Step 3: Integration in WorkflowAgent

Replace:
```python
self.qwen.generate(BRIEFING_FRAMINGS[task_type]["role"] + ...)
```

With:
```python
idiom = self.idiom_router.route("briefing", task_type, context=...)
self.qwen.generate(idiom.patterns["system_prompt"] + ...)
```

### Step 4: Metrics

Track per-idiom:
- Latency (LLM generation time)
- User-approval rate (did user accept the idiom's output?)
- Retrieval-quality (if applicable)
- Cost (token-count)

---

## Benefits

1. **Deterministic:** No LLM→Routing overhead. Lookup is O(1) after filtering.
2. **Reproducible:** Same input → same idiom every time (same code_idioms.json).
3. **Explainable:** User sees "Using idiom: `analysis::briefing::two_part` (score: 0.87)".
4. **Composable:** Idioms can reference other idioms ("requires: ['brief::analysis::two_part']").
5. **Auditable:** Every idiom is versioned + documented.

---

## Questions for Refinement

- **How many idioms to start?** Sketch: 5-8 per phase × 6 phases ≈ 40-50 total?
- **Task-agnostic idioms?** Some idioms (e.g., hybrid-retrieve) don't care about ANALYSIS vs IMPL?
- **Context-aware refinement?** Should `route()` accept more context (e.g., codebase size, compute budget)?
- **Fallback strategy?** If confidence < threshold, use random from subset, or explicitly defined fallback?
- **Where to store embeddings?** Inline JSON (fast load) or separate binary (ONNX-style)?

