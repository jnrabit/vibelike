"""
web/pair_admin.py — Operator-Tool: Geräte-Tokens minten / widerrufen / listen.

Echtes Pairing läuft über chaos-gartens QR-Handshake (signiertes X25519). Dies ist
der Interim-/Operator-Pfad (Phase 1 auf monolith): schreibt einen Token direkt in
DIESELBE auth_tokens-DB (die einzige Autorität) und pflegt die Capability-Tiers in
capabilities.toml. Du kopierst den Token aufs Gerät (Bearer beim Terminal-Connect).

  python3 web/pair_admin.py mint   --device handy --caps dashboard,terminal
  python3 web/pair_admin.py revoke --device handy
  python3 web/pair_admin.py list

Revoke löscht Token (DB) UND Capabilities (toml) → Chat- und Terminal-Zugang weg.
"""
import argparse
import os
import secrets
import sqlite3
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
TOKEN_DB = Path(os.environ.get("VIBELIKE_TOKEN_DB", ROOT / "data" / "chaos_tokens.db"))
CAP_FILE = Path(os.environ.get("VIBELIKE_CAPABILITIES", HERE / "capabilities.toml"))

# auth_tokens-Schema exakt wie chaos-garten internal/db/db.go (UnixMilli-Timestamps).
SCHEMA = """CREATE TABLE IF NOT EXISTS auth_tokens (
  token TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  created_at INTEGER,
  last_used INTEGER
);"""

CAP_HEADER = """# Capability-Tiers — device_id -> erlaubte Fähigkeiten.
#
# Tiers:
#   "dashboard"   — read-only Ansicht (Workflows, Wissens-Substrat)
#   "terminal"    — PTY/REPL-Zugriff (faktisch Remote-Shell auf terminal.py)
#   "destructive" — Workflow-Writes/Commits ohne Extra-Confirm (bewusst SPARSAM)
#
# Wearable/unterwegs ⇒ nur ["dashboard"] oder ["dashboard","terminal"] ohne destructive.
# Revoke: Zeile hier entfernen ODER Token in der chaos-garten-DB löschen.
# Verwaltung bequem via:  python3 web/pair_admin.py mint|revoke|list
"""


def _db() -> sqlite3.Connection:
    TOKEN_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(TOKEN_DB))
    con.execute(SCHEMA)
    return con


def _load_caps() -> dict:
    if not CAP_FILE.exists():
        return {}
    with open(CAP_FILE, "rb") as f:
        return dict(tomllib.load(f).get("devices", {}))


def _save_caps(devices: dict) -> None:
    lines = [CAP_HEADER, "[devices]"]
    for dev, caps in sorted(devices.items()):
        arr = ", ".join(f'"{c}"' for c in caps)
        lines.append(f'"{dev}" = [{arr}]')
    CAP_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_mint(args) -> None:
    device = args.device.strip()  # \r/\n vom Handy-Paste raus → toml-Key == DB-device_id
    caps = [c.strip() for c in args.caps.split(",") if c.strip()]
    token = secrets.token_hex(32)  # 64 hex chars, wie chaos-garten
    now = int(time.time() * 1000)
    con = _db()
    try:
        con.execute(
            "INSERT INTO auth_tokens (token, device_id, created_at, last_used) VALUES (?,?,?,?)",
            (token, device, now, now),
        )
        con.commit()
    finally:
        con.close()
    devices = _load_caps()
    devices[device] = caps
    _save_caps(devices)
    print(f"✅ Device '{device}' gepairt | Capabilities: {caps}")
    print(f"   TOKEN (auf das Gerät übertragen, Bearer):\n   {token}")


def cmd_revoke(args) -> None:
    device = args.device.strip()
    con = _db()
    try:
        n = con.execute("DELETE FROM auth_tokens WHERE device_id=?", (device,)).rowcount
        con.commit()
    finally:
        con.close()
    devices = _load_caps()
    had = devices.pop(device, None)
    _save_caps(devices)
    print(f"🚫 Device '{device}' widerrufen | {n} Token gelöscht | caps entfernt: {had is not None}")


def cmd_list(args) -> None:
    devices = _load_caps()
    con = _db()
    try:
        counts = dict(con.execute(
            "SELECT device_id, COUNT(*) FROM auth_tokens GROUP BY device_id"
        ).fetchall())
    finally:
        con.close()
    if not devices and not counts:
        print("(keine Geräte)")
        return
    for dev in sorted(set(devices) | set(counts)):
        print(f"  {dev:20s} caps={devices.get(dev, [])}  tokens={counts.get(dev, 0)}")


def main() -> None:
    p = argparse.ArgumentParser(description="chaos-garten Token-/Capability-Verwaltung")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mint", help="Token + Capabilities für ein Gerät anlegen")
    m.add_argument("--device", required=True)
    m.add_argument("--caps", default="dashboard")
    m.set_defaults(func=cmd_mint)
    r = sub.add_parser("revoke", help="Gerät widerrufen (Token + caps löschen)")
    r.add_argument("--device", required=True)
    r.set_defaults(func=cmd_revoke)
    l = sub.add_parser("list", help="Geräte + caps + Token-Anzahl")
    l.set_defaults(func=cmd_list)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
