"""
run_imp_test.py — Faehrt EINEN Implementation-Task unbeaufsichtigt durch den
Workflow, um P12 + versiegelten Healthpoint + Drift-Checks live zu beobachten.

Auto-bestaetigt alle User-Gates (input -> 'ja'). NICHT fuer Produktiv-Nutzung —
nur Observations-Lauf. validator2.py ist git-committed; Diff danach pruefen.

max_iterations=1: kein langer Failure-Loop bei Test-Fail.
"""

import builtins
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Alle Workflow-Gates auto-bestaetigen
_real_input = builtins.input
builtins.input = lambda *a, **k: "ja"

from workflow_agent import WorkflowAgent

TASK = ("Füge zu validator2 einen Check hinzu, der Vergleiche mit == None oder "
        "!= None flaggt — sollte is None / is not None sein.")

if __name__ == "__main__":
    agent = WorkflowAgent()
    result = agent.run_workflow(TASK, max_iterations=1)

    print("\n\n" + "█" * 70)
    print("█  OBSERVATIONS-ZUSAMMENFASSUNG")
    print("█" * 70)
    print(f"task_type: {result.get('task_type')}")
    print(f"phasen: {list(result.get('phases', {}).keys())}")
    print("\nHEALTHPOINT-CHECKS:")
    print(json.dumps(result.get("healthpoint_checks", []), ensure_ascii=False, indent=2))
