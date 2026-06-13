#!/usr/bin/env python3
"""
P3.2: Privacy Router — deterministic query classification + model filtering.

Architektur:
- PrivacyClassifier: regex-basierte Klassifikation (PUBLIC → INTERNAL → SECRET → SUBSTRAT)
- ModelRouter: filtert verfügbare Modelle nach Privacy-Level
- TierMap: Metadaten über jeden Backend (zero_retention, free, throwaway)
"""

import re
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional


class PrivacyLevel(Enum):
    """4 Privacy-Level mit unterschiedlichen Model-Bedingungen."""
    PUBLIC = "public"       # alle Modelle ok
    INTERNAL = "internal"   # lokal + zero-retention; kein free-cloud
    SECRET = "secret"       # nur lokal (qwen3)
    SUBSTRAT = "substrat"   # nur lokal + Claude:zero-retention (harte Pässe)


@dataclass
class TierInfo:
    """Metadaten eines Backends / einer Tier."""
    label: str              # z.B. "lokal", "paid+zero-ret"
    zero_retention: bool    # Explizite Zero-Retention-Guarantee?
    free: bool              # Kostenlos?
    throwaway: bool         # Free-Cloud-Tier (Daten können gesammelt werden)?


# Metadaten aller Backend-Tiers (nur qwen + claude für P3 MVP)
TIER_MAP = {
    "qwen3": TierInfo(
        label="qwen2.5-coder:1.5b (lokal, GPU)",
        zero_retention=True,
        free=True,
        throwaway=False
    ),
    "qwen": TierInfo(
        label="qwen2.5-coder:1.5b (lokal, GPU)",
        zero_retention=True,
        free=True,
        throwaway=False
    ),
    "claude": TierInfo(
        label="claude-haiko (API, zero-ret)",
        zero_retention=True,
        free=False,
        throwaway=False
    ),
    "haiko": TierInfo(
        label="claude-haiko (API, zero-ret)",
        zero_retention=True,
        free=False,
        throwaway=False
    ),
}


class PrivacyClassifier:
    """Klassifiziere Query-Text regelbasiert → PrivacyLevel."""

    # Muster für SUBSTRAT: Harte Pässe (niemand liest Substrat-Daten)
    SUBSTRAT_PATTERNS = [
        r"substrat\s*pass",
        r"zero\s*retention",
        r"niemand\s*liest",
        r"kritisch.*daten",
        r"geheim.*pass",
    ]

    # Muster für SECRET: Passwörter, Keys, Credentials
    SECRET_PATTERNS = [
        r"passwort",
        r"password",
        r"api\s*key",
        r"token",
        r"credential",
        r"ssh",
        r"private\s*key",
        r"secret",
        r"credentials",
        r"geheim",
        r"authentifizier",
    ]

    # Muster für INTERNAL: Projektinterner Code, Filedaten
    INTERNAL_PATTERNS = [
        r"mein[a-z]*\s+(code|projekt|datei|workflow)",
        r"vibelike",
        r"terminal\.py",
        r"agent_loop",
        r"my\s+(code|file|project)",
        r"hier\s+(im\s+)?projekt",
        r"intern",
    ]

    def classify(self, query: str) -> PrivacyLevel:
        """
        Klassifiziere Query nach Privacy-Level.
        Rückgabe: PrivacyLevel (lowest to highest restriction)
        """
        query_lower = query.lower()

        # Hierarchie: SUBSTRAT > SECRET > INTERNAL > PUBLIC
        if self._matches_any(query_lower, self.SUBSTRAT_PATTERNS):
            return PrivacyLevel.SUBSTRAT

        if self._matches_any(query_lower, self.SECRET_PATTERNS):
            return PrivacyLevel.SECRET

        if self._matches_any(query_lower, self.INTERNAL_PATTERNS):
            return PrivacyLevel.INTERNAL

        # Default: PUBLIC
        return PrivacyLevel.PUBLIC

    @staticmethod
    def _matches_any(text: str, patterns: List[str]) -> bool:
        """Prüfe ob Text irgendein Pattern matched."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False


class ModelRouter:
    """Filtere verfügbare Modelle nach Privacy-Level."""

    def __init__(self, tier_map: dict = TIER_MAP):
        self.tier_map = tier_map

    def allowed_models(
        self,
        level: PrivacyLevel,
        selected_models: List[str]
    ) -> List[str]:
        """
        Filtere selected_models nach Privacy-Level-Regeln.
        """
        if not selected_models:
            # Default fallback: qwen3 (lokal)
            return ["qwen3"]

        filtered = []

        if level == PrivacyLevel.SUBSTRAT:
            # Nur: lokal + zero-retention Claude
            # (harte Pässe, niemand liest die Substrat-Daten)
            for model in selected_models:
                info = self.tier_map.get(model)
                if info and info.zero_retention and not info.free:
                    # Claude nur
                    if model == "claude":
                        filtered.append(model)
            # Fallback zu qwen3 wenn nichts passt
            if not filtered and "qwen3" in selected_models:
                filtered.append("qwen3")

        elif level == PrivacyLevel.SECRET:
            # Nur lokal (qwen3)
            for model in selected_models:
                if model == "qwen3":
                    filtered.append(model)
            # Fallback falls qwen3 nicht ausgewählt
            if not filtered:
                filtered.append("qwen3")

        elif level == PrivacyLevel.INTERNAL:
            # Lokal + zero-retention (Claude), kein free-cloud throwaway
            for model in selected_models:
                info = self.tier_map.get(model)
                if info and not info.throwaway:
                    filtered.append(model)
            # Fallback zu qwen3 wenn nichts
            if not filtered:
                filtered.append("qwen3")

        else:  # PrivacyLevel.PUBLIC
            # Alle erlaubten Modelle
            filtered = selected_models

        return filtered or ["qwen3"]  # Absoluter Fallback


# ═══ Test / Demo ═══

def main():
    """Test PrivacyClassifier und ModelRouter."""
    print("═══ P3.2: Privacy Router — Classification & Filtering ═══\n")

    classifier = PrivacyClassifier()
    router = ModelRouter()

    test_cases = [
        ("Was ist Quantenverschränkung?", PrivacyLevel.PUBLIC),
        ("Mein Passwort ist 12345", PrivacyLevel.SECRET),
        ("Lies meinen Code aus terminal.py", PrivacyLevel.INTERNAL),
        ("Substrat-Pass: niemand liest das", PrivacyLevel.SUBSTRAT),
        ("Wie funktioniert Zero-Retention?", PrivacyLevel.PUBLIC),
    ]

    available = ["qwen3", "claude", "gemini", "openrouter"]

    print("[TEST] PrivacyClassifier\n")
    for query, expected in test_cases:
        classified = classifier.classify(query)
        match = "✓" if classified == expected else "✗"
        print(f"{match} '{query[:40]}...'")
        print(f"   → {classified.value} (expected: {expected.value})\n")

    print("\n[TEST] ModelRouter\n")
    test_routing = [
        (PrivacyLevel.PUBLIC, ["qwen3", "claude", "gemini", "openrouter"]),
        (PrivacyLevel.INTERNAL, ["qwen3", "claude", "gemini", "openrouter"]),
        (PrivacyLevel.SECRET, ["qwen3", "claude", "gemini", "openrouter"]),
        (PrivacyLevel.SUBSTRAT, ["qwen3", "claude", "gemini", "openrouter"]),
    ]

    for level, selected in test_routing:
        allowed = router.allowed_models(level, selected)
        print(f"{level.value:12s}: {selected} → {allowed}")

    print("\n[OK] Tests abgeschlossen")


if __name__ == "__main__":
    main()
