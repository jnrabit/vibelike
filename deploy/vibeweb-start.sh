#!/usr/bin/env bash
# vibeweb-start.sh — Mini-Diagnose + Start der Kommandozentrale (Dashboard + PTY-Terminal).
#
# Nutzung (selbst starten, hält Token/Key aus dem Chat-Transkript):
#   ! bash deploy/vibeweb-start.sh
#
# Stoppen:  Ctrl-C   (oder:  pkill -f 'uvicorn web.server')
#
# Env-Overrides:
#   VIBEWEB_PORT=8800           Port
#   VIBEWEB_HOST=auto           'auto' = tailnet-IP; sonst feste Adresse / 0.0.0.0
#   VIBEWEB_ENVFILE=~/.vibeweb.env   optionale chmod-600 Datei mit ANTHROPIC_API_KEY (export)
set -euo pipefail

cd "$(dirname "$0")/.."          # Projekt-Root
ROOT="$(pwd)"
PORT="${VIBEWEB_PORT:-8800}"
HOST_REQ="${VIBEWEB_HOST:-auto}"
RETR_PORT="${VIBELIKE_RETRIEVAL_PORT:-8810}"
RETR_URL="http://127.0.0.1:${RETR_PORT}"

c_ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
c_warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
c_bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }

fail=0
echo "── vibeweb Diagnose ───────────────────────────────"

# 1. Python-Env (muss wsproto haben — der 3.11-uvicorn kann kein WebSocket)
if python3 -c 'import uvicorn,wsproto,websockets' 2>/dev/null; then
  ver=$(python3 -c 'import uvicorn,wsproto; print("uvicorn",uvicorn.__version__,"wsproto",wsproto.__version__)')
  c_ok "Python $(python3 -c 'import platform;print(platform.python_version())') · $ver"
else
  c_bad "python3 fehlt uvicorn/wsproto/websockets — WebSocket-Terminal geht NICHT"; fail=1
fi

# 2. Auth-Substrat
[ -f data/chaos_tokens.db ]  && c_ok "Token-DB data/chaos_tokens.db"        || { c_bad "data/chaos_tokens.db fehlt — kein Pairing"; fail=1; }
[ -f web/capabilities.toml ] && c_ok "web/capabilities.toml"               || { c_bad "web/capabilities.toml fehlt — keine Capabilities"; fail=1; }
[ -f web/terminal_ws.py ]    && c_ok "web/terminal_ws.py (PTY-Router)"     || { c_bad "web/terminal_ws.py fehlt — kein /ws/terminal"; fail=1; }
[ -f terminal.py ]           && c_ok "terminal.py (REPL fürs PTY)"         || { c_warn "terminal.py fehlt — Terminal-Tab spawnt nichts"; }
[ -f retrieval_service.py ]  && c_ok "retrieval_service.py (Vault-Daemon)" || { c_warn "retrieval_service.py fehlt — Vaults laden pro Verbindung neu (~40s)"; }

# 3. Bind-Host (Default 0.0.0.0 → localhost UND Tailnet; Firewall gated) + Tailnet-IP für Anzeige
BIND="${VIBEWEB_HOST:-0.0.0.0}"
[ "$BIND" = "auto" ] && BIND="0.0.0.0"
TAILNET_IP=$(tailscale ip -4 2>/dev/null | head -n1)
if [ -n "$TAILNET_IP" ]; then
  c_ok "Bind $BIND · Tailnet-IP $TAILNET_IP (Firewall: tailscale0 trusted, WLAN block)"
else
  c_warn "Tailscale nicht erreichbar — Bind $BIND, Tailnet-URL unbekannt"
fi

# 4. Port frei?
if command -v ss >/dev/null && ss -ltn 2>/dev/null | grep -q ":$PORT "; then
  c_bad "Port $PORT belegt — läuft schon was? (pkill -f 'uvicorn web.server')"; fail=1
else
  c_ok "Port $PORT frei"
fi

# 5. Optionaler Secrets-EnvFile (chmod 600) — Key bleibt aus History/Transkript
ENVFILE="${VIBEWEB_ENVFILE:-$HOME/.vibeweb.env}"
if [ -f "$ENVFILE" ]; then
  perm=$(stat -c '%a' "$ENVFILE" 2>/dev/null || echo '?')
  [ "$perm" = "600" ] || c_warn "$ENVFILE hat Rechte $perm (empfohlen: chmod 600)"
  set -a; . "$ENVFILE"; set +a
  [ -n "${ANTHROPIC_API_KEY:-}" ] && c_ok "ANTHROPIC_API_KEY aus $ENVFILE geladen" || c_warn "$ENVFILE ohne ANTHROPIC_API_KEY"
else
  [ -n "${ANTHROPIC_API_KEY:-}" ] && c_warn "ANTHROPIC_API_KEY aus Shell-Env (besser: $ENVFILE chmod 600)" \
                                  || c_warn "kein ANTHROPIC_API_KEY — query/REPL ok, Codegen-Workflows nicht"
fi

echo "───────────────────────────────────────────────────"
if [ "$fail" = 1 ]; then
  c_bad "Diagnose fehlgeschlagen — Start abgebrochen."; exit 1
fi

# ── Retrieval-Daemon: 188k-Wissens-Vault EINMAL warm halten. Sonst zahlt jede pro
#    PTY-Verbindung frisch gespawnte terminal.py die ~40s Ladezeit erneut. ──
if [ -f retrieval_service.py ] && command -v curl >/dev/null; then
  if curl -fsS "$RETR_URL/health" 2>/dev/null | grep -q '"ready": *true'; then
    c_ok "Retrieval-Daemon läuft bereits ($RETR_URL)"
  else
    echo "  … starte Retrieval-Daemon (lädt beide Vaults einmalig, ~40s)…"
    nohup python3 retrieval_service.py > /tmp/hotr_retrieval.log 2>&1 &
    disown 2>/dev/null || true
    ready=0
    for _ in $(seq 1 90); do
      if curl -fsS "$RETR_URL/health" 2>/dev/null | grep -q '"ready": *true'; then ready=1; break; fi
      sleep 1
    done
    [ "$ready" = 1 ] && c_ok "Retrieval-Daemon READY ($RETR_URL)" \
                     || c_warn "Daemon nicht ready (siehe /tmp/hotr_retrieval.log) — Terminal lädt Vaults lokal (~40s/Verbindung)"
  fi
  export VIBELIKE_RETRIEVAL_URL="$RETR_URL"   # vererbt sich an die per PTY gespawnte terminal.py
else
  c_warn "Retrieval-Daemon übersprungen (retrieval_service.py oder curl fehlt) — Vaults laden pro Verbindung"
fi

echo "───────────────────────────────────────────────────"
echo "  hótr̥ lokal (PC) :  http://localhost:$PORT/"
[ -n "$TAILNET_IP" ] && echo "  hótr̥ Tailnet    :  http://$TAILNET_IP:$PORT/  (Handy)"
echo "  Stop            :  Ctrl-C (Server) · Daemon bleibt warm: pkill -f retrieval_service.py"
echo "───────────────────────────────────────────────────"

exec python3 -m uvicorn web.server:app --host "$BIND" --port "$PORT" --ws wsproto
