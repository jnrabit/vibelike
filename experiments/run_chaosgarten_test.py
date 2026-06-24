"""
run_chaosgarten_test.py — Echte-Feature-Validierung des Workflows mit
MONOLITH-gegroundetem Claude-Codegen.

Baut ein self-contained Mini-Feature in NEUEM Ordner chaosgarten/ (kein Eingriff
in bestehenden Code). Validiert: Block-Selektor-Fallback (nichts Bestehendes
relevant), MONOLITH-Grounding, Codegen neuer Dateien, Verify (pytest), Commit.

Auto-bestätigt alle Gates. Schreibt echte Dateien + committet per Step.
"""
import builtins
import json
import sys
from pathlib import Path


builtins.input = lambda *a, **k: "ja"

from vibelike.workflow_agent import WorkflowAgent

TASK = (
    "Baue ein NEUES, eigenständiges Python-Modul im neuen Ordner chaosgarten/: "
    "eine Handshake-State-Machine für den Key-Exchange eines E2E-Messengers.\n\n"
    "Datei chaosgarten/handshake.py:\n"
    "- Enum HandshakeState mit INIT, KEY_EXCHANGED, CONFIRMED, FAILED.\n"
    "- Klasse Handshake mit Methode advance(event: str) -> HandshakeState.\n"
    "- Legale Übergänge: INIT --'send_key'--> KEY_EXCHANGED --'confirm'--> "
    "CONFIRMED; aus JEDEM nicht-finalen Zustand --'fail'--> FAILED.\n"
    "- Illegaler Übergang (Event passt nicht zum Zustand) wirft ValueError.\n"
    "- CONFIRMED und FAILED sind final: jeder weitere advance wirft ValueError.\n\n"
    "Schreibe pytest-Tests (chaosgarten/test_handshake.py) für legale Pfade "
    "und für illegale Übergänge (ValueError erwartet)."
)

if __name__ == "__main__":
    agent = WorkflowAgent()
    result = agent.run_workflow(TASK, max_iterations=1)

    print("\n\n" + "█" * 70)
    print("█  OBSERVATIONS-ZUSAMMENFASSUNG")
    print("█" * 70)
    print(f"task_type: {result.get('task_type')}")
    print(f"phasen: {list(result.get('phases', {}).keys())}")
    print(f"verdict: {result.get('verdict', {})}")
