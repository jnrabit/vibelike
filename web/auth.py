"""
web/auth.py — Identitäts-Gate: chaos-garten Bearer-Token + Capability-Tiers.

Single Source of Truth = chaos-gartens `auth_tokens`-SQLite (eine Pairing-/Revoke-
Autorität für Chat UND Terminal). Wir lesen sie **read-only**:
`SELECT device_id FROM auth_tokens WHERE token=?`. Token entsteht nur nach
erfolgreichem signiertem X25519-Handshake. Revoke = Zeile/Device dort löschen →
Chat und Terminal sofort tot.

Capability-Tiers in web/capabilities.toml (device_id -> [dashboard, terminal, …]).
Frisch pro Request gelesen → Edits/Revoke wirken sofort. Fail-closed: unbekanntes
Token oder fehlende DB ⇒ keine Berechtigung.
"""
import os
import sqlite3
import tomllib
from pathlib import Path

from fastapi import Header, HTTPException, WebSocket, status

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent

# In Produktion auf die chaos-garten-Server-DB zeigen lassen. Interim/Test: lokal.
TOKEN_DB = Path(os.environ.get("VIBELIKE_TOKEN_DB", ROOT / "data" / "chaos_tokens.db"))
CAP_FILE = Path(os.environ.get("VIBELIKE_CAPABILITIES", HERE / "capabilities.toml"))

TOKEN_LEN = 64  # 32 Byte hex, wie chaos-garten (crypto/rand)


def device_for_token(token: str | None) -> str | None:
    """device_id zu einem gültigen Token, sonst None. Liest die DB read-only."""
    if not token or len(token) != TOKEN_LEN:
        return None
    try:
        con = sqlite3.connect(f"file:{TOKEN_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return None  # DB fehlt ⇒ fail-closed
    try:
        row = con.execute(
            "SELECT device_id FROM auth_tokens WHERE token=?", (token,)
        ).fetchone()
        # device_id defensiv strippen: beim Pairen vom Handy (Termux/Paste) rutscht
        # gern ein \r/\n ins Geräte-Arg und bricht sonst den capabilities.toml-Lookup.
        return row[0].strip() if row and row[0] else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def capabilities_for(device_id: str) -> set[str]:
    """Erlaubte Capabilities eines Device — frisch aus capabilities.toml."""
    if not device_id or not CAP_FILE.exists():
        return set()
    try:
        with open(CAP_FILE, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    return set(data.get("devices", {}).get(device_id, []))


def _extract_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer "):].strip()


def require_capability(cap: str):
    """FastAPI-Dependency (HTTP): verlangt gültiges Token MIT Capability `cap`.
    Gibt die verifizierte device_id zurück."""
    def _dep(authorization: str | None = Header(default=None)) -> str:
        device = device_for_token(_extract_token(authorization))
        if not device:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ungültiges oder fehlendes Token")
        if cap not in capabilities_for(device):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Device hat keine '{cap}'-Capability")
        return device
    return _dep


async def authorize_ws(websocket: WebSocket, cap: str, token: str | None) -> str | None:
    """WebSocket-Auth: device_id bei Erfolg, sonst Verbindung schließen + None.
    Schließcodes: 4401 = unauthorized, 4403 = forbidden."""
    device = device_for_token(token)
    if not device:
        await websocket.close(code=4401)
        return None
    if cap not in capabilities_for(device):
        await websocket.close(code=4403)
        return None
    return device
