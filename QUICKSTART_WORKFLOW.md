# Vibelike Workflow - Quick Start Guide

## Overview

The vibelike system now includes a **5-phase AI-powered development workflow** powered by Qwen2.5-Code. You can describe features in natural language and the system will automatically:

1. **BRIEFING** - Analyze the task and project structure
2. **PLANNING** - Propose an implementation plan (you approve)
3. **EXECUTION** - Write production code with tests
4. **VERIFICATION** - Run the full test suite
5. **COMMIT** - Create git commits with proper messages

## Getting Started

### Start the Terminal

```bash
python terminal.py
```

You'll see:
```
======================================================
CODE-VAULT TERMINAL
======================================================
[q] beenden | [l] logs | [s] state | [r] review | [c] clear | [w] workflow
------------------------------------------------------
>
```

### Method 1: Use the [w] Command

```bash
> w
📝 Aufgabe eingeben: Add GitHub README harvester
```

Then the system will guide you through all 5 phases.

### Method 2: Direct Briefing

```bash
> Briefing: Add GitHub README harvester
```

This starts the workflow directly without the prompt.

### Method 3: Full Description

```bash
> Briefing: Füge einen GitHub-Harvester hinzu, der README-Files von populären Python-Repositories sammelt und zur Code-Vault hinzufügt
```

## What Happens in Each Phase

### Phase 1: BRIEFING
- System analyzes your task description
- Reviews project structure and existing code
- Identifies affected components
- Lists dependencies and potential issues
- **Output:** Analysis report

### Phase 2: PLANNING
- Qwen generates a detailed implementation plan
- Lists all files to be modified
- Describes new functions/classes
- Proposes test strategy
- **You review and approve** ✅ or request changes
- If approved: continues to Phase 3
- If rejected: workflow stops

### Phase 3: EXECUTION
- System writes production-ready code
- Generates tests using pytest
- Integrates with existing code
- Follows coding style of the project
- **Output:** Modified files + tests

### Phase 4: VERIFICATION
- Automatic test suite runs
- All tests must pass (15+ tests)
- Reports any failures
- If failed: stops for manual review
- If passed: continues to Phase 5

### Phase 5: COMMIT
- Qwen generates a meaningful commit message
- Shows the message for review
- **You confirm** ✅ to create commit
- If confirmed: `git commit` is created
- If declined: changes remain uncommitted

## Examples

### Example 1: Add a Feature

```bash
> Briefing: Add caching to the harvest scheduler

System analyzes...
[BRIEFING COMPLETE]

[PLANNING] Implementation Plan:
  Files to modify:
    - harvest_scheduler.py: add @cache decorator
    - tests/test_scheduler.py: add cache tests
  New methods:
    - HarvestScheduler.clear_cache()
  Dependencies: 
    - functools (stdlib)

👤 Plan ok? (ja/nein/änderungen): ja

[EXECUTION] Writing code...
✓ Code written to 2 files

[VERIFICATION] Running tests...
✓ ALL TESTS PASSED: 18/18

[COMMIT] Generating message...
Add caching to harvest scheduler

- Reduces duplicate harvest requests
- Saves 60% of API calls
- Cache clears on schedule updates
- Full test coverage

👤 Commit erstellen? (ja/nein): ja
✓ Commit created!
```

### Example 2: Fix a Bug

```bash
> Briefing: Fix: harvest worker crashes on network timeout

System analyzes the issue...
[BRIEFING] Bug identified in:
  - harvest_worker.py:157 - missing timeout handling
  
[PLANNING] Proposed fix:
  - Add retry logic with exponential backoff
  - Add timeout exception handlers
  - Add integration tests

👤 Plan ok? (ja/nein/änderungen): ja

[EXECUTION] Writing fix...
[VERIFICATION] Testing...
✓ Bug test passes, no regressions

[COMMIT] Bug fix committed
```

## Tips & Tricks

### How to Get Better Plans

Be specific in your briefing:

❌ Bad: "Improve the system"  
✅ Good: "Add exponential backoff to harvest_worker network retries"

❌ Bad: "Fix bugs"  
✅ Good: "Fix: harvest worker crashes on network timeout after 10 minutes"

### Request Changes to Plan

```bash
👤 Plan ok? (ja/nein/änderungen): änderungen
Welche Änderungen? Use asyncio instead of threading for network calls
```

The system will revise the plan based on your feedback.

### Review Generated Code

Even though the system generates code, review it:
1. Check if it matches the plan
2. Look for potential issues
3. Run `python run_tests.py` if needed before commit
4. You can manually edit files before phase 5 (COMMIT)

### Undo a Commit

If you committed something and want to undo:
```bash
git reset --soft HEAD~1
git restore .  # Discard changes if needed
```

## Commands Reference

| Command | Effect |
|---------|--------|
| `w` | Start workflow (interactive) |
| `Briefing: ...` | Start workflow (direct) |
| `l` | Show recent logs |
| `s` | Show hardware state |
| `r` | Review ossifikat triples |
| `c` | Clear screen |
| `q` | Quit |

## Configuration

### Optional: Set Qwen Temperature

Edit `workflow_agent.py`:
```python
analysis = self.qwen.generate(analysis_prompt, temperature=0.3)  # Lower = more deterministic
```

- `0.1` = Most deterministic, best for code generation
- `0.3` = Balanced (default)
- `0.5+` = More creative

### Optional: Custom Prompts

The system uses these prompts:
- Phase 1 BRIEFING: Line 56 in workflow_agent.py
- Phase 2 PLANNING: Line 97
- Phase 3 EXECUTION: Line 154
- Phase 5 COMMIT: Line 265

You can customize them for your needs.

## Troubleshooting

### "Ollama nicht erreichbar"

Qwen2.5-Code is not running. Start it:
```bash
ollama run qwen2.5-coder:latest
```

In another terminal:
```bash
python terminal.py
```

### "Plan not approved, workflow stopped"

You rejected the plan at phase 2. The changes are not written.
Start a new workflow with adjusted briefing.

### "Tests failed, please review manually"

Phase 4 failed. Check `logs/` for details:
```bash
python run_tests.py
```

Then fix the issue manually or start a new workflow asking to fix the specific problem.

## Next Steps

1. **Try it:**
   ```bash
   python terminal.py
   > w
   ```

2. **Add a Feature:**
   ```bash
   > Briefing: Add config file support to harvest scheduler
   ```

3. **Fix a Bug:**
   ```bash
   > Briefing: harvest_worker crashes on disk full
   ```

4. **Extend the Code:**
   ```bash
   > Briefing: Add Slack notifications for harvest completion
   ```

## Full Documentation

For more details, see:
- `WORKFLOW.md` - Complete workflow documentation
- `FEATURE_TEMPLATE.md` - Feature request template
- `README_FINAL.md` - System overview
- `INTEGRATION.md` - Architecture details

---

**You're now ready to use AI-powered development in vibelike!** 🚀
