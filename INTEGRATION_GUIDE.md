# Vibelike Integration Guide

## Overview

Vibelike is a **3-part integrated system** for code knowledge harvesting, tool documentation collection, and interactive CLI querying with ossifikat knowledge graph storage.

```
┌─────────────────────────────────────────────────────────────┐
│                    VIBELIKE ECOSYSTEM                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │  harvest.py  │   │ tools_harvest│   │ terminal.py  │    │
│  │              │   │er.py        │   │              │    │
│  │ Wikipedia    │   │ Tool Docs    │   │ Interactive  │    │
│  │ RFCs         │   │ Official Docs│   │ CLI          │    │
│  │ PEPs         │   │             │   │ + Hardware   │    │
│  │ Tool Docs    │   │             │   │   Logging    │    │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘    │
│         │                  │                   │             │
│         └──────────────────┼───────────────────┘             │
│                            │                                 │
│                   ┌────────▼────────┐                        │
│                   │  ADAPTERS       │                        │
│                   ├─────────────────┤                        │
│                   │ - HarvestAdapter│                        │
│                   │ - ToolsAdapter  │                        │
│                   │ - TerminalAdapter                        │
│                   └────────┬────────┘                        │
│                            │                                 │
│                   ┌────────▼────────┐                        │
│                   │   OSSIFIKAT     │                        │
│                   │  Triple Store   │                        │
│                   │ (Knowledge Base)│                        │
│                   └─────────────────┘                        │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         quelibrium Framework                           │ │
│  │  - Protocol (Hardware State)                           │ │
│  │  - Vault (Code Storage)                                │ │
│  │  - Retrieval (Chaos-based search)                      │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 1️⃣ HARVEST.PY - Data Collection

Collects structured knowledge from multiple sources and embeds it using multilingual embeddings.

### Sources (Phases)
- **basics**: Core CS concepts (algorithms, data structures, complexity)
- **languages**: Programming languages and frameworks
- **network**: Networking (TCP/IP, DNS, security)
- **advanced**: Compilers, OS, distributed systems, AI/ML
- **databases**: Relational/NoSQL/graph databases
- **security**: Cryptography, auth, vulnerability management
- **devops**: CI/CD, containers, infrastructure
- **algorithms**: Classic algorithms and data structures
- **tools**: Official tool documentation
- **rfc**: IETF RFC network standards
- **pep**: Python Enhancement Proposals

### Class: CodeVaultWriter
```python
from harvest import CodeVaultWriter

writer = CodeVaultWriter(device="cuda")  # or "cpu"
writer.add({
    "id": "unique-id",
    "content": "article text...",
    "title": "Article Title",
    "source": "WIKI_CS",
    "sector": "LANGUAGES",
    "lang": "en",
    "url": "https://...",
    "timestamp": "2024-05-18 10:00:00"
})
writer.flush()  # Save to disk
```

### Usage
```bash
# Harvest specific phase
python3 harvest.py --phase languages

# Harvest all phases
python3 harvest.py --phase all

# Or from code
from harvest import CodeVaultWriter, harvest_wikipedia_seeds
writer = CodeVaultWriter()
harvest_wikipedia_seeds(writer, seeds_de, "de", "LANGUAGES", "WIKI_CS_LANGUAGES")
```

## 2️⃣ TOOLS_HARVESTER.PY - Tool Documentation

Specialized harvester for official tool documentation (36 pre-configured sources).

### Covered Tools
- **Compilers**: GCC, Clang, Rust, Python, Go, Java, Fortran
- **Build Systems**: CMake, Bazel, Maven, Gradle, Cargo, npm
- **Test Runners**: pytest, JUnit, Google Test, Jest, Cypress
- **VCS**: Git, GitHub, GitLab, Mercurial
- **Debugging**: GDB, LLDB, Valgrind, perf
- **Shells & Scripting**: Bash, Python, AWK, sed, jq
- **Containers**: Docker, Kubernetes, Podman
- **CI/CD**: GitHub Actions, GitLab CI, Jenkins
- **Databases**: PostgreSQL, MySQL, Redis, MongoDB
- **Monitoring**: Prometheus, Grafana, ELK Stack

### Usage
```bash
# Harvest tool documentation
python3 tools_harvester.py

# Or integrated with harvest.py
python3 harvest.py --phase tools
```

## 3️⃣ TERMINAL.PY - Interactive CLI

Real-time Code-Vault querying with hardware state logging and qwen2.5-coder integration.

### Features
- **Code Retrieval**: C++-accelerated 8D Lorenz-attractor search
- **Generation**: qwen2.5-coder via Ollama
- **Hardware Logging**: Lorenz parameters, entropy, temperature, cortex-bias
- **Triplet Logging**: Query + context + response (JSON-Lines)

### Requirements
```bash
# Install dependencies
pip install sentence-transformers numpy requests

# Start Ollama (separate terminal)
ollama serve
ollama pull qwen2.5-coder:latest
```

### Usage
```bash
python3 terminal.py

# Then in terminal:
l          # Show last 10 logs
s          # Show hardware state
c          # Clear screen
q          # Quit
<query>    # Search code-vault and generate with qwen2.5-coder
```

### Class: HardwareLogger
```python
from terminal import HardwareLogger
from framework.quelibrium.core.protocol import Protocol

protocol = Protocol()
logger = HardwareLogger(protocol)
logger.log_state(query="example", label="search_start")
logger.log_triplet(query, context, response)
```

## 🔌 ADAPTERS - Knowledge Graph Integration

Bridge layer connecting all components with **ossifikat** triple-store.

### HarvestAdapter
Converts harvested documents into knowledge triples.

```python
from adapters import HarvestAdapter

adapter = HarvestAdapter()

# Store document
doc = {
    'id': 'WIKI-CS-001',
    'title': 'Python Programming',
    'source': 'WIKI_CS',
    'sector': 'LANGUAGES'
}
triple_id = adapter.store_document(doc, confirm=True)

# Store sector summary
adapter.store_sector("LANGUAGES", doc_count=42)
```

### TerminalAdapter
Stores terminal interactions as triples for audit trail.

```python
from adapters import TerminalAdapter

adapter = TerminalAdapter()

# Store query-response
query_id = adapter.store_query_response(
    query="What is Python?",
    response="Python is a versatile language",
    context_ids=["WIKI-CS-001"]
)

# Store hardware state
adapter.store_hardware_state(
    lorenz_params={"x1": 0.12, "y1": -0.34, ...},
    thermodynamics={"entropy": 3.14, "temperature": 45.0, ...},
    label="query_execution"
)
```

### ToolsAdapter
Stores tool metadata and relationships.

```python
from adapters import ToolsAdapter

adapter = ToolsAdapter()

# Store tool
tool_id = adapter.store_tool({
    'id': 'GCC-13',
    'sector': 'COMPILERS',
    'source': 'GCC_OFFICIAL',
    'urls': ['https://gcc.gnu.org/...']
})

# Store relationship
adapter.store_tool_relationship(
    tool_a='GCC-13',
    relationship='extends',
    tool_b='LLVM'
)

# Store sector summary
adapter.store_sector_summary("COMPILERS", tool_count=8)
```

## 🏗️ Framework Integration

### quelibrium Core
```python
from framework.quelibrium.core.protocol import Protocol
from framework.quelibrium.core.vault import Vault
from framework.quelibrium.core.paths import CODE_VAULT_FILE, CODE_CACHE_FILE
```

- **Protocol**: Hardware state (Lorenz parameters, entropy, temperature, cortex-bias)
- **Vault**: Encrypted code-vault storage (LZMA + Chaos-XOR cipher)
- **Retrieval**: ChaosRetrieval for 8D Lorenz-attractor based search

## 📊 Data Flow

```
harvest.py / tools_harvester.py
         ↓
    Documents
         ↓
  HarvestAdapter / ToolsAdapter
         ↓
   Triple Creation
         ↓
    Ossifikat Store
         ↓
    Terminal Queries
         ↓
  TerminalAdapter (logs interactions)
         ↓
  Audit Trail & Knowledge Graph
```

## 🚀 Quick Start

```bash
# Initialize project
cd /home/jnrabit/vibelike

# 1. Collect data
python3 harvest.py --phase basics
python3 harvest.py --phase tools

# 2. Verify collection
ls -lh ossifikat/data/ossifikat.db

# 3. Start interactive terminal
python3 terminal.py
```

## 📝 File Structure

```
vibelike/
├── harvest.py              # Data harvester (Wikipedia, RFCs, PEPs)
├── tools_harvester.py      # Tool documentation harvester
├── terminal.py             # Interactive CLI
├── adapters/               # Knowledge graph adapters
│   ├── __init__.py
│   ├── harvest_adapter.py
│   ├── terminal_adapter.py
│   └── tools_adapter.py
├── framework/quelibrium/   # Hardware + Retrieval engine
├── ossifikat/              # Knowledge triple-store (submodule)
├── reqqueue/               # Request queue management
├── sandbox/                # Sandbox execution
├── models/                 # Data models
├── tools/                  # Tool registry
└── logdb/                  # Logging database
```

## 🔍 Querying the Knowledge Base

### Programmatically
```python
from adapters import HarvestAdapter, TerminalAdapter
from ossifikat.store import OssifikatStore

store = OssifikatStore("ossifikat/data/ossifikat.db")

# Find all documents in a sector
docs = store.query(object="LANGUAGES", only_confirmed=False)

# Find query-response interactions
interactions = store.query(predicate="retrieved_answer")

# Find tool relationships
relationships = store.query(predicate="extends")
```

### Via CLI
```bash
# Use terminal.py for interactive querying
python3 terminal.py

# Or review staging triples
cd ossifikat && ossifikat review
```

## ⚙️ Configuration

All adapters use relative paths by default:
- Database: `ossifikat/data/ossifikat.db`
- Code Vault: `data/code_archive.monolith`
- Cache: `data/code_embedding_cache.pkl`

Override via constructor arguments:
```python
adapter = HarvestAdapter(ossifikat_db_path="/custom/path/ossifikat.db")
```

## 📚 Dependencies

- **sentence-transformers**: Multilingual embeddings (384-dim)
- **numpy**: Numerical operations
- **requests**: HTTP client (for Ollama API)
- **ossifikat**: Triple-store with staging workflow
- **numba**: JIT compilation for Lorenz attractor
- **sqlite3**: Databases (built-in)

## 🎯 Next Steps

1. **Expand Ossification Workflow**: Add confirmation CLI for triples
2. **REST API**: Add HTTP endpoints for querying
3. **Real-time Visualization**: Live Lorenz-attractor rendering
4. **Semantic Search**: Advanced similarity queries
5. **Ontology Support**: Formal knowledge representation

---

**Last Updated**: 2026-05-18  
**Status**: ✅ All components integrated and tested
