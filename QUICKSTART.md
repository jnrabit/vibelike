# Vibelike Quick Start Guide

## System Overview

Vibelike is a knowledge harvesting and retrieval system with three main components:

1. **Terminal** - Interactive CLI for searching and reviewing knowledge
2. **Harvester** - Background system for collecting documents from Wikipedia, RFCs, PEPs
3. **Knowledge Graph** - Ossifikat-based storage with staging workflow

## Installation

```bash
# Install in development mode
cd /path/to/vibelike
pip install -e .

# Or run directly without installation
python terminal.py
python harvest_worker.py
python harvest_scheduler.py --help
```

## Basic Usage

### 1. Interactive Terminal (Search Mode)

```bash
python terminal.py
```

**Commands:**
- Type a query to search Code-Vault
- `q` - Quit
- `l` - View logs
- `s` - Show hardware state
- `r` - Review ossifikat triples (human-in-the-loop confirmation)
- `c` - Clear screen

### 2. Start Background Harvester

```bash
# Terminal 1: Start worker (listens for jobs)
python harvest_worker.py

# Terminal 2: Schedule harvest jobs
python harvest_scheduler.py wikipedia --limit 100 --priority 1
python harvest_scheduler.py rfcs --limit 50
python harvest_scheduler.py peps --limit 50
python harvest_scheduler.py tools --limit 50

# Terminal 3: Monitor progress
while true; do
  python -c "from harvest_scheduler import HarvestScheduler; \
  s = HarvestScheduler(); print(s.get_status())"
  sleep 5
done
```

### 3. Batch Harvesting

```bash
# Schedule all harvest types at once
python harvest_scheduler.py batch --limit 50

# Check queue status
python -c "
from harvest_scheduler import HarvestScheduler
s = HarvestScheduler()
status = s.get_status()
print(f'Queue: {status[\"pending\"]} pending, {status[\"completed\"]} completed')
"
```

## Architecture

```
User Input
    ↓
terminal.py ←→ Code-Vault (embeddings)
    ↓
[Search] ←→ ChaosRetrieval (Lorenz-8D)
    ↓
Results → ossifikat (staging)
    ↓
[Review "r"] → Human confirmation
    ↓
harvest_scheduler.py → RequestQueue
    ↓
harvest_worker.py → Process jobs
    ↓
harvest_*.py → Collect documents
    ↓
HarvestAdapter → Store in ossifikat
    ↓
Knowledge Graph (stable)
```

## Features

### Search (terminal.py)
- **ChaosRetrieval** - Uses 8D Lorenz attractor for retrieval
- **RiemannianWarp** - Time-dependent metric based on hardware state
- **ResonanceField** - Co-activation matrix for semantic retrieval
- **Thompson Sampling** - Exploration/exploitation balance

### Harvesting
- **Wikipedia** - Computer science topics (DE + EN)
- **RFCs** - Network and protocol specifications
- **PEPs** - Python Enhancement Proposals
- **Tools** - Compiler and IDE documentation

### Knowledge Storage
- **Code-Vault** - 384-dimensional embeddings (paraphrase-multilingual-MiniLM-L12-v2)
- **Ossifikat** - Knowledge graph with staging and confirmation workflow
- **LogDB** - Event logging and telemetry

## Configuration

### Environment Variables
```bash
export EMBEDDING_DEVICE=cuda          # or cpu
export VIBELIKE_QUEUE_DB=logs/queue.db
export VIBELIKE_HARVEST_DB=ossifikat/data/ossifikat.db
export HARVEST_POLL_INTERVAL=5        # seconds
```

### Database Paths
- Queue: `logs/queue.db` (SQLite)
- Logs: `logs/triplets.jsonl` (JSON-Lines)
- Ossifikat: `ossifikat/data/ossifikat.db` (Knowledge graph)
- Events: `logs/execution.db` (LogDB)

## File Structure

```
vibelike/
├── terminal.py                 # Interactive CLI
├── harvest.py                  # Document harvesting (Wikipedia/RFC/PEP)
├── harvest_scheduler.py        # Queue scheduling API
├── harvest_worker.py           # Background job processor
├── tools_harvester.py          # Tool documentation collector
│
├── framework/quelibrium/       # Advanced retrieval engine
│   ├── core/protocol.py        # Hardware state tracking
│   ├── core/vault.py           # Encrypted document storage
│   └── intelligence/           # Retrieval algorithms
│       ├── retrieval.py        # ChaosRetrieval, Warp, Thompson
│       └── resonance.py        # ResonanceField
│
├── adapters/                   # Knowledge graph adapters
│   ├── harvest_adapter.py      # Document storage
│   ├── terminal_adapter.py     # Query/response logging
│   └── tools_adapter.py        # Tool metadata
│
├── reqqueue/                   # Request queue system
│   └── manager.py              # SQLite job queue
│
├── models/                     # Data models
│   └── request.py              # Job request schema
│
├── logdb/                      # Event logging (formerly "logging/")
│   └── db.py                   # SQLite event store
│
└── pyproject.toml              # Package configuration
```

## Performance Metrics

- **Throughput:** ~100-200 documents/minute
- **Memory:** ~2-4GB for full Wikipedia corpus
- **Disk:** ~5GB for Code-Vault with embeddings
- **Queue polling:** 5 seconds (configurable)

## Troubleshooting

### "No module named 'vibelike'"
**Solution:** Run scripts from vibelike directory, or install: `pip install -e .`

### "RequestQueue not found"
**Solution:** Ensure `logs/` directory exists: `mkdir -p logs`

### "Ossifikat not found"
**Solution:** Install optional dependency: `pip install -e ".[ossifikat]"`

### Worker not processing jobs
**Solution:** 
1. Check queue: `python harvest_scheduler.py --help` (shows queue status)
2. Check logs: `tail -f logs/harvest_worker.log`
3. Ensure worker is running: `ps aux | grep harvest_worker`

### Ollama errors in terminal
**Solution:** Start Ollama server: `ollama serve` (in separate terminal)

## Examples

### Example 1: Search then harvest

```bash
# Terminal 1: Start harvester
python harvest_worker.py &

# Terminal 2: Search
python terminal.py
# > machine learning algorithms
# [Results from Code-Vault]

# Schedule related harvest
python harvest_scheduler.py wikipedia --limit 100 --priority 1

# Back in terminal.py
# > r
# [Review new documents in ossifikat]
```

### Example 2: Scheduled daily harvest

```bash
# In crontab (crontab -e)
0 2 * * * cd /home/jnrabit/vibelike && \
  python harvest_scheduler.py batch --limit 100

# Background worker runs all day
# In ~/.bashrc or systemd service:
# nohup python /path/to/harvest_worker.py \
#   > /var/log/vibelike_harvest.log 2>&1 &
```

### Example 3: API usage

```python
from harvest_scheduler import HarvestScheduler

# Create scheduler
scheduler = HarvestScheduler()

# Schedule jobs
wiki_id = scheduler.schedule_wikipedia_harvest(limit=100, priority=1)
rfc_id = scheduler.schedule_rfc_harvest(limit=50, priority=2)

# Monitor
status = scheduler.get_status()
print(f"Pending: {status['pending']}")
print(f"Completed: {status['completed']}")

# Retrieve job info
from reqqueue.manager import RequestQueue
queue = RequestQueue()
job = queue.get_request(wiki_id)
print(f"Status: {job.status}")
```

## Advanced Topics

See **INTEGRATION.md** for:
- Detailed architecture diagram
- Database schema
- Error handling and retries
- Monitoring and metrics
- Future enhancements

See **SESSION_SUMMARY.md** for:
- Completed work overview
- Implementation details
- Testing results
- Next steps

## Support

For issues or questions:
1. Check `INTEGRATION.md` for architecture details
2. Review `SESSION_SUMMARY.md` for implementation notes
3. Check logs: `logs/queue.db`, `logs/triplets.jsonl`
4. Run status check: `python /tmp/vibelike_status_check.py`

## License

MIT - See LICENSE file

---

**Ready to start?**

```bash
# 1. Start the worker
python harvest_worker.py

# 2. In another terminal, schedule jobs
python harvest_scheduler.py wikipedia --limit 50

# 3. In another terminal, use interactive search
python terminal.py
```

Happy harvesting! 🚀
