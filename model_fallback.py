#!/usr/bin/env python3
"""
Local-First Fallback-Kette: Cloud-Backend probieren → bei Quota/Overload auf
lokales Ollama abfallen.

Hintergrund (Nordstern lokal-first): Cloud war eine Krücke; das Guthaben-Aus bewies
die Fragilität. Mitten in einer Session kann ein Cloud-Modell (Claude/Gemini/Mistral)
sein Kontingent erschöpfen — bisher verschluckte ClaudeCoder.generate() das in einen
"[ERR] ..."-String, der als "generierter Code/Analyse" weiterfloss. Diese Schicht macht
den Quota-Fall LAUT (typisierter ModelQuotaExceededError) und fängt ihn auf: das lokale
Modell übernimmt, statt den Workflow mit Müll zu füttern.

Das ist die EINE Abstraktion, die sich rechtfertigt — sie löst ein reales Problem und
verdrahtet zugleich errors.py an einer echten Stelle.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from errors import (
    ModelError,
    ModelNotAvailableError,
    ModelQuotaExceededError,
    ModelTimeoutError,
)

logger = logging.getLogger(__name__)


class Coder(Protocol):
    """Minimales Coder-Interface (QwenCoder/ClaudeCoder erfüllen es duck-typed)."""

    def generate(self, prompt: str, **kwargs) -> str: ...


# Signaturen für Exception-Klassifikation (provider-agnostisch, per Substring).
# Quota/Overload/Rate-Limit → fallback-würdig (lokal kann übernehmen).
_QUOTA_SIGNATURES = (
    "rate limit", "ratelimit", "rate_limit",
    "quota", "credit balance", "insufficient_quota", "insufficient credit",
    "overloaded", "overload",
    "resource_exhausted", "resource exhausted",
    "429", "529",
    "too many requests",
)
_TIMEOUT_SIGNATURES = ("timeout", "timed out", "deadline exceeded")
_UNAVAILABLE_SIGNATURES = (
    "service unavailable", "503", "connection", "could not connect",
    "name or service not known", "max retries",
)


def classify_model_exception(exc: BaseException) -> Optional[ModelError]:
    """Mappt eine Provider-Exception auf einen typisierten ModelError.

    Provider-agnostisch über Exception-Klassennamen + Message-Substrings
    (anthropic.RateLimitError, google ResourceExhausted, requests-Timeouts …),
    damit kein hartes SDK-Import nötig ist.

    Returns:
        ModelError-Subinstanz (noch nicht geraist) oder None wenn unklassifiziert.
    """
    name = type(exc).__name__.lower()
    msg = str(exc)
    low = msg.lower()

    def _hit(sigs) -> bool:
        return any(s in low for s in sigs)

    # 1. Klassennamen-Heuristik (zuverlässiger als Message)
    if "ratelimit" in name or "quota" in name or "resourceexhausted" in name or "overloaded" in name:
        return ModelQuotaExceededError(msg, context={"exc_type": type(exc).__name__})
    if "timeout" in name or "deadline" in name:
        return ModelTimeoutError(msg, context={"exc_type": type(exc).__name__})

    # 2. Message-Substring-Heuristik
    if _hit(_QUOTA_SIGNATURES):
        return ModelQuotaExceededError(msg, context={"exc_type": type(exc).__name__})
    if _hit(_TIMEOUT_SIGNATURES):
        return ModelTimeoutError(msg, context={"exc_type": type(exc).__name__})
    if _hit(_UNAVAILABLE_SIGNATURES):
        return ModelNotAvailableError(msg, context={"exc_type": type(exc).__name__})

    return None


class FallbackCoder:
    """Wrappt (primary=Cloud, fallback=lokal) mit QwenCoder-kompatiblem generate().

    generate() probiert primary; bei ModelError (Quota/Timeout/Unavailable) ODER einem
    "[ERR] …"-Rückgabestring mit Quota-Signatur → lokales Fallback. Andere Fehler werden
    durchgereicht (kein blindes Verschlucken).

    Drop-in: gleiche generate()-Signatur wie QwenCoder/ClaudeCoder. Der Workflow merkt
    nichts außer einer Log-Zeile beim Umschalten.
    """

    def __init__(self, primary: Coder, fallback: Coder, *, name: str = "codegen"):
        self.primary = primary
        self.fallback = fallback
        self.name = name
        # Sticky: nach dem ersten Quota-Hit für den Rest der Session lokal bleiben
        # (Cloud-Kontingent kommt nicht in Sekunden zurück → spart vergebliche Calls).
        self._cloud_exhausted = False

    @property
    def usable(self) -> bool:
        # Nutzbar solange wenigstens das Fallback nutzbar ist.
        return getattr(self.fallback, "usable", True) or getattr(self.primary, "usable", True)

    def generate(self, prompt: str, **kwargs) -> str:
        # Bereits erschöpft → direkt lokal, kein vergeblicher Cloud-Call.
        if self._cloud_exhausted:
            return self.fallback.generate(prompt, **kwargs)

        try:
            # raise_on_quota signalisiert dem Cloud-Coder: Quota NICHT in [ERR]
            # verschlucken, sondern werfen. Unbekannte Coder ignorieren das kwarg
            # nicht zwingend → defensiv per try.
            try:
                result = self.primary.generate(prompt, raise_on_quota=True, **kwargs)
            except TypeError:
                # primary kennt raise_on_quota nicht → ohne aufrufen, dann String prüfen
                result = self.primary.generate(prompt, **kwargs)

            # String-basierter Fallback-Trigger (für Coder die noch [ERR] zurückgeben)
            if isinstance(result, str) and result.startswith("[ERR]"):
                err = classify_model_exception(Exception(result))
                if isinstance(err, ModelError):
                    return self._do_fallback(prompt, err, kwargs)
            return result

        except ModelQuotaExceededError as e:
            self._cloud_exhausted = True
            return self._do_fallback(prompt, e, kwargs)
        except (ModelTimeoutError, ModelNotAvailableError) as e:
            # Transient: einmal lokal versuchen, aber Cloud nicht als erschöpft markieren.
            return self._do_fallback(prompt, e, kwargs)

    def _do_fallback(self, prompt: str, err: ModelError, kwargs: dict) -> str:
        sticky = " (Cloud für Session deaktiviert)" if self._cloud_exhausted else ""
        logger.warning(
            "[FALLBACK:%s] Cloud-Backend %s → lokal. Grund: %s%s",
            self.name, type(err).__name__, err.message[:120], sticky,
        )
        print(f"[⤵️  FALLBACK:{self.name}] Cloud erschöpft ({type(err).__name__}) "
              f"→ lokales Modell übernimmt{sticky}")
        # raise_on_quota nicht ans lokale Modell weiterreichen.
        kwargs.pop("raise_on_quota", None)
        return self.fallback.generate(prompt, **kwargs)
