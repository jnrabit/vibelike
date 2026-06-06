"""
query_decomposer.py
===================
Pre-Retrieval-Hook: mehr-aspektige Queries in fokussierte Teilfragen zerlegen, damit
beim Retrieval JEDER Anker getroffen wird — nicht nur der, der das Embedding dominiert.

Motivation: "Zusammenhang zwischen biochemischen und biophysischen Erklärungen in der
IT" trifft mit EINEM Embedding nur die Bio-Seite (stärkste Terme), die IT-Seite geht
unter. Zerlegt man in Teilfragen ("biochemical explanations", "biophysical methods in
computing") und retrievt jede getrennt + fusioniert per RRF, ist jeder Anker geerdet.

Design (analog query_translator.py):
- Heuristik-Gate: nur bei Mehr-Aspekt-Indikatoren (und/zwischen/vergleich/…) + genug
  Länge wird überhaupt ein LLM-Call gemacht. Einfache Queries → [original], kein Cost.
- Ollama Structured Output (JSON-Schema) erzwingt sauberes {"subqueries":[…]}.
- Cache: content_hash -> subqueries.
- Graceful: LLM weg/kaputt -> [original].

Nutzung:
    from query_decomposer import QueryDecomposer
    d = QueryDecomposer()
    d.decompose("relationship between biochemistry and IT")["subqueries"]
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


DEFAULT_MODEL = os.environ.get("VIBELIKE_DECOMPOSE_MODEL", "qwen2.5:3b")
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_TIMEOUT = 20.0
DEFAULT_CACHE_FILE = Path(__file__).parent / "data" / "decompose_cache.json"
MAX_SUBQUERIES = 3

# Mehr-Aspekt-Indikatoren: Koordination / Vergleich / Bezug über Domänen hinweg.
_MULTI = re.compile(
    r"\b(und|and|sowie|versus|vs|zwischen|between|unterschied|difference|"
    r"compare|vergleich|relationship|beziehung|zusammenhang|verbindung|both|jeweils)\b",
    re.IGNORECASE,
)

_SCHEMA = {
    "type": "object",
    "properties": {"subqueries": {"type": "array", "items": {"type": "string"}}},
    "required": ["subqueries"],
}


def _looks_multi_aspect(text: str) -> bool:
    words = re.findall(r"\w+", text)
    return len(words) >= 6 and bool(_MULTI.search(text))


def _cache_key(text: str, model: str) -> str:
    return hashlib.sha256(f"{model}|{text.strip().lower()}".encode("utf-8")).hexdigest()[:16]


class QueryDecomposer:
    """Cached Query-Zerlegung via Ollama (JSON-Schema)."""

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

    # -- Cache --
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
            pass

    # -- LLM --
    def _build_prompt(self, query: str) -> str:
        return (
            "Break the following search query into 2-3 focused, self-contained sub-queries, "
            "ONE per distinct concept or domain it touches. Each sub-query must stand alone "
            "(no pronouns referring to the others) and be in English, suitable for keyword/"
            "semantic search in technical & scientific documents. Do NOT add concepts the "
            "query does not mention. If the query is already single-topic, return it unchanged "
            "as the only element.\n\n"
            f"Query: {query}\n"
            'Respond as JSON: {"subqueries": ["...", "..."]}'
        )

    def _call_ollama(self, prompt: str) -> Optional[dict]:
        if self._session is None:
            return None
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": _SCHEMA,                 # Structured Output → valides JSON erzwungen
            "keep_alive": "10m",
            "options": {"num_predict": 200, "temperature": 0.0},
        }
        try:
            r = self._session.post(self.ollama_url, json=payload, timeout=self.timeout)
            if r.status_code != 200:
                return None
            return json.loads(r.json().get("response", "") or "{}")
        except Exception:
            return None

    def _clean(self, raw_subs, original: str) -> list:
        out, seen = [], set()
        for s in (raw_subs or []):
            if not isinstance(s, str):
                continue
            s = s.strip().strip('"\'').strip()
            key = s.lower()
            if len(s) >= 3 and key not in seen:
                seen.add(key)
                out.append(s)
        return out[:MAX_SUBQUERIES]

    def decompose(self, query: str) -> dict:
        """
        Returns {original, subqueries:[…], skipped:bool, cache_hit:bool, duration_ms}.
        subqueries enthält IMMER mindestens [original]. skipped=True ⇒ kein Fan-out nötig.
        """
        original = query.strip()
        t0 = time.time()
        base = {"original": original, "subqueries": [original], "skipped": True,
                "cache_hit": False, "duration_ms": 0.0}

        if not _looks_multi_aspect(original):
            base["duration_ms"] = (time.time() - t0) * 1000
            return base

        cache_id = _cache_key(original, self.model)
        if self.enable_cache and cache_id in self._cache:
            subs = self._cache[cache_id].get("subqueries") or [original]
            return {"original": original, "subqueries": subs,
                    "skipped": len(subs) <= 1, "cache_hit": True,
                    "duration_ms": (time.time() - t0) * 1000}

        data = self._call_ollama(self._build_prompt(original))
        subs = self._clean(data.get("subqueries") if isinstance(data, dict) else None, original)
        # < 2 brauchbare Teilfragen ⇒ kein Gewinn, beim Original bleiben.
        if len(subs) < 2:
            subs = [original]

        if self.enable_cache:
            self._cache[cache_id] = {"original": original, "subqueries": subs,
                                     "model": self.model,
                                     "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            self._save_cache()

        return {"original": original, "subqueries": subs,
                "skipped": len(subs) <= 1, "cache_hit": False,
                "duration_ms": (time.time() - t0) * 1000}


def main() -> int:
    import argparse, sys
    p = argparse.ArgumentParser(description="Query-Decomposer (Test-CLI)")
    p.add_argument("query")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args()
    d = QueryDecomposer(model=args.model, enable_cache=not args.no_cache)
    r = d.decompose(args.query)
    print(f"  Original:    {r['original']}")
    print(f"  Subqueries:  {r['subqueries']}")
    print(f"  Skipped:     {r['skipped']}  Cache: {r['cache_hit']}  {r['duration_ms']:.0f}ms")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
