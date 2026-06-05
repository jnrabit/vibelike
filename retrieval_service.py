#!/usr/bin/env python3
"""
retrieval_service.py — warmer Retrieval-Daemon.

Lädt beide Vaults (Code + großer 188k-Wissens-Vault) EINMAL und beantwortet
Suchanfragen über HTTP auf 127.0.0.1. So zahlt nicht jede frisch gespawnte
terminal.py (das Web-PTY spawnt sie pro Verbindung neu) die ~40s Vault-Ladezeit
— der Daemon hält sie warm, Antworten kommen in Millisekunden.

Start:
    python3 retrieval_service.py            # bindet 127.0.0.1:8810
Nutzung (terminal.py als dünner Client):
    VIBELIKE_RETRIEVAL_URL=http://127.0.0.1:8810 python3 terminal.py

Endpunkte:
    GET  /health            -> {"ready":true,"engines":[...],"docs":N}
    POST /search {query,k}  -> {"docs":[...]}

Nur localhost — kein Auth nötig, da nicht exponiert (Web-Server + terminal.py
laufen auf demselben Host). Single-Source = dieselbe CodeRetriever-Logik wie lokal.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

HOST = os.environ.get("VIBELIKE_RETRIEVAL_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIBELIKE_RETRIEVAL_PORT", "8810"))

_retriever = None
_lock = threading.Lock()  # CodeRetriever.search ist nicht thread-safe (Chaos-Warp-State)


def _load():
    global _retriever
    from terminal import CodeRetriever
    print("[daemon] Lade Vaults (einmalig, ~40s)…", flush=True)
    # remote_url=None erzwingt LOKALES Laden — sonst würde der Daemon sich selbst proxien.
    _retriever = CodeRetriever(remote_url=None)
    labels = [e["label"] for e in _retriever._engines]
    print(f"[daemon] READY · engines={labels}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # HTTP-Zugriffe still halten
        pass

    def do_GET(self):
        if self.path.startswith("/health"):
            ready = _retriever is not None
            engines = [e["label"] for e in _retriever._engines] if ready else []
            docs = len(_retriever.protocol.archive) if ready else 0
            self._send(200 if ready else 503, {"ready": ready, "engines": engines, "docs": docs})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/search"):
            self._send(404, {"error": "not found"})
            return
        if _retriever is None:
            self._send(503, {"error": "not ready"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            self._send(400, {"error": f"bad json: {e}"})
            return
        query = (req.get("query") or "").strip()
        if not query:
            self._send(400, {"error": "empty query"})
            return
        k = int(req.get("k", 10))
        boost = req.get("source_boost")
        with _lock:
            try:
                docs, _, _ = _retriever.search(query, k=k, source_boost=boost)
            except Exception as e:
                self._send(500, {"error": str(e)})
                return
        self._send(200, {"docs": docs})


def main():
    _load()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[daemon] http://{HOST}:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[daemon] stop", flush=True)
        srv.shutdown()
        try:
            _retriever.protocol.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
