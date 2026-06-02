"""
run_analysis_test.py — Fährt EINE ANALYSIS-Frage durch den Workflow, um den
geboosteten Selfcode-Retrieval im Briefing live zu beobachten.

Auto-bestätigt alle Gates. Lokal (qwen3:8b), kein API-Call für Code-Gen.
Die Frage ist genau der Ausgangsfall, der diese Retrieval-Arbeit auslöste.
"""
import builtins
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

builtins.input = lambda *a, **k: "ja"

from workflow_agent import WorkflowAgent

TASK = "Analysiere, wie terminal.py's search() mit dem Code-Vault integriert ist."

if __name__ == "__main__":
    agent = WorkflowAgent()
    result = agent.run_workflow(TASK, max_iterations=1)

    print("\n\n" + "█" * 70)
    print("█  OBSERVATIONS-ZUSAMMENFASSUNG")
    print("█" * 70)
    print(f"task_type: {result.get('task_type')}")
    print(f"phasen: {list(result.get('phases', {}).keys())}")
    report = result.get("phases", {}).get("report", {})
    if report.get("report_path"):
        print(f"report_path: {report['report_path']}")
