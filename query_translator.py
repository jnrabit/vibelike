"""
query_translator.py
===================
Pre-Retrieval-Hook: deutsche Queries nach Englisch uebersetzen, damit
englische Wikipedia/RFC/PEP-Docs auch bei deutschen Suchanfragen treffen.

Design:
- Cheap-Check: Heuristik fuer "vermutlich schon Englisch" -> kein LLM-Call
- Cache: JSON-File mit content_hash -> translation (vermeidet
  Mehrfach-Uebersetzungen bei identischen Queries)
- Timeout: 5s harte Grenze, danach Fallback auf Original
- LLM: gemma2:2b default (was bereits babel_powerful nutzte)

Migriert aus quelibrium/quelibrium_terminal.py:translate_query().

Nutzung:
    from vibelike.query_translator import QueryTranslator
    t = QueryTranslator()
    result = t.translate("Wie funktioniert TLS Handshake?")
    print(result["translated"])   # 'How does TLS handshake work?'
    print(result["lang_detected"]) # 'de'
    print(result["cache_hit"])    # False (erstes Mal), True bei Wiederholung
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Optional

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


DEFAULT_MODEL = "gemma2:2b"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_TIMEOUT = 15.0  # gemma2:2b cold-load ~6s, warmer call <500ms
DEFAULT_CACHE_FILE = Path(__file__).parent / "data" / "translation_cache.json"

# Heuristik: deutsche Marker
_GERMAN_CHARS = set("äöüÄÖÜß")
_GERMAN_STOPWORDS = {
    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einen", "einem", "einer", "eines",
    "und", "oder", "aber", "wenn", "weil", "dass",
    "ich", "du", "er", "sie", "es", "wir", "ihr",
    "nicht", "mit", "von", "zu", "auf", "in", "aus",
    "ist", "war", "sind", "wird", "wurde", "werden",
    "wie", "was", "wo", "wann", "warum", "welche",
    "fuer", "auch", "noch", "schon", "nur",
}


def _looks_german(text: str) -> bool:
    """Heuristik: enthaelt der Text deutsche Indikatoren?"""
    if any(c in _GERMAN_CHARS for c in text):
        return True
    words = re.findall(r"[a-zA-ZäöüÄÖÜß]+", text.lower())
    german_hits = sum(1 for w in words if w in _GERMAN_STOPWORDS)
    return german_hits >= 1  # 1 Treffer reicht (kurze Queries)


def _cache_key(text: str, model: str) -> str:
    """Stabile ID fuer (Text, Modell)-Kombination."""
    payload = f"{model}|{text.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class QueryTranslator:
    """Cached DE->EN Translator via Ollama."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        timeout: float = DEFAULT_TIMEOUT,
        cache_file: Optional[Path] = None,
        enable_cache: bool = True,
    ):
        self.model = model
        self.ollama_url = ollama_url
        self.timeout = timeout
        self.enable_cache = enable_cache
        self.cache_file = cache_file if cache_file is not None else DEFAULT_CACHE_FILE
        self._cache: dict = self._load_cache() if enable_cache else {}
        self._session = requests.Session() if _HAS_REQUESTS else None

    # -- Cache --------------------------------------------------------------

    def _load_cache(self) -> dict:
        if not self.cache_file.exists():
            return {}
        try:
            with self.cache_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cache(self) -> None:
        if not self.enable_cache:
            return
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_file.open("w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # cache ist best-effort

    # -- LLM-Call -----------------------------------------------------------

    def _call_ollama(self, prompt: str) -> Optional[str]:
        if self._session is None:
            return None
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "num_predict": 60,
                "temperature": 0.0,
                "top_p": 0.9,
            },
        }
        try:
            r = self._session.post(self.ollama_url, json=payload, timeout=self.timeout)
            if r.status_code != 200:
                return None
            return r.json().get("response", "").strip()
        except Exception:
            return None

    # -- Translation --------------------------------------------------------

    def _build_prompt(self, query: str) -> str:
        return (
            "Translate the following German query into concise English suitable "
            "for keyword search in technical/scientific documents. "
            "Keep technical terms (TLS, HTTP, RAM, etc.) unchanged. "
            "Output ONLY the translated query — no quotes, no explanation, no prefix.\n\n"
            f"German: {query}\nEnglish:"
        )

    def _clean_response(self, raw: str) -> str:
        """Heuristisch unsaubere LLM-Antworten saeubern."""
        s = raw.strip()
        # Quotes entfernen
        s = s.strip('"\'')
        # Prefix wie 'English:' droppen
        if ":" in s and len(s.split(":", 1)[0]) <= 12:
            s = s.split(":", 1)[1].strip()
        # Bei Newlines: nur erste Zeile (verhindert Wuchern)
        s = s.split("\n")[0].strip()
        return s

    def translate(self, query: str) -> dict:
        """
        Uebersetze DE->EN falls noetig.

        Returns:
            {
                "original":      str,
                "translated":    str,       # == original wenn skip
                "lang_detected": "de"|"en", # vereinfachte Klassifikation
                "skipped":       bool,      # True wenn Heuristik 'eh englisch'
                "cache_hit":     bool,
                "duration_ms":   float,
            }
        """
        original = query.strip()
        t0 = time.time()

        if len(original) < 3:
            return {
                "original": original, "translated": original,
                "lang_detected": "en", "skipped": True,
                "cache_hit": False, "duration_ms": 0.0,
            }

        if not _looks_german(original):
            return {
                "original": original, "translated": original,
                "lang_detected": "en", "skipped": True,
                "cache_hit": False, "duration_ms": (time.time() - t0) * 1000,
            }

        # Cache-Lookup
        cache_id = _cache_key(original, self.model)
        if self.enable_cache and cache_id in self._cache:
            entry = self._cache[cache_id]
            return {
                "original": original,
                "translated": entry["translated"],
                "lang_detected": "de",
                "skipped": False,
                "cache_hit": True,
                "duration_ms": (time.time() - t0) * 1000,
            }

        # LLM-Call
        raw = self._call_ollama(self._build_prompt(original))
        if not raw:
            return {
                "original": original, "translated": original,
                "lang_detected": "de", "skipped": False,
                "cache_hit": False,
                "duration_ms": (time.time() - t0) * 1000,
            }

        translated = self._clean_response(raw) or original

        # Cache schreiben
        if self.enable_cache:
            self._cache[cache_id] = {
                "original": original,
                "translated": translated,
                "model": self.model,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_cache()

        return {
            "original": original,
            "translated": translated,
            "lang_detected": "de",
            "skipped": False,
            "cache_hit": False,
            "duration_ms": (time.time() - t0) * 1000,
        }


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="DE->EN Query-Translator (Test-CLI)")
    parser.add_argument("query", help="Query (DE oder EN)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    t = QueryTranslator(model=args.model, enable_cache=not args.no_cache)
    result = t.translate(args.query)

    print(f"  Original:   {result['original']}")
    print(f"  Translated: {result['translated']}")
    print(f"  Lang:       {result['lang_detected']}")
    print(f"  Skipped:    {result['skipped']}")
    print(f"  Cache-Hit:  {result['cache_hit']}")
    print(f"  Dauer:      {result['duration_ms']:.1f} ms")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
