#!/usr/bin/env python3
"""
Minimal-Context-Probe: Hypothese "Aufgabe schrumpfen trägt das kleine Modell".

Statt 650-Zeilen-Volldatei + abstraktes Format → nur die relevante Pattern-Liste
(~10 Zeilen) + EINE konkrete Anweisung. Task ist genuin fehlend (== True/False),
nicht schon vorhanden.

Misst: kommt ein anwendbarer SEARCH/REPLACE-Block, der byte-genau matched?
"""
import os
import re
import sys

os.environ.setdefault("VIBELIKE_QWEN_MODEL", "deepseek-coder:6.7b-instruct")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from workflow_agent import WorkflowAgent  # noqa: E402

VALIDATOR = "/home/jnrabit/vibelike/validator2.py"
full = open(VALIDATOR).read()

# Exakte Region als Anchor-Kontext (nur die Liste, nicht die Datei)
region = '''_BEST_PRACTICE_PATTERNS = [
    (r"^\\s*except\\s*:", "high", "bare_except", "bare except: — fängt alle Exceptions ab"),
    (r"^\\s*except\\s*Exception\\s*:", "medium", "generic_except", "except Exception: — fängt zu allgemein ab"),
    (r"\\bprint\\s*\\(", "low", "print_stmt", "print() statement — nutze Logger für Produktion"),
    (r"\\b\\d{3,}\\b", "low", "magic_number", "Magic Number (>2 Zeichen) — nutze Named Constants"),
    (r"TODO|FIXME|XXX|HACK", "low", "technical_debt", "Technische Schuld offen (TODO/FIXME)"),
    (r"\\bpass\\s*$", "low", "dead_code", "pass statement — Möglicher toter Code"),
    (r"\\bglobal\\s+\\w+", "medium", "global_state", "global statement — vermeide globale State-Mutation"),
    (r"\\bassert\\s+", "low", "assert_stmt", "assert statement — wird mit -O wegoptimiert"),
    (r"\\bfrom\\s+\\w+\\s+import\\s+\\*", "medium", "wildcard_import", "Wildcard Import — explizite Imports bevorzugen"),
]'''

assert region in full, "Region matched nicht byte-genau in validator2.py!"

agent = WorkflowAgent()
print(f"\n[PROBE] Code-Gen: {agent.qwen.model} | Minimal-Context ({len(region)} Z.)\n")

prompt = f"""Du erweiterst eine Python-Liste von Lint-Pattern-Tupeln.

Hier ist die bestehende Liste in validator2.py:

```python
{region}
```

Jedes Tupel hat das Format: (regex, severity, check_id, message).

AUFGABE: Füge ZWEI neue Tupel hinzu, die `== True` und `== False` flaggen
(Stil: man soll den Wert direkt nutzen). severity = "low".

Gib NUR einen SEARCH/REPLACE-Block aus, der die neuen Tupel vor der
schließenden `]` einfügt. Format:

## Datei: validator2.py
```python
<<<<<<< SEARCH
<exakter Code-Ausschnitt aus der Liste oben, byte-genau>
=======
<derselbe Ausschnitt plus die zwei neuen Tupel>
>>>>>>> REPLACE
```

Der SEARCH-Ausschnitt muss byte-genau aus der Liste oben stammen."""

print("[PROBE] === DEEPSEEK ANTWORTET ===\n")
out = agent.qwen.generate(prompt, temperature=0.1, stream=True)

# Diagnose: SR-Block extrahieren + gegen echte Datei testen
sr = re.search(r"<{5,}\s*SEARCH\s*\n(.*?)\n={5,}\s*\n(.*?)\n>{5,}\s*REPLACE", out or "", re.DOTALL)
print("\n\n[PROBE] === DIAGNOSE ===")
if not sr:
    print("  SR-Block            : KEINER gefunden")
    print("  VERDICT             : 🔴 kein anwendbarer Block")
else:
    search, replace = sr.group(1), sr.group(2)
    count = full.count(search)
    print(f"  SR-Block gefunden    : ja")
    print(f"  SEARCH-Länge         : {len(search)} Zeichen")
    print(f"  SEARCH matched in Datei: {count}× (1 = anwendbar)")
    has_true = "== True" in replace or "==\\s*True" in replace or "True" in replace
    has_false = "False" in replace
    print(f"  REPLACE enthält True/False: {has_true}/{has_false}")
    if count == 1 and has_true and has_false:
        verdict = "🟢 ANWENDBAR — Minimal-Context trägt deepseek"
    elif count == 1:
        verdict = "🟡 Block anwendbar, aber Inhalt zweifelhaft"
    else:
        verdict = f"🔴 SEARCH matched {count}× — nicht anwendbar"
    print(f"  VERDICT             : {verdict}")
