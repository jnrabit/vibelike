# Vibelike Integration Pipeline

## Overview

The vibelike system integrates three major components:

1. **Harvest** (Data Collection) - Gathers documents from Wikipedia, RFCs, PEPs, and tools
2. **Queue** (Job Management) - RequestQueue manages background harvesting tasks
3. **Adapter** (Knowledge Storage) - HarvestAdapter stores results in the ossifikat knowledge graph

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Interactive CLI (terminal.py)                                  │
│  - Search Code-Vault                                            │
│  - Review ossifikat triples ("r" command)                       │
└─────────────────────────────────────────────────────────────────┘
                              △
                              │
┌─────────────────────────────────────────────────────────────────┐
│  Background Harvesting Pipeline                                 │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │ Scheduler    │───→│   Queue      │───→│   Worker    │     │
│  │              │    │              │    │              │     │
│  │ harvest_     │    │ RequestQueue │    │ harvest_    │     │
│  │ scheduler.py │    │ (SQLite)     │    │ worker.py   │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│                                                  │               │
│                                                  ▼               │
│                                          ┌──────────────┐       │
│                                          │   Adapter   │       │
│                                          │              │       │
│                                          │ harvest_    │       │
│                                          │ adapter.py  │       │
│                                          └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Knowledge Storage                                              │
│  - Code-Vault (embeddings + documents)                         │
│  - Ossifikat (triples + staging workflow)                      │
│  - LogDB (events + execution logs)                             │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. HarvestScheduler (`harvest_scheduler.py`)

**Purpose:** Submit harvest jobs to the queue

**Usage:**
```python
from harvest_scheduler import HarvestScheduler

scheduler = HarvestScheduler()

# Schedule individual jobs
req_id = scheduler.schedule_wikipedia_harvest(limit=100, priority=1)
req_id = scheduler.schedule_rfc_harvest(limit=50, priority=2)
req_id = scheduler.schedule_pep_harvest(limit=50, priority=2)
req_id = scheduler.schedule_tools_harvest(limit=50, priority=2)

# Schedule batch
req_ids = scheduler.schedule_batch([
    {"operation": "harvest_wikipedia", "limit": 100},
    {"operation": "harvest_rfcs", "limit": 50},
])

# Check queue status
status = scheduler.get_status()
print(f"Pending: {status['pending']}, Running: {status['running']}")
```

**CLI:**
```bash
# Schedule individual operations
python harvest_scheduler.py wikipedia --limit 100 --priority 1
python harvest_scheduler.py rfcs --limit 50
python harvest_scheduler.py peps --limit 50
python harvest_scheduler.py tools --limit 50

# Schedule all operations
python harvest_scheduler.py batch --limit 50
```

### 2. HarvesterWorker (`harvest_worker.py`)

**Purpose:** Background process that dequeues and executes harvest jobs

**How it works:**
1. Polls the RequestQueue for pending jobs
2. Checks if operation is a harvest operation (starts with `harvest_`)
3. Calls the corresponding harvest function (via wrapper in harvest.py)
4. Logs results to ossifikat via HarvestAdapter
5. Marks request as completed or failed

**Usage:**
```python
from harvest_worker import HarvesterWorker

worker = HarvesterWorker()
worker.run()  # Infinite loop - process jobs until stopped
```

**CLI:**
```bash
# Run with default settings
python harvest_worker.py

# Run with custom database paths
python harvest_worker.py --queue-db custom/queue.db \
                         --harvest-db custom/ossifikat.db

# Process only 10 requests then exit
python harvest_worker.py --max-requests 10

# Custom poll interval (default: 5s)
python harvest_worker.py --poll-interval 2.0
```

### 3. Harvest Functions (in `harvest.py`)

**Wrapper functions** for background job processing:
- `harvest_wikipedia_worker(source, limit, **kwargs)` - Harvest Wikipedia
- `harvest_rfcs_worker(limit, **kwargs)` - Harvest RFCs  
- `harvest_peps_worker(limit, **kwargs)` - Harvest PEPs
- `harvest_tools_worker(limit, **kwargs)` - Harvest tool documentation

These create a CodeVaultWriter internally and call the original harvest functions.

### 4. RequestQueue (in `reqqueue/manager.py`)

**Purpose:** SQLite-based job queue with status tracking

**Key methods:**
- `enqueue(request)` - Add job to queue
- `dequeue()` - Get next pending job
- `complete(req_id)` - Mark job as completed
- `fail(req_id, error)` - Mark job as failed with retry
- `get_status()` - Get queue statistics
- `requeue_failed()` - Retry failed jobs with retry delay

### 5. HarvestAdapter (in `adapters/harvest_adapter.py`)

**Purpose:** Store harvested documents as ossifikat triples

**Methods:**
- `store_document(doc)` - Store a document triple
- `store_sector(sector, doc_count)` - Store sector summary
- `get_document_triples(doc_id)` - Retrieve document triples

## Workflow Examples

### Example 1: Manual Harvesting Session

```bash
# Terminal 1: Start scheduler and queue jobs
python -c "
from harvest_scheduler import HarvestScheduler
s = HarvestScheduler()
s.schedule_wikipedia_harvest(limit=50)
s.schedule_rfc_harvest(limit=30)
s.schedule_tools_harvest(limit=20)
print('Jobs scheduled!')
"

# Terminal 2: Start harvester worker
python harvest_worker.py

# Terminal 3: Monitor queue status
while true; do
  python -c "
  from harvest_scheduler import HarvestScheduler
  s = HarvestScheduler()
  status = s.get_status()
  print(f'Pending: {status[\"pending\"]} | Running: {status[\"running\"]} | Completed: {status[\"completed\"]}')
  "
  sleep 5
done
```

### Example 2: Scheduled Harvesting (using cron)

```bash
# Add to crontab: run daily harvest at 2 AM
0 2 * * * cd /path/to/vibelike && python harvest_scheduler.py batch --limit 100

# Background worker runs continuously
nohup python harvest_worker.py > logs/harvest_worker.log 2>&1 &
```

### Example 3: Interactive Terminal with Harvesting

```bash
# Terminal 1: Start worker (background)
python harvest_worker.py &

# Terminal 2: Start interactive terminal
python terminal.py

# In terminal.py:
# > my query
# [search and return results from vault]
# > r
# [review ossifikat staging with new documents]
```

## Data Flow

### Harvest Job Lifecycle

```
1. HarvestScheduler.schedule_*() 
   ├─ Create Request object
   ├─ Set operation (e.g., "harvest_wikipedia")
   └─ Enqueue via RequestQueue

2. RequestQueue stores in SQLite
   ├─ Status: "pending"
   ├─ Priority: X
   └─ Retries: 0

3. HarvesterWorker.run_once()
   ├─ Dequeue request
   ├─ Set status to "running"
   └─ Call harvest_*_worker()

4. harvest_*_worker()
   ├─ Create CodeVaultWriter
   ├─ Call original harvest function
   └─ Return number of docs added

5. Update status
   ├─ Success: mark "completed"
   └─ Failure: mark "failed" + schedule retry

6. (Optional) Store to ossifikat
   ├─ Via HarvestAdapter
   └─ Create doc + sector triples
```

## Database Schema

### RequestQueue (SQLite in `logs/queue.db`)

```sql
-- Requests
CREATE TABLE request_queue (
    id INTEGER PRIMARY KEY,
    req_id TEXT UNIQUE,           -- UUID
    payload TEXT,                 -- Serialized Request JSON
    priority INTEGER DEFAULT 0,   -- Higher = sooner
    status TEXT,                  -- pending|running|completed|failed|timeout
    retries INTEGER DEFAULT 0,    -- Attempt count
    next_attempt_at TIMESTAMP,    -- For retry scheduling
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Reminders for long-running/failed jobs
CREATE TABLE reminders (
    id INTEGER PRIMARY KEY,
    req_id TEXT,
    user TEXT,
    message TEXT,
    due_at TIMESTAMP,
    status TEXT,                  -- pending|sent|cancelled
    sent_at TIMESTAMP,
    FOREIGN KEY (req_id) REFERENCES request_queue(req_id)
);
```

### Ossifikat (in `ossifikat/data/ossifikat.db`)

```sql
-- Staging triples awaiting human confirmation
CREATE TABLE staging (
    id INTEGER PRIMARY KEY,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    source TEXT,
    created_at TIMESTAMP,
    confirmed_at TIMESTAMP
);

-- Confirmed triples
CREATE TABLE ossifikat (
    id INTEGER PRIMARY KEY,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    source TEXT,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP
);
```

## Error Handling

### Retry Logic

- **Max retries:** 3
- **Retry delays:** 
  - 1st retry: 5 minutes
  - 2nd retry: 5 minutes
  - 3rd retry: 5 minutes
  - After 3 failed: permanent failure

### Timeouts

- **Harvest timeout:** 20s per request (configurable)
- **Queue timeout:** Jobs marked as "timeout" after 20s execution
- **Health check:** Updates `/tmp/vibelike_queue_health` on each operation

## Monitoring

### Queue Status

```bash
# Quick status check
python -c "
from reqqueue.manager import RequestQueue
q = RequestQueue()
s = q.get_status()
print(f'Queue: {s.pending} pending, {s.running} running, {s.completed} completed')
"
```

### Logs

- **Queue events:** `logs/queue.db` (SQLite)
- **Harvest triplets:** `logs/triplets.jsonl` (JSON-Lines)
- **Worker output:** `logs/harvest_worker.log` (if nohup'd)
- **Adapter events:** `logs/execution.db` (LogDB)

### Performance

- **Throughput:** ~100-200 docs/minute (depends on network)
- **Memory:** ~2-4GB for full Wikipedia corpus
- **Disk:** ~5GB for Code-Vault with embeddings

## Configuration

### Environment Variables

```bash
# Device for embeddings (cuda/cpu)
export EMBEDDING_DEVICE=cuda

# Custom database paths
export VIBELIKE_QUEUE_DB=/path/to/queue.db
export VIBELIKE_HARVEST_DB=/path/to/ossifikat.db

# Poll interval (seconds)
export HARVEST_POLL_INTERVAL=5
```

### pyproject.toml Entry Points

```toml
[project.scripts]
vibelike-harvest-worker = "vibelike.harvest_worker:main"
vibelike-harvest-scheduler = "vibelike.harvest_scheduler:main"
```

When installed: `pip install -e .`

## Future Enhancements

1. **Distributed Workers** - Run multiple workers in parallel
2. **Priority Queue** - Better scheduling for high-priority jobs
3. **Progress Tracking** - Real-time harvest progress UI
4. **Incremental Updates** - Skip already-harvested sources
5. **Caching** - Cache pages to reduce network requests
6. **Compression** - Compress old logs and archives
