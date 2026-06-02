"""
run_reactions_test.py — Härterer Ceiling-Test: Chat-Reaktionen + Zitat-Antworten
als self-contained Python-Modellschicht (chaosgarten/reactions.py).

Komplexer als die Handshake-State-Machine: mehrere Entitäten, Beziehungen
(Zitat-Referenzen), Toggle/Dedup-Logik, viele Edge-Cases. Validiert, wieviel
der Workflow (MONOLITH-gegroundeter Claude-Codegen) bei steigender Komplexität
schafft. Auto-confirm, schreibt echte Dateien + committet per Step.
"""
import builtins
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

builtins.input = lambda *a, **k: "ja"

from workflow_agent import WorkflowAgent

TASK = (
    "Baue die NEUE Datei chaosgarten/reactions.py: eine backend-agnostische "
    "Modellschicht für Chat-Reaktionen und Zitat-Antworten in einem E2E-Messenger.\n\n"
    "chaosgarten/reactions.py:\n"
    "- @dataclass Message mit Feldern: id (int), author (str), text (str), "
    "quote_of (int | None = None).\n"
    "- Klasse MessageThread mit:\n"
    "  - add_message(text, author, quote_of=None) -> Message: vergibt fortlaufende "
    "id ab 1. Ist quote_of gesetzt, aber keine Message mit dieser id vorhanden → ValueError.\n"
    "  - react(msg_id, user, emoji) -> None: fügt eine Emoji-Reaktion hinzu; "
    "dieselbe (user, emoji) zweimal ist idempotent. Unbekannte msg_id → ValueError.\n"
    "  - unreact(msg_id, user, emoji) -> bool: entfernt die Reaktion; True wenn "
    "entfernt, False wenn nicht gesetzt. Unbekannte msg_id → ValueError.\n"
    "  - counts(msg_id) -> dict[str, int]: Anzahl je Emoji. Unbekannte msg_id → ValueError.\n"
    "  - reactors(msg_id, emoji) -> list[str]: User, die mit diesem Emoji reagiert haben.\n"
    "  - resolve_quote(msg_id) -> Message | None: die zitierte Message, oder None "
    "wenn nichts zitiert wird. Unbekannte msg_id → ValueError.\n\n"
    "Schreibe pytest-Tests (chaosgarten/test_reactions.py): fortlaufende ids, "
    "Zitat auflösen, Zitat ins Leere (ValueError), react idempotent, unreact-"
    "Rückgabewert, counts/reactors, und alle ValueError-Edge-Cases (unbekannte msg_id)."
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
