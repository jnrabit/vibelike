"""
babel_synthesizer.py -- Quellen-fokussierter Synthesizer im "Feynman-Mode".

Migriert aus quelibrium/babel_powerful.py (Feb 2026), adaptiert an vibelikes
QwenCoder-Wrapper und seine Doc-Sources (WIKI_*/IETF_RFC/PYTHON_PEP/etc.).

Was es vom Original übernimmt:
- Wiki/Non-Wiki Splitting mit unterschiedlichen Quoten pro Mode
- Strukturierter Prompt: Konzept / Aktueller Stand / Deep Dive
- Feynman-Mode: Komplexität für intelligenten Laien aufschlüsseln,
  zu spezifische Paper ignorieren, Analogien einsetzen

Was modernisiert wurde:
- Ollama-Modell flexibel (default qwen3:8b statt gemma2:2b -- besseres Reasoning)
- Zweiter Mode "science" (behält Jargon, präzise) neben "feynman"
- Source-Klassifikation kompatibel mit vibelikes WIKI_*-Tags
- Wiederverwendbar via QwenCoder-Injection (kein eigener Session-State)

Integration-Hinweise (zum manuellen Übernehmen, nicht automatisiert):
- terminal.py: `research_mode()` -> babel.synthesize(query, found_docs)
- workflow_agent.py: `phase_briefing()` könnte mode="feynman" nutzen,
  um den Task vor dem Detail-Plan in einem strukturierten Konzept zu erden
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Optional


# --- Standalone-Fallback ohne vibelike-Imports ---------------------------------
# Wenn dieses Modul aus vibelike heraus importiert wird, nutzt es den dortigen
# QwenCoder. Wenn es als CLI alleinsteht, baut es einen minimalen Ollama-Client.

try:
    from terminal import QwenCoder, OLLAMA_URL  # type: ignore[import]
    _HAS_VIBELIKE_QWEN = True
except Exception:
    _HAS_VIBELIKE_QWEN = False
    OLLAMA_URL = "http://localhost:11434/api/generate"

    import requests

    class QwenCoder:  # type: ignore[no-redef]
        """Minimaler Ollama-Wrapper als Fallback (nur wenn standalone)."""

        def __init__(self, model: str = "qwen3:8b", num_predict: int = 1200,
                     keep_alive: str = "30m"):
            self.model = model
            self.num_predict = num_predict
            self.keep_alive = keep_alive
            self.session = requests.Session()

        def generate(self, prompt: str, system: Optional[str] = None,
                     temperature: float = 0.3, stream: bool = False) -> str:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": {
                    "temperature": temperature,
                    "num_ctx": 8192,
                    "num_predict": self.num_predict,
                },
            }
            if system:
                payload["system"] = system
            r = self.session.post(OLLAMA_URL, json=payload, timeout=600)
            if r.status_code != 200:
                return f"[ERR] HTTP {r.status_code}"
            return r.json().get("response", "")


# --- Source-Klassifikation ----------------------------------------------------

_WIKI_PREFIXES = ("WIKI_",)
_SPEC_PREFIXES = ("IETF_RFC", "PYTHON_PEP", "RUST_OFFICIAL", "MDN_")


def classify_source(source: str) -> str:
    """Klassifiziere eine vibelike-Source in {wiki, spec, science, other}."""
    s = (source or "").upper()
    if s.startswith(_WIKI_PREFIXES):
        return "wiki"
    if any(s.startswith(p) for p in _SPEC_PREFIXES):
        return "spec"
    if s.startswith(("ARXIV", "PAPER", "PHYS_", "SCI_")):
        return "science"
    return "other"


def _type_tag(category: str) -> str:
    """Menschenlesbares Tag fuer den Prompt-Kontext."""
    return {
        "wiki": "[BASIS]",
        "spec": "[SPEC]",
        "science": "[FORSCHUNG]",
        "other": "[QUELLE]",
    }.get(category, "[QUELLE]")


# --- Mode-Konfiguration -------------------------------------------------------

class _Mode:
    """Container fuer Mode-spezifische Quoten und Prompt-Anweisungen."""

    def __init__(self, name: str, quotas: dict[str, int], instruction: str,
                 temperature: float = 0.3):
        self.name = name
        self.quotas = quotas
        self.instruction = instruction
        self.temperature = temperature


MODES = {
    "feynman": _Mode(
        name="feynman",
        quotas={"wiki": 2, "spec": 4, "science": 3, "other": 1},
        temperature=0.3,
        instruction=(
            "ZIEL: Erklaere fuer einen intelligenten Laien.\n"
            "1. Ignoriere Quellen die zu spezifisch sind -- es sei denn sie zeigen das Grundprinzip.\n"
            "2. SYNTHETISIERE: Lies die Quellen, aber wiederhole nicht ihren Jargon.\n"
            "   Erklaere WAS sie bedeuten -- mit Analogien wo es hilft.\n"
            "3. STRUKTUR:\n"
            "   - **Das Konzept:** Was ist es? (Einfache Definition)\n"
            "   - **Der aktuelle Stand:** Woran arbeiten Praktiker/Forscher gerade?\n"
            "   - **Deep Dive:** Ein spannendes Detail, mit einer Analogie erklaert.\n"
        ),
    ),
    "science": _Mode(
        name="science",
        quotas={"wiki": 1, "spec": 4, "science": 4, "other": 1},
        temperature=0.2,
        instruction=(
            "ZIEL: Praezise technische Antwort fuer Fachpublikum.\n"
            "1. Behalte den Fachjargon der Quellen -- nicht vereinfachen.\n"
            "2. ZITIERE: bei jedem nicht-trivialen Claim 'Quelle N' angeben.\n"
            "3. STRUKTUR:\n"
            "   - **Definition:** technisch praezise, mit Begriffen aus den Quellen.\n"
            "   - **Mechanik:** wie funktioniert es konkret?\n"
            "   - **Open Questions / Limits:** was steht in den Quellen offen?\n"
        ),
    ),
}


# --- Synthesizer --------------------------------------------------------------

class BabelSynthesizer:
    """
    Quellen-fokussierter Synthesizer mit Wiki/Non-Wiki-Splitting und
    strukturiertem Mode-Prompt.

    Nutzung:
        synth = BabelSynthesizer()  # default: qwen3:8b, mode="feynman"
        result = synth.synthesize(query, docs)
        print(result["analysis"])
    """

    def __init__(self, qwen: Optional[QwenCoder] = None,
                 model: str = "qwen3:8b", num_predict: int = 1200,
                 default_mode: str = "feynman", max_used_docs: int = 10,
                 max_content_chars: int = 800):
        self.qwen = qwen if qwen is not None else QwenCoder(
            model=model, num_predict=num_predict
        )
        if default_mode not in MODES:
            raise ValueError(f"Unbekannter Mode: {default_mode!r}. "
                             f"Verfuegbar: {list(MODES.keys())}")
        self.default_mode = default_mode
        self.max_used_docs = max_used_docs
        self.max_content_chars = max_content_chars

    # -- Doc-Selektion --------------------------------------------------------

    def _select_docs(self, docs: list[dict], mode: _Mode) -> list[dict]:
        """Waehle bis zu max_used_docs gemaess Mode-Quoten."""
        buckets: dict[str, list[dict]] = {"wiki": [], "spec": [], "science": [], "other": []}
        for d in docs:
            cat = classify_source(d.get("source", ""))
            buckets[cat].append(d)

        selected: list[dict] = []
        for cat, quota in mode.quotas.items():
            picked = buckets[cat][:quota]
            for d in picked:
                d.setdefault("_category", cat)
            selected.extend(picked)

        # Auffuellen falls Quoten nicht ausgeschoepft
        if len(selected) < self.max_used_docs:
            already = {id(d) for d in selected}
            for cat in ("science", "spec", "wiki", "other"):
                for d in buckets[cat]:
                    if id(d) in already:
                        continue
                    d.setdefault("_category", cat)
                    selected.append(d)
                    if len(selected) >= self.max_used_docs:
                        break
                if len(selected) >= self.max_used_docs:
                    break

        return selected[:self.max_used_docs]

    # -- Prompt-Build ---------------------------------------------------------

    def _build_prompt(self, query: str, used_docs: list[dict], mode: _Mode) -> str:
        if used_docs:
            context_parts = ["=== WISSENSBASIS ==="]
            for i, doc in enumerate(used_docs, 1):
                tag = _type_tag(doc.get("_category", "other"))
                title = doc.get("title", "Unbekannt")
                source = doc.get("source", "?")
                content = (doc.get("content", "") or "")[:self.max_content_chars]
                context_parts.append(
                    f"\nQUELLE {i} {tag} ({source}): {title}\nINHALT: {content}"
                )
            context_block = "\n".join(context_parts)
        else:
            context_block = "=== WISSENSBASIS ===\n(keine Quellen verfuegbar)"

        return (
            "DU BIST: ein wissenschaftlicher Uebersetzer.\n"
            f"{mode.instruction}\n"
            f"INPUT FRAGE: \"{query}\"\n\n"
            f"DEINE WERKZEUGE:\n{context_block}\n\n"
            "WICHTIG: Antworte auf DEUTSCH. Fachbegriffe in Klammern erklaeren.\n\n"
            "ANTWORT:"
        )

    # -- Public API -----------------------------------------------------------

    def synthesize(self, query: str, docs: list[dict],
                   mode: Optional[str] = None) -> dict[str, Any]:
        """
        Synthetisiere eine Antwort.

        Args:
            query: Eingabe-Frage
            docs: Liste von Doc-Dicts mit Keys {title, content, source, distance?}
            mode: "feynman" oder "science" (default: self.default_mode)

        Returns:
            dict mit Keys:
              - analysis: str (die generierte Antwort, oder "[ERR] ...")
              - mode: str
              - used_docs: list[dict] (Auswahl mit _category-Tag)
              - source_stats: dict[str, int] (Anzahl pro Kategorie)
              - duration_s: float
        """
        mode_name = mode or self.default_mode
        if mode_name not in MODES:
            raise ValueError(f"Unbekannter Mode: {mode_name!r}")
        mode_cfg = MODES[mode_name]

        used = self._select_docs(docs, mode_cfg)
        prompt = self._build_prompt(query, used, mode_cfg)

        stats: dict[str, int] = {"wiki": 0, "spec": 0, "science": 0, "other": 0}
        for d in used:
            stats[d.get("_category", "other")] += 1

        t0 = time.time()
        response = self.qwen.generate(prompt, temperature=mode_cfg.temperature)
        duration = time.time() - t0

        return {
            "analysis": response,
            "mode": mode_name,
            "used_docs": used,
            "source_stats": stats,
            "duration_s": round(duration, 2),
        }


# --- CLI ---------------------------------------------------------------------

def _load_docs_from_json(path: str) -> list[dict]:
    """Lade Docs aus einer JSON-Datei (Liste von Dicts)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Erwarte JSON-Liste von Doc-Dicts")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Standalone-Test fuer BabelSynthesizer (ohne vibelike-Retrieval)."
    )
    parser.add_argument("query", help="Die Frage")
    parser.add_argument("--docs", type=str, default=None,
                        help="JSON-Datei mit Liste von Doc-Dicts (sonst leerer Kontext)")
    parser.add_argument("--mode", choices=list(MODES.keys()), default="feynman")
    parser.add_argument("--model", default="qwen3:8b",
                        help="Ollama-Modell (default qwen3:8b)")
    args = parser.parse_args()

    docs: list[dict] = []
    if args.docs:
        docs = _load_docs_from_json(args.docs)
        print(f"[INFO] {len(docs)} Docs geladen aus {args.docs}")

    synth = BabelSynthesizer(model=args.model, default_mode=args.mode)
    print(f"[INFO] Synthese-Modell: {synth.qwen.model}, Mode: {args.mode}")
    print()

    result = synth.synthesize(args.query, docs)

    print(result["analysis"])
    print()
    print("---")
    print(f"Mode: {result['mode']} | Dauer: {result['duration_s']}s")
    print(f"Quellen: {result['source_stats']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
