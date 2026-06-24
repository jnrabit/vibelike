#!/usr/bin/env python3
"""
Mikro-Probe (entscheidend): KEIN Patch-DSL. Modell liefert nur die neuen
Tupel-Zeilen, Python spleißt deterministisch vor die schließende ']'.

Trennt sauber: "kann SR-Format nicht" vs. "kann Task nicht".
Wenn deepseek hier sauber 2 valide Tupel liefert -> tragfähiges Design gefunden.
"""
import os
import re
import sys

os.environ.setdefault("VIBELIKE_QWEN_MODEL", "deepseek-coder:6.7b-instruct")
from vibelike.workflow_agent import WorkflowAgent  # noqa: E402

region = '''_BEST_PRACTICE_PATTERNS = [
    (r"^\\s*except\\s*:", "high", "bare_except", "bare except: — fängt alle Exceptions ab"),
    (r"\\bprint\\s*\\(", "low", "print_stmt", "print() statement — nutze Logger für Produktion"),
    (r"\\bassert\\s+", "low", "assert_stmt", "assert statement — wird mit -O wegoptimiert"),
]'''

agent = WorkflowAgent()
print(f"\n[PROBE] Code-Gen: {agent.qwen.model} | Mikro / kein DSL\n")

prompt = f"""Hier ist eine Python-Liste von Lint-Pattern-Tupeln:

```python
{region}
```

Format jedes Tupels: (regex, severity, check_id, message)

Gib mir AUSSCHLIESSLICH zwei neue Tupel-Zeilen (nichts sonst, kein Drumherum),
die `== True` und `== False` als Stil-Problem flaggen. severity = "low".
Jede Zeile genau im Format der bestehenden, mit 4 Leerzeichen Einrückung:

    (r"...", "low", "...", "..."),"""

print("[PROBE] === DEEPSEEK ANTWORTET ===\n")
out = agent.qwen.generate(prompt, temperature=0.1, stream=True)

# Extrahiere Tupel-Zeilen
lines = re.findall(r'^\s*\(r["\'].*?\),?\s*$', out or "", re.MULTILINE)
print("\n\n[PROBE] === DIAGNOSE ===")
print(f"  Tupel-Zeilen gefunden: {len(lines)}")
for ln in lines:
    print(f"    {ln.strip()}")

# Validiere: parsen sie als Python? + True/False abgedeckt?
ok = []
for ln in lines:
    try:
        val = eval(ln.strip().rstrip(","))
        ok.append(isinstance(val, tuple) and len(val) == 4)
    except Exception:
        ok.append(False)

joined = " ".join(lines)
has_true = "True" in joined
has_false = "False" in joined
parseable = sum(ok)

print(f"  Davon valide 4-Tupel : {parseable}")
print(f"  True / False drin     : {has_true} / {has_false}")

if parseable >= 2 and has_true and has_false:
    # Deterministischer Splice-Test
    spliced = region.replace("\n]", "\n    " + "\n    ".join(l.strip() for l in lines[:2]) + "\n]")
    try:
        compile(spliced, "<spliced>", "exec")
        verdict = "🟢 TRAGFÄHIG — Modell liefert Inhalt, Python spleißt, kompiliert"
    except SyntaxError as e:
        verdict = f"🟡 Tupel ok, aber Splice-Syntax kaputt: {e}"
else:
    verdict = "🔴 Modell liefert keine 2 validen Tupel"
print(f"  VERDICT             : {verdict}")
