# 📖 VIBELIKE PROJECT SUMMARY
**Last Updated:** 2026-06-21  
**Status:** Hybrid-Mode Operational  

---

## 🎯 PROJECT OVERVIEW

**Goal:** Local-first, agent-based knowledge + code system without cloud dependency.

**Core Architecture:**
- **Terminal:** Python CLI for interactive queries + workflows
- **Server:** FastAPI web (port 8000) for remote access
- **Models:** Ollama (qwen2.5-coder:1.5b local) + API access (Claude Haiku, Mistral)
- **Retrieval:** Dual vault system (Code 1.7K docs + Knowledge 260K docs)
- **Workflow:** Hybrid 6-phase (Briefing → Plan → Execute → Verify → Commit → Review)

---

## 🏗️ ARCHITECTURE LAYERS

### **Layer 1: Task Entry**
```
User Input → TaskClassifier
  ├─ EXPLAIN (pure knowledge)
  ├─ IMPLEMENTATION (code generation)
  ├─ BUG_FIX (debugging)
  └─ REFACTOR (code improvement)
```

### **Layer 2: Routing (dispatch)**
```
dispatch(task_type)
  ├─ EXPLAIN → ExplainLoop [lightweight]
  │   ├─ CodeRetriever.search() (vault)
  │   ├─ Synthesize answer
  │   └─ Return
  │
  └─ IMPL/BUG/REFACTOR → ImplementationLoop [6-phase]
      ├─ Briefing (analysis + context)
      ├─ Planning (strategy + detailed plan)
      ├─ Execution (code generation)
      ├─ Verification (testing)
      └─ Commit (git + documentation)
```

### **Layer 3: Model Strategies**
- **Single Query:** Direct model call (fastest)
- **P3-Consensus:** All 3 models parallel → consensus winner
- **Hybrid-Vault:** Claude deep analysis + all 3 models with vault context
- **Council:** Lokal + multiple APIs → Sonnet synthesis

### **Layer 4: Persistence**
- **Triplets:** (query, context, response) logged to logs/triplets.jsonl
  - Stable SHA256 hashing (reproducible)
  - Hardware state tracking
- **Workflows:** Full execution logs in logs/workflows.jsonl
- **Ossifikat:** Facts + rationales in data/ossifikat.db

---

## 🔄 CURRENT CAPABILITIES

### ✅ WORKING
- ✅ w-mode (workflow) with task classification
- ✅ Knowledge Q&A (lightweight answer_knowledge path)
- ✅ Code generation + refactoring (6-phase)
- ✅ /api/query endpoint (REST + vault context)
- ✅ P3-Hybrid-Mode (all 3 models + vault)
- ✅ Vault retrieval (Code + Knowledge dual)
- ✅ Task history + logging
- ✅ Hardware state monitoring
- ✅ Git integration (auto-commits)

### ⚠️ KNOWN ISSUES
- **Queue test failure** (pre-existing, unrelated to hybrid)
  - Status: 'pending' instead of 'running' after dequeue()
  - Severity: LOW (doesn't block workflows)
  - Fix: Separate maintenance task

- **Import structure** (just fixed 2026-06-21)
  - Was: Only `vibelike.*` package imports
  - Now: Fallback to sys.path for script execution
  - Status: ✅ RESOLVED

### ❌ NOT IMPLEMENTED YET
- Context-based retrieval (currently query-based)
- Cross-loop communication (Implement → Review sequential)
- Healthpoint per-loop (currently single)
- Full task decomposition (multi-aspect queries)

---

## 📁 KEY FILES & LOCATIONS

### **Terminal & Core**
- `terminal.py` — Main CLI entry point
- `workflow_agent.py` — Task dispatch + 6-phase logic
  - Line 160: `dispatch()` method (hybrid router)
  - Line 182: `answer_knowledge()` (explain loop)
  - Line ~2980: `run_workflow()` (implementation loop)

### **Models & Inference**
- `terminal.py` — Model classes (QwenCoder, ClaudeCoder, MistralCoder)
- `agent_loop.py` — Agent execution framework
- `consensus.py` — Multi-model winner selection

### **Retrieval & Vault**
- `framework/quelibrium/core/vault.py` — Encrypted vault with JSON fallback
- `framework/quelibrium/core/protocol.py` — Protocol engine
- `framework/quelibrium/intelligence/retrieval.py` — ChaosRetrieval (semantic search)
- `framework/quelibrium/intelligence/resonance.py` — ResonanceField (embedding cache)

### **Web & API**
- `web/server.py` — FastAPI server (port 8000)
  - `/api/health` — Status
  - `/api/query` — Hybrid-mode REST endpoint
  - `/api/workflows` — Workflow history
  - `/ws/terminal` — Web terminal

### **Security & Crypto**
- `crypto.py` — Stable hashing (SHA256) + XOR encryption
- `web/auth.py` — Token-based auth (device + capabilities)

### **Persistence**
- `logs/triplets.jsonl` — Query-context-response triplets
- `logs/workflows.jsonl` — Full workflow execution logs
- `data/ossifikat.db` — Fact store (SQLite)
- `data/agent_log.jsonl` — Agent decision logs

---

## 🔧 CONFIGURATION

### **Environment Variables**
```bash
VIBELIKE_QWEN_MODEL=qwen2.5-coder:1.5b (local)
VIBELIKE_ANALYSIS_MODEL=claude-haiku-4-5-20251001 (API)
VIBELIKE_CODEGEN_MODEL=claude-sonnet-4-6 (API)
VIBELIKE_COUNCIL_MODEL=claude-haiku-4-5-20251001 (API)
VIBELIKE_RETRIEVAL_URL=http://127.0.0.1:8810 (optional daemon)
```

### **Hardware Constraints**
- GPU: AMD RX 7600 (8GB VRAM)
- CPU: ~16GB available
- qwen2.5-coder:1.5b → fits GPU fully
- No multi-7b models simultaneously (memory limitation)

---

## 📊 TEST STATUS

**pytest Results:** 30/31 PASS (96%)

✅ Passing:
- Adapter tests (7)
- Agent loop tests (9)
- P3 parallel tests (4)
- Action decider repair (8)
- Others (2)

❌ Failing:
- test_queue.py::test_enqueue_and_dequeue (pre-existing, LOW severity)

---

## 🎯 RECENT CHANGES (2026-06-14 to 2026-06-21)

### Commits
1. **9ab06f7** — P3-Hybrid-Mode (vault context for all 3 models)
2. **756656a** — /api/query REST endpoint
3. **ce322da** — Vault JSON fallback
4. **d180ce3** — gradlew auto-download (Android)
5. **d974c72** — Import fallback (package + script modes)

### Scope Changes
- 83 files modified (but mostly logging/infrastructure)
- Core logic changes: Clean and intentional
- Architecture: Evolved toward intelligent task routing

---

## 🚀 DEPLOYMENT STATUS

**Current:** Operational, can deploy  
**Blockers:** None  
**Warnings:** Queue test pre-existing (doesn't block)  

**Quick Start:**
```bash
python3 terminal.py  # Start CLI
curl http://localhost:8000/api/health  # Check server
```

---

## 💡 DESIGN DECISIONS

### **Why Hybrid Loops?**
Knowledge questions don't need 6-phase (overkill). Implementation tasks do.
→ dispatch() routes to appropriate loop based on task type.

### **Why Dual Vault?**
Code vault (1.7K) is fast + specific.  
Knowledge vault (260K) is broad coverage.  
→ Query both, merge results fairly.

### **Why P3-Consensus?**
Single model is weak (esp. 1.5b).  
3 models parallel + consensus = robust answers.  
→ Failure mode: disagree but diverse (good for user).

### **Why Stable Hashing?**
Python's `hash()` is non-deterministic across restarts.  
→ SHA256 + triplet logging enables reproducible debugging.

---

## 🔮 FUTURE OPPORTUNITIES

1. **Per-Loop Healthpoint** — Drift detection per task type
2. **Context-Based Retrieval** — Extract docs from existing context, not just query
3. **Cross-Loop Workflows** — Implement → Review sequential
4. **Task Decomposition** — Break multi-aspect queries into sub-tasks
5. **Local-Only Mode** — Use only Ollama (no API dependency)

---

## 📞 KEY CONTACTS / DOCS

- **Architecture:** MONOLITH.md (if exists)
- **Vault Format:** framework/quelibrium/core/vault.py
- **Model Config:** terminal.py (lines 57-77)
- **Tests:** tests/ directory (pytest)
- **Memory:** See GPU constraints section above

---

**For Future Claude Sessions:**  
This summary should give enough context to:
- Understand the architecture
- Know what's working + what's not
- Find relevant code quickly
- Make informed design decisions

*Last verified: 2026-06-21*

