#!/usr/bin/env python3
"""
P1: Agent Backends — Cloud→Lokal-Fallback + Verfügbarkeits-Check.

Philosophie: Minimal, lokal-first. Default = qwen3:8b lokal. Cloud = optional, nie Blocker.

Wenn Claude-Guthaben leer (wie heute) → still funktionieren (lokal).
Wenn Gemini/Mistral-Keys weg → still funktionieren (Heuristik statt Inferencing).
"""

import os
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).parent


@dataclass
class BackendInfo:
    """Metadaten eines Backends."""
    name: str
    model_id: str
    can_generate: bool        # Generate Text
    can_infer_actions: bool   # Choose Actions für Agent-Loop
    available: bool           # Key + SDK present?
    reason: Optional[str] = None  # Warum nicht verfügbar?


class BackendRegistry:
    """Minimal-Registry für Coder-Backends (nicht `/collect`-Inflation)."""

    def __init__(self):
        self.backends: Dict[str, BackendInfo] = {}
        self._probe()

    def _probe(self):
        """Prüfe Verfügbarkeit aller Backends."""
        # Lokal (qwen3:8b via Ollama) — immer
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        local_ok = sock.connect_ex(("localhost", 11434)) == 0
        sock.close()
        self.backends["qwen3"] = BackendInfo(
            name="qwen3:8b (Ollama lokal)",
            model_id="qwen3:8b",
            can_generate=local_ok,
            can_infer_actions=local_ok,
            available=local_ok,
            reason=None if local_ok else "Ollama-Server nicht erreichbar"
        )

        # Claude (Anthropic API) — optional
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        try:
            import anthropic
            claude_ok = bool(api_key)
            self.backends["claude"] = BackendInfo(
                name="Claude Sonnet (Anthropic)",
                model_id="claude-sonnet-4-6",
                can_generate=claude_ok,
                can_infer_actions=claude_ok,
                available=claude_ok,
                reason=None if claude_ok else "ANTHROPIC_API_KEY nicht gesetzt"
            )
        except ImportError:
            self.backends["claude"] = BackendInfo(
                name="Claude Sonnet",
                model_id="claude-sonnet-4-6",
                can_generate=False,
                can_infer_actions=False,
                available=False,
                reason="anthropic-Paket nicht installiert"
            )

        # Gemini (Google AI) — optional
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        try:
            import google.genai
            gemini_ok = bool(gemini_key)
            self.backends["gemini"] = BackendInfo(
                name="Gemini 2.5 Flash",
                model_id="gemini-2.5-flash",
                can_generate=gemini_ok,
                can_infer_actions=gemini_ok,
                available=gemini_ok,
                reason=None if gemini_ok else "GEMINI_API_KEY nicht gesetzt"
            )
            if gemini_ok:
                self._gemini_client = google.genai.Client(api_key=gemini_key)
            else:
                self._gemini_client = None
        except ImportError:
            self.backends["gemini"] = BackendInfo(
                name="Gemini 2.5 Flash",
                model_id="gemini-2.5-flash",
                can_generate=False,
                can_infer_actions=False,
                available=False,
                reason="google-genai-Paket nicht installiert"
            )
            self._gemini_client = None

        # Mistral (Mistral API) — optional
        mistral_key = os.environ.get("MISTRAL_API_KEY", "").strip()
        try:
            import mistralai
            mistral_ok = bool(mistral_key)
            self.backends["mistral"] = BackendInfo(
                name="Mistral Large",
                model_id="mistral-large-latest",
                can_generate=mistral_ok,
                can_infer_actions=mistral_ok,
                available=mistral_ok,
                reason=None if mistral_ok else "MISTRAL_API_KEY nicht gesetzt"
            )
        except ImportError:
            self.backends["mistral"] = BackendInfo(
                name="Mistral Large",
                model_id="mistral-large-latest",
                can_generate=False,
                can_infer_actions=False,
                available=False,
                reason="mistralai-Paket nicht installiert"
            )

    def get_for_generation(self) -> BackendInfo:
        """Bestes Backend für Text-Generierung (Cloud→Lokal-Fallback)."""
        # Preferenz: Claude > Gemini > Mistral > qwen3 lokal
        for name in ["claude", "gemini", "mistral", "qwen3"]:
            if name in self.backends and self.backends[name].can_generate:
                return self.backends[name]
        # Fallback: qwen3 lokal (sollte immer da sein wenn Server läuft)
        return self.backends.get("qwen3", BackendInfo(
            name="(keine)", model_id="", can_generate=False,
            can_infer_actions=False, available=False,
            reason="Kein Backend verfügbar"
        ))

    def get_for_action_inference(self) -> BackendInfo:
        """Bestes Backend für Agent-Action-Wahl."""
        # Preferenz: Claude > qwen3 lokal (Agent braucht gute Entscheidungen)
        for name in ["claude", "qwen3"]:
            if name in self.backends and self.backends[name].can_infer_actions:
                return self.backends[name]
        # Fallback: irgendwas
        for name in ["gemini", "mistral"]:
            if name in self.backends and self.backends[name].can_infer_actions:
                return self.backends[name]
        return BackendInfo(
            name="(keine)", model_id="", can_generate=False,
            can_infer_actions=False, available=False,
            reason="Kein Backend verfügbar"
        )

    def list_all(self) -> list[BackendInfo]:
        """Alle Backends + Status."""
        return list(self.backends.values())

    def get_gemini_client(self):
        """Hole Gemini-Client wenn verfügbar."""
        return getattr(self, "_gemini_client", None)

    def generate_with_gemini(self, prompt: str, temperature: float = 0.3, max_tokens: int = 600) -> str:
        """Generiere Text via Gemini API."""
        client = self.get_gemini_client()
        if not client:
            return ""
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }
            )
            return (response.text or "").strip()
        except Exception as e:
            print(f"[WARN] Gemini generate fehlgeschlagen: {e}")
            return ""

    def status_string(self) -> str:
        """Human-readable Status aller Backends."""
        lines = ["═══ Agent Backends Status ═══\n"]
        for b in self.list_all():
            status = "✓" if b.available else "✗"
            reason = f" ({b.reason})" if b.reason else ""
            lines.append(f"  {status} {b.name:30s} {reason}")
        gen = self.get_for_generation()
        inf = self.get_for_action_inference()
        lines.append(f"\n→ Generierung: {gen.name}")
        lines.append(f"→ Action-Wahl: {inf.name}")
        return "\n".join(lines)


# ═══ Global Registry (Singleton) ═══

_registry = None

def get_registry() -> BackendRegistry:
    """Hole oder erstelle globales Backend-Registry."""
    global _registry
    if _registry is None:
        _registry = BackendRegistry()
    return _registry


# ═══ Test / Demo ═══

if __name__ == "__main__":
    registry = get_registry()
    print(registry.status_string())
