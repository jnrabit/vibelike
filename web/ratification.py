"""
web/ratification.py — reversible Ratifizier-Zustände über dem ossifikat-Staging.

ossifikat kennt nur staging → confirmed (+ ein hartes, löschendes reject). Für eine
*humane* Ratifizierung braucht es reversible Zwischenzustände, OHNE den append-only
ossifikat-Kern zu verbiegen:

  queue    — unentschieden (Default; ossifikat-staging ohne Overlay-Eintrag)
  parked   — zurückgestellt, später entscheiden (nichts verloren, jederzeit zurück)
  archived — verworfen, aber NICHT gelöscht (reversibel; ersetzt das harte reject)

„Verbürgen" bleibt ossifikat.confirm() (staging=0). Diese Overlay-Datei ist reine
Laufzeit-Config (JSON, gitignored). Ein confirmtes/zurückgeholtes Tripel verliert
seinen Overlay-Eintrag → fällt zurück in die Queue-Logik.
"""
import json
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVERLAY_FILE = Path(os.environ.get(
    "VIBELIKE_RATIFY_OVERLAY", ROOT / "data" / "ratification_overlay.json"))

VALID_STATES = {"parked", "archived"}
_LOCK = threading.Lock()


def _load() -> dict:
    try:
        with open(OVERLAY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d: dict) -> None:
    OVERLAY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OVERLAY_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    tmp.replace(OVERLAY_FILE)  # atomar


def states() -> dict:
    """{triple_id(str): {'state','by','at'}} — alle Overlay-Einträge."""
    return _load()


def set_state(triple_id: int, state: str, by: str) -> None:
    if state not in VALID_STATES:
        raise ValueError(f"ungültiger state: {state}")
    with _LOCK:
        d = _load()
        d[str(triple_id)] = {"state": state, "by": by,
                             "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        _save(d)


def clear_state(triple_id: int) -> None:
    """Overlay entfernen → Tripel ist wieder in der Queue (Restore / nach Confirm)."""
    with _LOCK:
        d = _load()
        if d.pop(str(triple_id), None) is not None:
            _save(d)
