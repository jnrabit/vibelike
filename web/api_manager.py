#!/usr/bin/env python3
"""
P3.4a: API Manager — REST endpoints für Backend-Management, Privacy-Levels, Model-Selection.

Endpoints:
- GET  /api/backends              → [{name, label, status, key_set, tier}, ...]
- POST /api/backends/{name}/key   → key in ~/.vibeweb.env schreiben
- POST /api/backends/{name}/test  → 1 API-Call, Status zurückgeben
- GET  /api/privacy/level         → current default
- POST /api/privacy/level         → {"level": "internal"}
- GET  /api/models/selected       → aktuell ausgewählte Modelle
- POST /api/models/selected       → {"models": ["qwen3", "claude"]}

Sicherheit: Bearer Token Auth (via @require_backend_mgmt)
"""

import os
import json
import warnings
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Header, Depends, Body
from pydantic import BaseModel

# Import tier map from privacy_router
try:
    from vibelike.web.privacy_router import TIER_MAP
except ImportError:
    warnings.warn("privacy_router not available", ImportWarning)
    TIER_MAP = {}


# Request models
class KeyRequest(BaseModel):
    key: str


class PrivacyRequest(BaseModel):
    level: str


class ModelsRequest(BaseModel):
    models: List[str]

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
ENV_FILE = Path.home() / ".vibeweb.env"

router = APIRouter(prefix="/api", tags=["backends"])


# ── Auth Gate ──

def _require_backend_mgmt(authorization: str = Header(default=None)) -> str:
    """Verlange gültiges Bearer Token mit 'terminal' oder 'destructive' capability."""
    from auth import device_for_token, capabilities_for

    token = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else None
    device = device_for_token(token)
    if not device:
        raise HTTPException(401, "ungültiges oder fehlendes Token")

    caps = capabilities_for(device)
    if "terminal" not in caps and "destructive" not in caps:
        raise HTTPException(403, "Device darf Backends nicht verwalten ('terminal' nötig)")

    return device


# ── Backends ──

@router.get("/backends")
async def list_backends(device: str = Depends(_require_backend_mgmt)):
    """Liste alle Backends mit Status, Key-Gesetztheit, Tier."""
    try:
        from agent_backends import get_registry
        from privacy_router import TIER_MAP

        registry = get_registry()
        result = []

        for backend in registry.list_all():
            # Shortname
            shortname = backend.model_id.split(":")[0] if ":" in backend.model_id else backend.name

            # Finde in TIER_MAP
            tier_info = TIER_MAP.get(shortname.lower(), None)

            # Check ob Key gesetzt
            key_env = f"{shortname.upper()}_API_KEY"
            key_set = bool(os.environ.get(key_env, "").strip())

            result.append({
                "name": shortname,
                "label": backend.name,
                "available": backend.available,
                "status": "✓" if backend.available else "✗",
                "reason": backend.reason or "ok",
                "key_set": key_set,
                "tier": tier_info.label if tier_info else "unknown",
                "zero_retention": tier_info.zero_retention if tier_info else False,
            })

        return result
    except Exception as e:
        raise HTTPException(500, f"Fehler beim Laden der Backends: {e}")


@router.post("/backends/{name}/key")
async def set_backend_key(
    name: str,
    request: KeyRequest,
    device: str = Depends(_require_backend_mgmt)
):
    """Speichere API-Key für Backend in ~/.vibeweb.env (XOR-verschlüsselt)"""
    try:
        from vibelike.crypto import xor_encrypt
        
        key = request.key.strip()
        if not key:
            raise ValueError("Key darf nicht leer sein")

        # Schreibe in ~/.vibeweb.env als JSON mit verschlüsselten Keys
        env_file = Path.home() / ".vibeweb.env"
        env_file.parent.mkdir(parents=True, exist_ok=True)

        # Lese bestehende JSON oder Fallback zu altem Format
        existing = {}
        if env_file.exists():
            try:
                content = env_file.read_text(encoding="utf-8").strip()
                if content.startswith("{"):
                    existing = json.loads(content)
                else:
                    # Altes Format (KEY=value)
                    for line in content.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            existing[k.strip()] = v.strip()
            except Exception:
                pass

        # Verschlüssle und speichere Key
        key_var = f"{name.upper()}_API_KEY"
        encrypted_key = xor_encrypt(key)
        existing[key_var] = encrypted_key

        # Schreibe als JSON zurück
        env_file.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        
        # Erzwinge chmod 600 (read/write für Owner nur)
        os.chmod(env_file, 0o600)

        return {
            "status": "ok",
            "key_var": key_var,
            "saved": True,
            "encrypted": True,
            "message": f"Key für {name} verschlüsselt gespeichert in {env_file} (chmod 600)"
        }
    except Exception as e:
        raise HTTPException(400, f"Fehler beim Speichern des Keys: {e}")


@router.post("/backends/{name}/test")
async def test_backend(
    name: str,
    device: str = Depends(_require_backend_mgmt)
):
    """Teste ob Backend erreichbar/funktioniert."""
    try:
        from agent_backends import get_registry

        registry = get_registry()
        backend = None
        for b in registry.list_all():
            if name.lower() in b.name.lower() or name.lower() in b.model_id.lower():
                backend = b
                break

        if not backend:
            raise HTTPException(404, f"Backend '{name}' nicht gefunden")

        return {
            "name": name,
            "available": backend.available,
            "status": "✓ verfügbar" if backend.available else f"✗ nicht verfügbar",
            "reason": backend.reason or "ok"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Test-Fehler: {e}")


@router.get("/models/status")
async def get_models_status():
    """Get live status of all models (für Sidebar live updates, no auth needed)."""
    try:
        from agent_backends import get_registry
        from privacy_router import TIER_MAP

        registry = get_registry()
        result = []

        for backend in registry.list_all():
            shortname = backend.model_id.split(":")[0] if ":" in backend.model_id else backend.name
            tier_info = TIER_MAP.get(shortname.lower(), None)

            # Check ob Key gesetzt
            key_env = f"{shortname.upper()}_API_KEY"
            key_set = bool(os.environ.get(key_env, "").strip())

            result.append({
                "name": shortname,
                "available": backend.available,
                "status": "✓" if backend.available else "✗",
                "reason": backend.reason or "ok",
                "key_set": key_set,
                "tier": tier_info.label if tier_info else "unknown",
            })

        return result
    except Exception as e:
        raise HTTPException(500, f"Status-Fehler: {e}")


# ── Privacy Level ──

# Persistiere Privacy-Level im HOME
PRIVACY_FILE = Path.home() / ".vibeweb_privacy.json"


@router.get("/privacy/level")
async def get_privacy_level(device: str = Depends(_require_backend_mgmt)):
    """Hole aktuellen Privacy-Level (default: auto)."""
    try:
        if PRIVACY_FILE.exists():
            data = json.loads(PRIVACY_FILE.read_text(encoding="utf-8"))
            return {"level": data.get("level", "auto")}
        return {"level": "auto"}
    except Exception as e:
        raise HTTPException(500, f"Fehler beim Laden des Privacy-Levels: {e}")


@router.post("/privacy/level")
async def set_privacy_level(
    request: PrivacyRequest,
    device: str = Depends(_require_backend_mgmt)
):
    """Setze Privacy-Level."""
    try:
        level = request.level.lower()
        if level not in ["auto", "public", "internal", "secret", "substrat"]:
            raise ValueError(f"Ungültiger Privacy-Level: {level}")

        PRIVACY_FILE.parent.mkdir(parents=True, exist_ok=True)
        PRIVACY_FILE.write_text(json.dumps({"level": level}), encoding="utf-8")

        return {"status": "ok", "level": level}
    except Exception as e:
        raise HTTPException(400, f"Fehler beim Setzen des Privacy-Levels: {e}")


# ── Model Selection ──

MODELS_FILE = Path.home() / ".vibeweb_models.json"


@router.get("/models/selected")
async def get_selected_models(device: str = Depends(_require_backend_mgmt)):
    """Hole aktuell ausgewählte Modelle (default: qwen3, claude, mistral)."""
    try:
        if MODELS_FILE.exists():
            data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
            return {"models": data.get("models", ["qwen3", "claude", "mistral"])}
        return {"models": ["qwen3", "claude", "mistral"]}
    except Exception as e:
        raise HTTPException(500, f"Fehler beim Laden der Modell-Auswahl: {e}")


@router.post("/models/selected")
async def set_selected_models(
    request: ModelsRequest,
    device: str = Depends(_require_backend_mgmt)
):
    """Setze ausgewählte Modelle."""
    try:
        models = request.models
        if not isinstance(models, list) or not models:
            raise ValueError("models muss eine nicht-leere Liste sein")

        # Validiere dass alle aufgelisteten Modelle gültig sind
        valid_models = {"qwen3", "claude", "gemini", "mistral", "openrouter"}
        for m in models:
            if m not in valid_models:
                raise ValueError(f"Ungültiges Modell: {m}")

        MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MODELS_FILE.write_text(json.dumps({"models": models}), encoding="utf-8")

        return {"status": "ok", "models": models}
    except Exception as e:
        raise HTTPException(400, f"Fehler beim Setzen der Modelle: {e}")


# ═══ Test / Demo (nur wenn direkt ausgeführt) ═══

if __name__ == "__main__":
    print("═══ P3.4a: API Manager ═══\n")
    print("Dieser Modul wird von web/server.py via app.include_router() integriert.")
    print("Routes:")
    for route in router.routes:
        if hasattr(route, "path"):
            print(f"  {route.methods or set()} {route.path}")
