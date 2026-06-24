#!/bin/bash

# Vibelike Web Server: Stop + Restart mit WS-Protokoll
# Usage: ./scripts/server-restart.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "[*] Stopping old server processes..."
pkill -f "uvicorn web.server:app" 2>/dev/null && echo "[✓] Old server stopped" || echo "[✓] No old processes found"

# Brief wait für Port-Freigabe
sleep 1

echo "[*] Starting vibelike server on port 8800..."
cd "$PROJECT_ROOT"
python3 -m uvicorn web.server:app --host 0.0.0.0 --port 8800 --ws wsproto
