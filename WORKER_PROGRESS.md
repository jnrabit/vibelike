# Harvest Worker Progress Visibility

## Problem Solved
Previously, the harvest worker would start but show no activity:
```
[2026-05-18 19:28:52,689] __main__: ✓ HarvesterWorker initialized
[2026-05-18 19:28:52,689] __main__: HarvesterWorker starting...
============================================================
HARVESTER WORKER
============================================================
[Press Ctrl+C to stop]
------------------------------------------------------------
[No more output - user doesn't know if it's working or hanging]
```

## Solution: Better Progress Visibility

Now the worker shows clear activity:

```
============================================================
HARVESTER WORKER
============================================================
[Press Ctrl+C to stop]
------------------------------------------------------------
[19:28:52] Ready. Waiting for harvest jobs...
------------------------------------------------------------
[19:28:55] Polling... | Pending: 2 | Running: 0 | Completed: 0 | Failed: 0
[19:29:01] ✓ Job completed | Pending: 1 | Completed: 1
[19:29:33] Starting: 811502b5... (harvest_wikipedia)
[harvest] Initializing Wikipedia harvester (device: cpu)
[harvest] Phase 1/2: basics
[wiki:de] Harvesting... (seed 1/45)
...progress from harvest functions...
[wiki:de] done: +15 docs, 2 skipped
[19:30:15] Polling... | Pending: 0 | Running: 1 | Completed: 1 | Failed: 0
```

## Key Improvements

### 1. Initial Ready Message
Shows the worker is initialized and waiting for jobs
```
[19:28:52] Ready. Waiting for harvest jobs...
```

### 2. Periodic Status Updates (every 30 seconds)
Shows the queue isn't stuck
```
[19:28:55] Polling... | Pending: 2 | Running: 0 | Completed: 0 | Failed: 0
```

### 3. Job Start Notification
Shows when a job begins processing
```
[19:29:01] ✓ Job completed | Pending: 1 | Completed: 1
[19:29:33] Starting: 811502b5... (harvest_wikipedia)
```

### 4. Harvest Operation Progress
Shows what each harvest operation is doing
```
[harvest] Initializing Wikipedia harvester (device: cpu)
[harvest] Phase 1/2: basics
[wiki:de] Harvesting... (seed 1/45)
```

### 5. Job Completion
Shows when jobs finish
```
[harvest] Wikipedia complete: +45 documents
[19:29:45] ✓ Job completed | Pending: 0 | Completed: 2
```

### 6. Shutdown Summary
Shows final statistics
```
[19:30:00] Final status: Completed: 2, Failed: 0, Pending: 0
```

## Output Timeline

### Immediately after startup
```
[HH:MM:SS] Ready. Waiting for harvest jobs...
```
**Interpretation:** Worker is running and listening

### Every 30 seconds (no jobs)
```
[HH:MM:SS] Polling... | Pending: N | Running: 0 | Completed: X | Failed: 0
```
**Interpretation:** Worker is actively checking the queue

### When a job arrives
```
[HH:MM:SS] Starting: XXXXXXXX... (harvest_operation)
[harvest] Initializing...
[harvest] Phase 1/N: name
[source] Harvesting... (seed N/M)
...
[harvest] Complete: +N documents
[HH:MM:SS] ✓ Job completed | Pending: X | Completed: Y
```
**Interpretation:** Worker found and is processing a job

### When shutting down (Ctrl+C)
```
[HH:MM:SS] Final status: Completed: N, Failed: 0, Pending: X
[BYE] Auf Wiedersehen
```
**Interpretation:** Worker is shutting down cleanly

## Usage

### Run with default settings
```bash
python harvest_worker.py
```

### Run with custom database
```bash
python harvest_worker.py --queue-db custom/queue.db
```

### Run with verbose logging
```bash
PYTHONUNBUFFERED=1 python harvest_worker.py
```

## What Each Status Means

| Status | Meaning |
|--------|---------|
| `Pending: 0` | No jobs waiting in queue |
| `Running: 0` | No jobs currently executing |
| `Completed: N` | N jobs have finished successfully |
| `Failed: 0` | No jobs have failed |
| `Polling...` | Worker is checking for new jobs |

## Monitoring the Worker

### In one terminal
```bash
python harvest_worker.py
# Shows real-time activity
```

### In another terminal - schedule jobs
```bash
python harvest_scheduler.py wikipedia --limit 100
python harvest_scheduler.py batch --limit 50
```

### Monitor progress
The worker terminal will immediately show:
1. Job start notification
2. Phase progress (for Wikipedia)
3. Document count updates
4. Job completion
5. Return to waiting state

## Troubleshooting with Progress Visibility

### Worker shows "Polling..." but no jobs start
- **Problem:** Queue might be empty
- **Solution:** `python harvest_scheduler.py wikipedia --limit 100`

### Worker shows a job started but no progress
- **Problem:** Harvest operation might be stuck or slow
- **Solution:** Check that network is working, or try with smaller limit

### Worker stops showing updates
- **Problem:** Worker might have crashed
- **Solution:** Check for error messages, restart with `python harvest_worker.py`

## Performance Notes

- Status updates appear every 30 seconds if queue is idle
- Job progress updates appear as harvest operations generate output
- Timestamp shows when event occurred (HH:MM:SS format)
- All times are in local timezone

## Example: Full Harvesting Session

```bash
# Terminal 1: Start worker
$ python harvest_worker.py
============================================================
HARVESTER WORKER
============================================================
[Press Ctrl+C to stop]
------------------------------------------------------------
[14:22:30] Ready. Waiting for harvest jobs...
------------------------------------------------------------

# Terminal 2: Schedule jobs
$ python harvest_scheduler.py wikipedia --limit 10
✓ Scheduled wikipedia harvest job: 12345678...

# Back in Terminal 1: Worker shows activity
[14:22:35] Starting: 12345678... (harvest_wikipedia)
[harvest] Initializing Wikipedia harvester (device: cpu)
[harvest] Phase 1/2: basics
[wiki:de] Harvesting... (seed 1/45)
[wiki:de] done: +8 docs, 2 skipped
[wiki:en] Harvesting... (seed 1/45)
[wiki:en] done: +12 docs, 1 skipped
[harvest] Wikipedia complete: +20 documents
[14:23:45] ✓ Job completed | Pending: 0 | Completed: 1
[14:23:45] Polling... | Pending: 0 | Running: 0 | Completed: 1 | Failed: 0

# Terminal 2: Schedule more jobs
$ python harvest_scheduler.py batch --limit 5
Scheduled 4 jobs...

# Back in Terminal 1: More jobs start
[14:23:50] Starting: 87654321... (harvest_rfcs)
[harvest] Starting RFC harvester (limit: 5)
...
[14:24:20] ✓ Job completed | Pending: 3 | Completed: 2

# And so on...
```

## Implementation Details

The improvements made:

1. **Status updates** - Every 30 seconds when queue is empty
2. **Job tracking** - Shows when jobs start and complete
3. **Progress logging** - Harvest operations print progress
4. **Time stamps** - All messages include HH:MM:SS
5. **Queue counters** - Shows pending/running/completed/failed counts
6. **Shutdown info** - Final statistics on ctrl+c

This gives users clear visibility into whether the worker is:
- Running and ready
- Waiting for jobs
- Processing jobs
- How many jobs are queued
- How many have completed
