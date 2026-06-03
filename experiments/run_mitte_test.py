"""
run_mitte_test.py — Experiment "ehrliche Mitte": Claude plant+reviewt, qwen-coder
codet als Worker. Läuft NUR mit VIBELIKE_ARCH=mitte sinnvoll.

Moderates Feature (Mention-Parser) — qwen-coder hat eine echte Chance auf einen
brauchbaren Draft, testet also den refine-Pfad. Beobachtet wird: Review-Verdict
(bless/refine/rewrite), Korrektheit (Tests), Speed.
"""
import builtins
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

builtins.input = lambda *a, **k: "ja"

from workflow_agent import WorkflowAgent

TASK = (
    "Baue die NEUE Datei chaosgarten/mentions.py: @-Mention-Parsing + Index für "
    "einen Chat-Messenger.\n\n"
    "chaosgarten/mentions.py:\n"
    "- Funktion extract_mentions(text: str) -> list[str]: gibt die mit '@' "
    "erwähnten Usernamen zurück (ohne das @), in Reihenfolge des Auftretens, "
    "dedupliziert. Ein Username besteht aus Buchstaben/Ziffern/Unterstrich nach "
    "dem @. '@' allein (ohne Namen) wird ignoriert.\n"
    "- Klasse MentionIndex mit:\n"
    "  - add(msg_id: int, text: str) -> None: parst die Mentions des Texts und "
    "indiziert, welche Message welchen User erwähnt.\n"
    "  - mentions_of(user: str) -> list[int]: die msg_ids, die diesen User "
    "erwähnen, in Einfüge-Reihenfolge, dedupliziert.\n"
    "  - mentioned_users(msg_id: int) -> list[str]: die in dieser Message "
    "erwähnten User. Unbekannte msg_id → [].\n\n"
    "Schreibe pytest-Tests (chaosgarten/test_mentions.py): einfache Mentions, "
    "mehrere/duplizierte Mentions, '@' allein ignoriert, Satzzeichen nach Mention, "
    "mentions_of über mehrere Messages, mentioned_users inkl. unbekannte msg_id."
)

if __name__ == "__main__":
    agent = WorkflowAgent()
    print(f"\n[EXPERIMENT] arch={agent.arch}\n")
    result = agent.run_workflow(TASK, max_iterations=1)

    print("\n\n" + "█" * 70)
    print("█  OBSERVATIONS-ZUSAMMENFASSUNG")
    print("█" * 70)
    print(f"arch: {agent.arch}")
    print(f"task_type: {result.get('task_type')}")
    print(f"review_verdict: {result.get('mitte', {}).get('review_verdict')}")
    print(f"verdict: {result.get('verdict', {})}")
