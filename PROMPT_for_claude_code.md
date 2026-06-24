# Claude Code Prompt: Code-Idiom-Embedding-Space für HOTR

## Context

Du baust ein **deterministic idiom routing system** für HOTR (6-Phasen-Workflow mit 5 Task-Typen).

Statt dass kritische Routing-Entscheidungen "ad-hoc" in Phase-Code hardcoded sind (z.B. "nutze _briefing_framing[task_type]"), wird ein gefrorenes Embedding-Lookup-Wörterbuch gebaut:

1. **Compile-Time:** YAML-Config → SentenceTransformer-Embeddings → `code_idioms.json` (frozen)
2. **Runtime:** Phase-Eintritt + Requirement → `phase_idiom_router.route()` → beste Idiom (O(1) Lookup nach Filter)
3. **Integration:** Replace `BRIEFING_FRAMINGS[task_type]` mit `idiom.patterns["system_prompt"]` etc.

## HOTR Phasen (aus workflow_agent.py)

```
0. TASK_KLASSIFIKATION     → TaskClassifier bestimmt Task-Typ
1. BRIEFING                → task_type-spezifische Rolle + Sektionen
2A. PLANNING_STRATEGIE     → allgemeines Vorgehen
2B. PLANNING_DETAILPLAN    → konkrete Durchführung + Retrieval-Strategie
3. EXECUTION               → Code-Gen + Dry-Run-Diff
4. VERIFICATION            → Tests laufen, bei Fehler: Failure-Analysis-Loop
5. COMMIT                  → Per-Teilschritt Git-Commits
```

Zusätzlich: `ANALYSIS_REPORT` (Special Case für ANALYSIS Task-Typ)

## Task-Typen (aus task_classifier.py)

```
ANALYSIS      → Projekt anschauen, Befunde liefern. KEINE Code-Änderung
IMPLEMENTATION → Neue Funktionalität. Code wird geschrieben
BUG_FIX       → Konkreten bekannten Fehler beheben
REFACTOR      → Code umstrukturieren, gleiches Verhalten
EXPLAIN       → Code/Konzept erklären (reine Wissensfrage)
```

## Deliverables

### 1. idiom_config.yaml (60-80 Idioms)

Schema pro Idiom:

```yaml
idioms:
  - id: "brief::analysis::two_part"
    phase: "briefing"
    task_type: "ANALYSIS"  # oder null für task-agnostic
    description: "6-teil Detailanalyse + Synthese-Block"
    tags: ["analysis", "synthesis", "thorough", "structured"]
    complexity_hint: "High"         # relativer Aufwand für LLM
    tradeoff: "Thoroughness vs Brevity — favors Thoroughness"
    requires: ["analyzer_qwen"]     # dependencies
    metadata:
      cost_estimate: "medium"
      latency_estimate: "high"
      approval_rate_target: 0.85
    patterns:
      system_prompt: |
        Du bist ein Senior Code-Architekt. Analysiere diese Aufgabe...
      response_format: |
        ## TEIL A — DETAILANALYSE
        ...
        ## TEIL B — SYNTHESE
        ## ERKENNTNISSE
        ...
      instructions: |
        - Alle 6 Sektionen ausfüllen (Pflicht)
        - ERKENNTNISSE-Block mit Findings
        - Keine Floskeln
```

**Idioms pro Phase (Schätzung):**

- BRIEFING: 8 (analysis::two_part, analysis::quick, impl::structured, impl::minimal, bugfix::root_cause, refactor::scope, explain::interactive, generic::skeleton)
- PLANNING_STRATEGIE: 6 (analysis::hierarchical, analysis::risk_first, impl::dependency_first, impl::incremental, refactor::staged, generic::hybrid_search)
- PLANNING_DETAILPLAN: 12 (retrieve::bm25_only, retrieve::dense_only, retrieve::hybrid_rerank, classify::pattern_match, classify::predicate_voting, classify::ensemble, execute::dry_run_diff, execute::auto_apply, verify::test_and_measure, verify::lint_only, verify::fuzzing, generic::adaptive)
- EXECUTION: 10 (analysis::report_gen, impl::code_gen, impl::git_workflow, bugfix::minimal_fix, refactor::structural_transform, test::pytest, test::property_based, test::integration, doc::auto_docstrings, generic::block_select)
- VERIFICATION: 5 (test_and_measure, lint_only, fuzzing, regression_check, coverage_analysis)
- COMMIT: 3 (per_step_commits, squash_logically, minimal_commits)
- ANALYSIS_REPORT: 4 (markdown_report, jupyter_notebook, interactive_html, structured_json)

**Total: ~50 idioms**

### 2. idiom_compiler.py

**Input:** `idiom_config.yaml`
**Output:** `code_idioms.json` (frozen Embeddings)

```python
python idiom_compiler.py --config idiom_config.yaml --model paraphrase-multilingual-MiniLM-L12-v2 --ollama http://localhost:11434 --out code_idioms.json
```

**Tasks:**
1. Lade YAML-Config
2. Validiere Schema (id, phase, task_type, patterns, etc)
3. Für jeden Idiom: `encode(description + " " + " ".join(tags))` via Ollama
4. Überprüfe Duplikate (Embeddings mit Cosine-Sim > 0.95)
5. Überprüfe Dependencies (if idiom requires X, X must exist)
6. Schreib frozen JSON:
   ```json
   {
     "metadata": {
       "model": "paraphrase-multilingual-MiniLM-L12-v2",
       "embedding_dim": 384,
       "timestamp": "2026-06-21T...",
       "count": 50
     },
     "idioms": [
       {
         "id": "brief::analysis::two_part",
         "phase": "briefing",
         "task_type": "ANALYSIS",
         "embedding": [0.123, -0.456, ...],  # 384-dim vector
         "description": "...",
         "tags": [...],
         ...
       }
     ]
   }
   ```
7. Optional: Validierungsbericht (Duplikate, Dependencies, Gaps)

### 3. phase_idiom_router.py

```python
from dataclasses import dataclass
from typing import Optional
import json
import numpy as np
from sentence_transformers import SentenceTransformer

@dataclass
class CodeIdiom:
    id: str
    phase: str
    task_type: Optional[str]
    embedding: np.ndarray
    description: str
    tags: list[str]
    complexity_hint: str
    tradeoff: str
    requires: list[str]
    patterns: dict[str, str]
    metadata: dict

class PhaseIdiomRouter:
    """Deterministic O(1) Idiom-Lookup nach Phase + Task-Typ + Requirement."""
    
    def __init__(self, space_path: str = "code_idioms.json", model_name: str = None):
        """
        space_path: Path zu frozen idioms JSON
        model_name: Optional SentenceTransformer name (default: paraphrase-multilingual-MiniLM-L12-v2)
        
        Bei first-load der idioms: lade SentenceTransformer (warm bis zum nächsten restart).
        """
        self.space = self._load_space(space_path)
        self.model_name = model_name or "paraphrase-multilingual-MiniLM-L12-v2"
        self.model = None  # lazy-load
    
    def _load_space(self, path: str) -> list[CodeIdiom]:
        """Lade frozen JSON, parse zu CodeIdiom-List."""
        pass
    
    def _ensure_model(self):
        """Lazy-load des SentenceTransformer."""
        if self.model is None:
            self.model = SentenceTransformer(self.model_name)
    
    def route(
        self,
        phase: str,
        task_type: Optional[str] = None,
        requirement: str = "",
        context: Optional[dict] = None,
    ) -> CodeIdiom:
        """
        Route zu beste Idiom für die Phase.
        
        Args:
            phase: "briefing", "planning_strategie", "planning_detailplan", etc
            task_type: "ANALYSIS", "IMPLEMENTATION", etc (oder None)
            requirement: Natürlichsprachige Anforderung (z.B. "ich brauch tiefgang")
            context: {
                "has_retriever": bool,
                "budget": "low" | "medium" | "high",
                "codebase_size": "small" | "medium" | "large",
                "api_available": bool,
                "compute_available": bool,
                ...
            }
        
        Returns:
            CodeIdiom mit beste Cosine-Sim gegen requirement-Embedding
        
        Algo:
        1. Filter self.space auf (phase + task_type OR task_type=None)
        2. Encode requirement via self.model
        3. Cosine-Sim gegen alle filtered idioms
        4. Top-1 (confidence threshold: 0.45)
        5. Bei <threshold: fallback-idiom
        """
        pass
    
    def _filter_by_context(
        self,
        idioms: list[CodeIdiom],
        context: dict
    ) -> list[CodeIdiom]:
        """
        Optional: Filter idioms basierend auf Context-Constraints.
        
        Z.B.:
        - "retrieve::hybrid_rerank" hat metadata.cost_estimate="high"
          → Filtern wenn context["budget"]="low"
        - "retrieve::dense_only" requires GPU
          → Filtern wenn context["compute_available"]=False
        """
        pass
    
    def fallback_idiom(self, phase: str, task_type: Optional[str] = None) -> CodeIdiom:
        """
        Bei Confidence < threshold: wähle robuste Fallback-Idiom.
        
        Fallback-Strategie pro Phase:
        - BRIEFING: "brief::*::skeleton" (minimal, aber sicher)
        - PLANNING_DETAILPLAN: "plan::*::adaptive" (passt sich an)
        - EXECUTION: "exec::*::safe_mode" (mit Validierung)
        - etc
        """
        pass
    
    def list_idioms_for_phase(self, phase: str, task_type: Optional[str] = None) -> list[CodeIdiom]:
        """Debug-Utility: List alle Idioms für eine Phase."""
        pass


# Integration in WorkflowAgent

class WorkflowAgent:
    def __init__(self):
        # ... existing ...
        self.idiom_router = PhaseIdiomRouter(space_path="code_idioms.json")
    
    def phase_briefing(self, task: str, task_type: str = "IMPLEMENTATION") -> dict:
        """Phase 1: Analyse der Aufgabe."""
        
        # Route zur beste Briefing-Idiom
        idiom = self.idiom_router.route(
            phase="briefing",
            task_type=task_type,
            requirement=f"Briefing für {task_type} task",
            context={"codebase_size": "large", "budget": "medium"}
        )
        
        # … gather project info, code, etc (wie zuvor) …
        
        # STATT: framing = self._briefing_framing(task_type)
        # JETZT:
        role = idiom.patterns.get("system_prompt", "")
        body = idiom.patterns.get("response_format", "")
        
        # Logging für Debugging
        print(f"[ROUTING] BRIEFING idiom={idiom.id} (confidence={idiom.metadata.get('confidence', 'N/A')})")
        
        # Qwen analysiert
        analysis_prompt = f"""{role}
        
        {monolith_block}
        AUFGABE:
        {task}
        ...
        {body}
        """
        
        analysis = self.analyzer_qwen.generate(analysis_prompt, ...)
        # … continue as before …
    
    def phase_planning_detailplan(self, briefing: dict, strategy: dict) -> dict:
        """Phase 2B: Detailplan mit Retrieval-Strategie-Routing."""
        
        # Route zur beste Retrieval-Strategie
        retrieval_idiom = self.idiom_router.route(
            phase="planning_detailplan",
            task_type=None,  # task-agnostic
            requirement="wähle retrieval strategie für semantic search",
            context={
                "has_retriever": True,
                "budget": "medium",
                "codebase_size": "large",
                "api_available": True,
            }
        )
        
        print(f"[ROUTING] RETRIEVAL idiom={retrieval_idiom.id}")
        
        # Idiom sagt z.B. "plan::retrieve::hybrid_rerank"
        retrieval_section = retrieval_idiom.patterns.get("instructions", "")
        
        # Build detail-plan-prompt mit dieser Retrieval-Strategie
        plan_prompt = f"""... 
        
        RETRIEVAL-STRATEGIE:
        {retrieval_section}
        
        ... rest of prompt ...
        """
        
        plan = self.analyzer_qwen.generate(plan_prompt, ...)
        # … continue …
```

### 4. Tests

```python
# tests/test_phase_idiom_router.py

def test_router_loads_space():
    """Space lädt korrekt."""
    pass

def test_route_briefing_analysis():
    """BRIEFING-Phase mit ANALYSIS task-type."""
    idiom = router.route("briefing", task_type="ANALYSIS", requirement="...")
    assert idiom.id.startswith("brief::analysis")
    assert "two_part" in idiom.id or "quick" in idiom.id

def test_route_planning_detailplan_retrieval():
    """PLANNING_DETAILPLAN mit Retrieval-Kontext."""
    idiom = router.route(
        "planning_detailplan",
        task_type=None,
        requirement="retrieval",
        context={"budget": "high"}
    )
    assert idiom.id.startswith("plan::retrieve")

def test_context_filtering():
    """Context constraints filtern Idioms."""
    # "hybrid_rerank" hat cost=high, sollte bei budget=low gefiltert werden
    idiom = router.route(
        "planning_detailplan",
        requirement="retrieval",
        context={"budget": "low"}
    )
    assert "rerank" not in idiom.id

def test_fallback_on_low_confidence():
    """Confidence < threshold → fallback."""
    idiom = router.route(
        "briefing",
        requirement="xyzabc irgendein nonsense text",
    )
    assert idiom is not None
    assert idiom.metadata.get("is_fallback", False)

def test_compile_no_duplicates():
    """idiom_compiler erkennt Duplikate."""
    # 2 Idioms mit identischen embeddings sollten Warnung/Error bringen
    pass

def test_compile_dependency_check():
    """idiom_compiler prüft, dass required idioms existieren."""
    pass
```

### 5. Integration-Checklist

**Phase 1: Setup**
- [ ] Erstelle `idiom_config.yaml` mit ~50 Idioms (alle 7 Phasen)
- [ ] Implementiere `idiom_compiler.py`
- [ ] Generiere `code_idioms.json`
- [ ] Implementiere `phase_idiom_router.py`

**Phase 2: Integration**
- [ ] `WorkflowAgent.phase_briefing()` nutzt `idiom_router.route()`
- [ ] `WorkflowAgent.phase_planning_detailplan()` nutzt Router für Retrieval-Strategie
- [ ] `WorkflowAgent.phase_execution()` nutzt Router für Code-Gen/Test-Strategie
- [ ] Logging: jede Route druckt Idiom-ID + Confidence

**Phase 3: Testing**
- [ ] Unit Tests: `test_phase_idiom_router.py`
- [ ] Integration Tests: Route in echo Phase mit echtem Task
- [ ] Metrics: Confidence-Distribution, Approval-Rate per Idiom

**Phase 4: Monitoring**
- [ ] Track per-Idiom: Nutzung, User-Approval, Latenz, Token-Cost
- [ ] Optional: Feedback-Loop zum Retrain/Reweight Idiom-Space

## Code-Struktur

```
vibelike/
├── phase_idiom_router.py          # PhaseIdiomRouter class
├── idiom_compiler.py               # Compile YAML → JSON
├── code_idioms.json                # Frozen space (generated)
├── idiom_config.yaml               # Human-editable config
└── tests/
    ├── test_phase_idiom_router.py
    └── test_idiom_compiler.py
```

## Notes

- **Keine LLM-Overhead:** Router nutzt fest-encodierte Embeddings, kein re-encoding bei jeder Route
- **Reproduzierbar:** Identische Input → identische Idiom (kein RNG, kein floating-point-Variance)
- **Explainierbar:** `print(f"Using idiom {idiom.id} (score: {score:.2f})")` macht Routing sichtbar
- **Erweiterbar:** Neue Idioms in YAML hinzufügen → `idiom_compiler.py --regenerate` → neue JSON
- **Kontext-aware:** Router kann Context-Constraints nutzen (Budget, Compute, API-Verfügbarkeit)

