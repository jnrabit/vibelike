"""
web/terminal_ws.py — PTY-Web-Terminal hinter dem Identitäts-Gate.

WebSocket /ws/terminal: nach Token-Auth (Capability 'terminal') wird `terminal.py`
in einem Pseudo-Terminal gespawnt; ein PTY *ist* ein Terminal, also funktioniert die
input()-REPL (und später die Workflow-Genehmigungs-Prompts) nativ — ohne Umbau von
terminal.py. Stream läuft über Tailscale (Shape A).

Protokoll:
  Client → Server (Text/JSON):
    {"type":"auth","token":"<64hex>"}            (erste Nachricht, Pflicht)
    {"type":"input","data":"..."}                (Tastatureingabe)
    {"type":"resize","cols":N,"rows":M}          (Fenstergröße)
  Server → Client:
    rohe Text-Frames = PTY-Ausgabe (xterm.write)

Audit: jede abgeschickte Eingabezeile → append-only logs/web_terminal_audit.jsonl.
Isolation (non-root, Sandbox) macht die systemd-Unit (deploy/vibeweb.service).
"""
import asyncio
import fcntl
import json
import os
import pty
import signal
import struct
import sys
import termios
import time
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth import device_for_token, capabilities_for

ROOT = Path(__file__).resolve().parent.parent
AUDIT_LOG = ROOT / "logs" / "web_terminal_audit.jsonl"

router = APIRouter()


def _audit(device: str, event: str, data: str = "") -> None:
    """Append-only Audit — jeder Web-Terminal-Befehl ist nachvollziehbar."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "device": device, "event": event, "data": data,
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except OSError:
        pass


@router.websocket("/ws/terminal")
async def terminal_ws(ws: WebSocket) -> None:
    await ws.accept()

    # ── 1. Auth: erste Nachricht muss {"type":"auth","token":...} sein ──
    try:
        first = json.loads(await ws.receive_text())
    except (json.JSONDecodeError, WebSocketDisconnect, KeyError):
        await ws.close(code=4400)
        return
    token = first.get("token") if first.get("type") == "auth" else None
    device = device_for_token(token)
    if not device:
        await ws.send_text("\r\n[Auth fehlgeschlagen: ungültiges Token]\r\n")
        await ws.close(code=4401)
        return
    if "terminal" not in capabilities_for(device):
        await ws.send_text("\r\n[Verweigert: Device hat keine 'terminal'-Capability]\r\n")
        await ws.close(code=4403)
        return

    _audit(device, "session_open")

    # ── 2. terminal.py in einem PTY spawnen ──
    master_fd, slave_fd = pty.openpty()
    env = dict(os.environ)               # systemd-Unit liefert das restriktive Environment
    env["TERM"] = "xterm-256color"
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(ROOT / "terminal.py"),
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        cwd=str(ROOT), env=env, start_new_session=True,
    )
    os.close(slave_fd)

    loop = asyncio.get_running_loop()
    line_buf = ""  # für zeilenweises Audit

    # PTY-Ausgabe → WebSocket
    def _on_pty_readable() -> None:
        try:
            data = os.read(master_fd, 65536)
        except OSError:
            data = b""
        if not data:
            loop.remove_reader(master_fd)
            asyncio.create_task(ws.close())
            return
        asyncio.create_task(ws.send_text(data.decode("utf-8", "replace")))

    loop.add_reader(master_fd, _on_pty_readable)

    # ── 3. WebSocket → PTY ──
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            if mtype == "input":
                d = msg.get("data", "")
                os.write(master_fd, d.encode("utf-8"))
                # zeilenweises Audit (Enter = Befehl abgeschickt)
                line_buf += d
                while "\r" in line_buf or "\n" in line_buf:
                    sep = min((i for i in (line_buf.find("\r"), line_buf.find("\n")) if i != -1))
                    cmd, line_buf = line_buf[:sep], line_buf[sep + 1:]
                    if cmd.strip():
                        _audit(device, "input", cmd.strip())
            elif mtype == "resize":
                _set_winsize(master_fd, int(msg.get("rows", 24)), int(msg.get("cols", 80)))
    except WebSocketDisconnect:
        pass
    finally:
        loop.remove_reader(master_fd)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        _audit(device, "session_close")
