"""
bridges_to_ossifikat.py — schließt den Kreis Ideenfindung ↔ Wissens-Substrat.

bridge_finder skizziert Kandidaten-Brücken (A ↔ B: Rationale). Dieser Connector
parst sie und legt jede als Staging-Tripel (A, brückt_zu, B) in ossifikat ab —
NICHT in den bestätigten Store. Das staging->confirm->ossify-Gate bleibt die
Determinismus-Schiene: du ratifizierst die guten via `ossifikat review`, der
Rest verfällt. Ein schwaches Brücken-Modell kann den Wissensstand nicht vergiften.

Rationale-Erhalt: S/P/O hat kein Notizfeld. Die Brücken-Begründung wird parallel
nach data/bridge_rationales.jsonl geschrieben (triple_id -> Rationale), damit du
beim Review Kante UND Begründung zusammen siehst.

Aufruf:
    python3 experiments/bridges_to_ossifikat.py "deine Frage / dein Thema"
    # danach:  python3 -m ossifikat.cli review --db data/ossifikat.db
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ossifikat"))

from experiments.bridge_finder import find_bridges
from ossifikat.store import OssifikatStore

DB_PATH = "data/ossifikat.db"          # == CLI-Default, damit `ossifikat review` greift
RATIONALE_LOG = Path("data/bridge_rationales.jsonl")
PREDICATE = "brückt_zu"
SOURCE = "bridge_finder"
CONFIDENCE = 0.3                       # Kandidat/Spekulation, bewusst niedrig

# A ↔ B: Rationale  — robust gegen ↔ / <-> / <--> und Markdown/Klammer-Deko.
_ARROW = r"(?:↔|<-+>|<->)"
_LINE = re.compile(rf"^(.+?)\s*{_ARROW}\s*(.+?)\s*:\s*(.+)$")


def _clean(s: str) -> str:
    """Markdown-/Klammer-Deko, Listennummern und 'Brücke N:'-Präfixe abstreifen."""
    s = s.strip().strip("*").strip()
    s = re.sub(r"^\d+[\.\)]\s*", "", s)                       # "1. " / "1) "
    s = re.sub(r"^Brücke\s*\d+\s*:?\s*", "", s, flags=re.IGNORECASE)
    s = s.strip().strip("*").strip().strip("[]<>").strip()    # umschließende Klammern
    return s


def parse_bridges(bridges_text: str) -> list[tuple[str, str, str]]:
    """Zerlege den Brücken-Block in (A, B, Rationale)-Tripel. Rauschzeilen ignoriert."""
    out = []
    for raw in bridges_text.splitlines():
        m = _LINE.match(raw.strip())
        if not m:
            continue
        a, b, rationale = _clean(m.group(1)), _clean(m.group(2)), m.group(3).strip()
        if a and b:
            out.append((a, b, rationale))
    return out


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else \
        "Wie hängen chaotische Dynamik und Wissens-Retrieval zusammen?"
    print(f"\n{'='*70}\nQUERY: {query}\n{'='*70}")

    _pool, bridges_text = find_bridges(query, verbose=True)
    parsed = parse_bridges(bridges_text)
    if not parsed:
        print("\n[!] Keine parsebaren Brücken — nichts gestaged.")
        return

    store = OssifikatStore(DB_PATH)
    RATIONALE_LOG.parent.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        with open(RATIONALE_LOG, "a", encoding="utf-8") as log:
            for a, b, rationale in parsed:
                tid = store.add_staging(
                    subject=a, predicate=PREDICATE, object=b,
                    source=SOURCE, confidence=CONFIDENCE,
                )
                log.write(json.dumps(
                    {"triple_id": tid, "query": query, "rationale": rationale},
                    ensure_ascii=False) + "\n")
                staged.append((tid, a, b, rationale))
    finally:
        store.close()

    print(f"\n{'='*70}\n🪨 {len(staged)} Kandidaten-Brücken nach ossifikat-STAGING ({DB_PATH}):\n{'='*70}")
    for tid, a, b, rationale in staged:
        print(f"  #{tid}  {a} —[{PREDICATE}]→ {b}")
        print(f"        ↳ {rationale}")
    print(f"\nRationale-Log: {RATIONALE_LOG}")
    print(f"Review/Ratifizieren:  python3 -m ossifikat.cli review --db {DB_PATH}")


if __name__ == "__main__":
    main()
