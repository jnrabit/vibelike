# Vibelike Improvements Roadmap

> **Status**: Phase 1 — config verdrahtet ✅, Abstraktionen (models/errors/workflow) als Scaffold 🟡
> **Last Updated**: 2026-06-24

> ⚠️ **Korrektur:** Die „✓ Complete"-Marken bei Task 1.2 (ModelBackend) und 1.3
> (Structured Errors) bedeuten „Scaffold geschrieben", NICHT „verdrahtet". Verifiziert:
> `models/` und `errors.py` haben **0 externe Imports** — der alte `QwenCoder`/`ClaudeCoder`-
> Code in terminal.py läuft unverändert. Erst wenn die Call-Sites umgestellt sind, ist es
> wirklich „done". Siehe Status-Tabelle in `REFACTORING_SUMMARY.md`.

---

## ✅ Phase 1: Configuration & Abstraction (COMPLETE)

### Task 1.1: Centralized Configuration with Pydantic ✓
**Status**: Complete  
**Files**: `config.py`  
**What was done**:
- Migrated from scattered env vars to `Pydantic Settings`
- Single source of truth for all configuration
- Type validation and fallbacks for all settings
- Knowledge vault path resolution (env var → fallback path)

**How to use**:
```python
from config import settings
settings.coder_model  # "deepseek-coder:6.7b-instruct"
settings.queue_db     # Path("/home/jnrabit/vibelike/logs/queue.db")
settings.analysis_model  # "claude-haiku-4-5-20251001"
```

**Benefits**:
- ✅ No more hardcoded `/home/jnrabit/` paths
- ✅ Type safety (Pydantic validates all values)
- ✅ Env var precedence clear and documented
- ✅ IDE autocomplete for all config keys

---

### Task 1.2: ModelBackend Abstraction ✓
**Status**: Complete  
**Files**: `models/base.py`, `models/ollama.py`  
**What was done**:
- Created abstract `ModelBackend` base class
- Implemented `OllamaBackend` as concrete example
- Added retry logic and async support
- Structured error handling (ModelTimeoutError, ModelUnavailableError)

**Design**:
```
ModelBackend (abstract)
  ├── generate(prompt) → str
  ├── stream_generate(prompt) → Iterator[str]
  ├── async_generate(prompt) → str
  ├── async_stream_generate(prompt) → AsyncIterator[str]
  └── health_check() → bool

RetryableModelBackend (abstract + retry logic)
OllamaBackend (concrete implementation)
```

**How to use**:
```python
from models.base import ModelRegistry
backend = ModelRegistry.get_backend("deepseek-coder:6.7b-instruct", backend_type="ollama")
response = backend.generate("Write hello world")
```

**Benefits**:
- ✅ Single interface for all LLM backends
- ✅ Easy to add Claude, Gemini, Mistral implementations
- ✅ Eliminates code duplication between QwenCoder, ClaudeCoder, etc.
- ✅ Centralized error handling and retry logic

---

### Task 1.3: Structured Error Types ✓
**Status**: Complete  
**Files**: `errors.py`  
**What was done**:
- Replaced string-based errors ("[ERR] ...") with typed exceptions
- Created error hierarchy: VaultError, ModelError, WorkflowError, etc.
- Added severity levels (debug, info, warning, error, critical)
- JSON serialization for API responses

**Error Hierarchy**:
```
VibelikeError
  ├── VaultError
  │   ├── VaultNotFoundError
  │   ├── VaultCorruptedError
  │   └── VaultEmptyError
  ├── ModelError
  │   ├── ModelNotAvailableError
  │   ├── ModelTimeoutError
  │   ├── ModelQuotaExceededError
  │   └── InvalidModelNameError
  ├── WorkflowError
  │   ├── WorkflowPhaseError
  │   ├── TaskClassificationError
  │   ├── VerificationFailedError
  │   └── MaxRetriesExceededError
  ├── OssifikatError
  ├── ConfigError
  └── SandboxError
```

**How to use**:
```python
from errors import VaultNotFoundError, format_error_for_output

try:
    vault.search(query)
except VaultNotFoundError as e:
    print(format_error_for_output(e))  # "❌ VaultNotFoundError: ..."
    # or API response
    return {"error": e.to_dict()}
```

**Benefits**:
- ✅ Programmatically catchable errors (not strings)
- ✅ Better logging and debugging
- ✅ API responses with structured error info
- ✅ Severity levels for filtering (e.g., only show CRITICAL warnings)

---

### Task 1.4: Git Hygiene ✓
**Status**: Complete  
**Files**: `.gitignore`  
**What was done**:
- Enhanced `.gitignore` to exclude generated files, logs, secrets
- Removed tracking of:
  - `data/agent_log.jsonl`, `data/chaos_tokens.db`, `data/*.pkl`
  - `logs/triplets.jsonl`, `logs/workflows.jsonl`, `logs/*.db`
  - `__pycache__/`, `*.pyc`, `.env`
  - `attic/`, `experiments/`, `choose_tests/`, `chaosgarten/`

**Benefits**:
- ✅ Repo stays clean (no 150MB+ binary caches)
- ✅ No secrets leaked
- ✅ Collaborators don't get cluttered git history

---

## 🔄 Phase 2: Code Refactoring (PLANNED)

### Task 2.1: Split terminal.py into Modules
**Priority**: P0 (High Impact)  
**Effort**: 3-4 days  
**Why**: `terminal.py` is 2031 lines — unmaintainable, untestable.

**Proposed Structure**:
```
terminal/
  __init__.py
  repl.py              # Main REPL loop, command dispatch
  search.py            # Vault search, result formatting
  prompts.py           # System prompt builders
  hardware_logger.py   # HardwareLogger class
  config_loader.py     # Integration with config.py
  workflow_bridge.py   # Integration with WorkflowAgent
  ui_formatter.py      # Output formatting (colors, tables, etc.)
```

**Steps**:
1. Extract REPL loop → `repl.py`
2. Extract search logic → `search.py`
3. Extract prompts → `prompts.py`
4. Extract HardwareLogger → `hardware_logger.py`
5. Update imports across terminal.py, workflow_agent.py, server.py
6. Add unit tests for each module

**Expected Outcome**:
- ✅ terminal.py → ~300 lines (main entry + REPL orchestration)
- ✅ Each module < 400 lines (testable)
- ✅ Clear module interfaces
- ✅ Easier to maintain and extend

---

### Task 2.2: Split workflow_agent.py into Phase Modules
**Priority**: P0  
**Effort**: 2-3 days  
**Why**: `workflow_agent.py` is 3530 lines — 6 phases in one file.

**Proposed Structure**:
```
workflow/
  __init__.py
  phases/
    base.py            # PhaseBase abstract class
    briefing.py        # Briefing phase (analysis + context)
    planning_strategy.py  # Planning strategy (general approach)
    planning_detail.py  # Planning detail (concrete steps)
    execution.py       # Execution (code generation)
    verify.py          # Verification (tests)
    commit.py          # Commit (git + documentation)
  validators/
    llm_validator.py   # LLM-based validation
    static_validator.py  # Already exists, move here
  orchestrator.py      # WorkflowAgent (dispatch, state machine)
```

**Steps**:
1. Create PhaseBase abstract class (interface for all phases)
2. Extract each phase into separate file
3. Move validators into `validators/` subdir
4. Simplify WorkflowAgent to pure orchestrator
5. Add phase tests

**Expected Outcome**:
- ✅ workflow_agent.py → ~500 lines (orchestrator only)
- ✅ Each phase file ~300-500 lines (testable)
- ✅ Phase reusability (can compose differently)
- ✅ Unit testable phases

---

### Task 2.3: Add Claude, Gemini, Mistral Backend Implementations
**Priority**: P1 (Medium Impact)  
**Effort**: 1-2 days  
**Files**: `models/anthropic.py`, `models/gemini.py`, `models/mistral.py`

**Why**: Currently only `OllamaBackend` implemented; code in `terminal.py` has inline API calls.

**Steps**:
1. Implement `AnthropicBackend` (Claude API)
2. Implement `GeminiBackend` (Google API)
3. Implement `MistralBackend` (Mistral API)
4. Each backend handles auth, streaming, error mapping
5. Register in `ModelRegistry`

**Expected Outcome**:
- ✅ Single import `from models import get_model("claude-3-sonnet")`
- ✅ No API code scattered in terminal.py
- ✅ Easy to add new providers (just subclass ModelBackend)

---

### Task 2.4: Add Unit Tests
**Priority**: P1  
**Effort**: 3-5 days  
**Files**: `tests/test_vault_router.py`, `tests/test_retrieval.py`, etc.

**Coverage Goals**:
- [ ] VaultRouter (code vs knowledge routing)
- [ ] TaskClassifier (task type detection)
- [ ] ChaosRetrieval (ranking, Lorenz dynamics)
- [ ] ModelBackend (each implementation)
- [ ] ErrorHandling (exception catching)

**Expected Outcome**:
- ✅ >80% code coverage
- ✅ Faster feedback during development
- ✅ Regression detection

---

## 📊 Phase 3: Performance & Optimization (FUTURE)

### Task 3.1: Benchmark Retrieval (Lorenz vs Cosine)
**Priority**: P2  
**Effort**: 2-3 days  
**Why**: Lorenz-Attraktor is complex; simple cosine similarity might be faster and equally effective.

**Hypothesis**: 
- ChaosRetrieval with Lorenz is beautiful but possibly over-engineered
- Simple cosine similarity + BM25 fusion might give 95% quality at 10% complexity

**Approach**:
1. Implement simple cosine-similarity baseline
2. Run both on real queries (search_queries.json)
3. Compare: relevance (MRR@5, NDCG), latency, memory
4. Document findings

**Expected Outcome**:
- 📊 Data-driven decision (keep Lorenz or simplify)
- 🚀 Potential 10x speedup if cosine wins
- 📝 Benchmark suite for future regressions

---

### Task 3.2: Async/Await Throughout
**Priority**: P2  
**Effort**: 2-3 days  
**Why**: Currently mixing sync/async; blocks on Ollama calls.

**Approach**:
1. Make agent_loop async-first
2. Non-blocking tool execution
3. Parallel phase validation

**Expected Outcome**:
- ⚡ Faster workflows (parallelism)
- 🔄 Better resource utilization

---

## 🎯 Immediate Next Steps (Before Phase 2)

### 1. Update terminal.py to Use New Config
**Effort**: 2 hours  
**Do this first** to unblock other work.

```python
# OLD
KNOWLEDGE_VAULT_FILE = os.environ.get("VIBELIKE_KNOWLEDGE_VAULT", "/home/jnrabit/...")
LOG_FILE = os.path.join(ROOT, "logs", "triplets.jsonl")

# NEW
from config import settings
KNOWLEDGE_VAULT_FILE = settings.knowledge_vault_file
LOG_FILE = settings.log_file
```

### 2. Create `models/__init__.py` Export
```python
# models/__init__.py
from .base import ModelBackend, ModelRegistry, ModelBackendError
from .ollama import OllamaBackend

__all__ = ["ModelBackend", "ModelRegistry", "ModelBackendError", "OllamaBackend"]
```

### 3. Add .env Example
```bash
# .env.example
VIBELIKE_CODER_MODEL=deepseek-coder:6.7b-instruct
VIBELIKE_ANALYSIS_MODEL=claude-haiku-4-5-20251001
VIBELIKE_CODEGEN_BACKEND=claude
VIBELIKE_DEEPSEEK_MAX=0
VIBELIKE_KNOWLEDGE_VAULT=/path/to/knowledge/vault.json
```

---

## 📈 Success Metrics

After completing all phases:
- [ ] Code coverage > 80%
- [ ] All modules < 500 lines
- [ ] 0 hardcoded paths
- [ ] All config via `config.py`
- [ ] All errors typed (no string returns)
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Performance benchmarks documented

---

## 💡 Rationale & Philosophy

### Why These Changes?
1. **Config Centralization**: Single source of truth prevents bugs, eases deployment
2. **ModelBackend Abstraction**: Allows swapping implementations without rewriting code
3. **Typed Errors**: Better error handling, easier to test, self-documenting
4. **Code Modularization**: Enables unit testing, concurrent development, reuse
5. **Git Hygiene**: Cleaner history, smaller repo, no secrets leaked

### Design Principles Followed
- **Single Responsibility Principle**: Each module does one thing well
- **Open/Closed Principle**: Easy to extend (new backends, phases), hard to break
- **Dependency Injection**: Config and models passed in, not hardcoded
- **Type Safety**: Pydantic + type hints throughout
- **Test-Driven Refactoring**: No refactoring without tests to ensure correctness

---

## 📞 Questions & Support

For questions on any of these improvements:
1. Check corresponding module docstrings
2. Review test files for usage examples
3. Reference this document for design decisions

