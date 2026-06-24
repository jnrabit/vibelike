#!/usr/bin/env python3
"""
Refusal-Smoke-Probe: schickt den ECHTEN Execution-Prompt (inkl.
_build_existing_files_context mit validator2.py + SEARCH/REPLACE-Instruktionen)
an deepseek-coder statt qwen2.5-coder. Misst nur: Verweigert es?

Kein 6-Phasen-Lauf, kein File-Write. Reine Frage: kommen SR-Blocks oder eine
"tut mir leid, ich kann nicht"-Antwort?
"""
import os
import re
import sys

os.environ.setdefault("VIBELIKE_QWEN_MODEL", "deepseek-coder:6.7b-instruct")


from vibelike.workflow_agent import WorkflowAgent  # noqa: E402

agent = WorkflowAgent()
print(f"\n[PROBE] Code-Gen-Modell: {agent.qwen.model}\n")

briefing = {
    "task": "Füge in validator2.py einen Check hinzu, der `== None` und "
            "`!= None` als Stil-Problem flaggt (sollte `is None` / `is not None` sein)."
}
plan = {
    "plan": "Erweitere validator2.py: neues Regex-Pattern für `== None` / `!= None` "
            "in die Quality-Checks aufnehmen, mit severity 'low' und Message-Hinweis "
            "auf `is None`. Test in test_validator2.py ergänzen."
}

existing_context = agent._build_existing_files_context(plan["plan"])
print(f"[PROBE] existing_context: {len(existing_context)} Zeichen "
      f"(enthält validator2.py: {'validator2.py' in existing_context})\n")

LANG = os.environ.get("PROBE_LANG", "de")
print(f"[PROBE] Sprache: {LANG}\n")

if LANG == "en":
    # Englische Übersetzung des existing_context-Headers + Prompt
    existing_context_en = existing_context.replace(
        "BESTEHENDE DATEIEN (additiv erweitern, NICHT überschreiben):",
        "EXISTING FILES (extend additively, do NOT overwrite):",
    ).replace("ZU ERHALTENDE SYMBOLE:", "SYMBOLS TO PRESERVE:").replace("Zeilen)", "lines)")
    execution_prompt = f"""You are an expert code generator. Implement based on this plan:

ORIGINAL TASK:
{briefing['task']}

PLAN:
{plan['plan']}

{existing_context_en}REQUIREMENTS:
1. Write production-ready code
2. Follow the existing coding style
3. Include error handling
4. Write tests (pytest format)
5. Comment only when necessary

OUTPUT FORMAT:

For each EXISTING file (shown above under "EXISTING FILES") you write one or
more SEARCH/REPLACE blocks. The system applies them to the file — you do NOT
need to copy the whole file.

Format per block:
## File: <path>
```python
<<<<<<< SEARCH
<exact code snippet from the file, byte-for-byte>
=======
<new code snippet>
>>>>>>> REPLACE
```

Rules:
- The SEARCH snippet must occur exactly once in the file (otherwise widen the anchor).
- Reproduce whitespace and indentation exactly.
- Multiple changes -> multiple SEARCH/REPLACE blocks (even in one file).

For NEW files (not listed above) you write the complete content:
## File: <path>
```python
<complete file content>
```

## Tests: <path>
```python
<complete test content>
```

Generate complete, runnable code."""
else:
    execution_prompt = f"""Du bist ein Experten-Code-Generator. Implementiere basierend auf diesem Plan:

ORIGINALAUFGABE:
{briefing['task']}

PLAN:
{plan['plan']}

{existing_context}ANFORDERUNGEN:
1. Schreib produktionsreife Code
2. Folge dem bestehenden Coding-Style
3. Inkludiere Error-Handling
4. Schreib Tests (pytest-Format)
5. Kommentiere nur wenn nötig

OUTPUT-FORMAT:

Für jede BESTEHENDE Datei (oben unter "BESTEHENDE DATEIEN" gezeigt)
schreibst du einen oder mehrere SEARCH/REPLACE-Blocks. Das System
wendet sie auf die Datei an — du musst NICHT die ganze Datei kopieren.

Format pro Block:
## Datei: <pfad>
```python
<<<<<<< SEARCH
<exakter Code-Snippet aus der Datei, byte-genau>
=======
<neuer Code-Snippet>
>>>>>>> REPLACE
```

Regeln:
- SEARCH-Snippet muss genau 1× in der Datei vorkommen (sonst Anchor erweitern).
- Whitespace und Einrückung exakt übernehmen.
- Mehrere Änderungen → mehrere SEARCH/REPLACE-Blocks (auch in einer Datei).

Für NEUE Dateien (nicht oben gelistet) schreibst du den vollständigen Inhalt:
## Datei: <pfad>
```python
<kompletter Datei-Inhalt>
```

## Tests: <pfad>
```python
<kompletter Test-Inhalt>
```

Generiere kompletten, lauffähigen Code."""

print("[PROBE] === DEEPSEEK ANTWORTET ===\n")
code = agent.qwen.generate(execution_prompt, temperature=0.1, stream=True)

# Diagnose
sr_blocks = re.findall(r"<{5,}\s*SEARCH", code or "")
refusal_markers = [
    "tut mir leid", "kann ich nicht", "kann keine", "ich kann nicht",
    "keine möglichkeit", "keine berechtigung", "gegen", "i'm sorry",
    "i cannot", "i can't",
]
low = (code or "").lower()
hits = [m for m in refusal_markers if m in low]

print("\n\n[PROBE] === DIAGNOSE ===")
print(f"  Antwort-Länge      : {len(code or '')} Zeichen")
print(f"  SEARCH-Blocks       : {len(sr_blocks)}")
print(f"  Refusal-Marker      : {hits if hits else 'KEINE'}")
verdict = "🟢 KEIN REFUSAL" if (sr_blocks and not hits) else (
    "🟡 unklar" if sr_blocks else "🔴 REFUSAL / keine SR-Blocks")
print(f"  VERDICT             : {verdict}")
