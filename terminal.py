#!/usr/bin/env python3
"""
terminal.py - Minimales CLI-Terminal für Code-Vault + qwen2.5-coder
================================================================

Start: python terminal.py

Features:
- Code-Vault Retrieval mit C++ Engine
- qwen2.5-coder über Ollama
- Log-Triplets: (query, context, response) als JSON-Lines
- Hardware-State Logging
- Keine Redis-Abhängigkeit
"""

import os
import sys
import json
import re
import time
import pickle
import numpy as np
import requests
from pathlib import Path
from dotenv import load_dotenv

# Lade .env-Datei am Anfang (explizit vom Projektverzeichnis)
# override=True damit bestehende Umgebungsvariablen überschrieben werden
_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_script_dir, '.env')
if os.path.exists(_env_path):
    load_dotenv(_env_path, override=True)
else:
    load_dotenv(override=True)  # Fallback auf Standard-Suche

try:
    from adapters import TerminalAdapter
    ADAPTERS_AVAILABLE = True
except ImportError:
    ADAPTERS_AVAILABLE = False

try:
    from workflow_agent import WorkflowAgent
    WORKFLOW_AVAILABLE = True
except ImportError:
    WORKFLOW_AVAILABLE = False

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from framework.quelibrium.core.protocol import Protocol
from framework.quelibrium.core.paths import CODE_VAULT_FILE, CODE_CACHE_FILE
from framework.quelibrium.intelligence.retrieval import ChaosRetrieval, RiemannianWarp, ThompsonSampler
from framework.quelibrium.intelligence.resonance import ResonanceField


# =============================================================================
# Konfiguration
# =============================================================================

# Foreground = 7b coder (4.9 GB, 100% GPU), Validator = 1.5b coder (1.4 GB, 100% GPU).
# Zusammen ~6.3 GB Modelle + Desktop = ~7.3 GB / 8.5 GB VRAM — passt parallel.
# StaticValidator fängt die fachliche Schwäche des 1.5b-Critics deterministisch ab.
MODEL = os.environ.get("VIBELIKE_QWEN_MODEL", "qwen2.5-coder:latest")
VALIDATOR_MODEL = os.environ.get("VIBELIKE_VALIDATOR_MODEL", "qwen2.5-coder:1.5b")
# Reasoning-Modell für Briefing/Strategy/Plan (generalist > coder für Analyse).
# GPU-optimiert: qwen2.5-coder:1.5b (100% GPU fit auf 8GB VRAM, 0.3s warm)
# Für Q&A: Claude Haiku (schnell, genug Qualität für Knowledge-Fragen)
ANALYSIS_MODEL = os.environ.get("VIBELIKE_ANALYSIS_MODEL", "claude-haiku-4-5-20251001")
# Code-Gen-Backend: "claude" (Frontier-API), "gemini" (Gemini-API),
# "council" (Lokal + Claude + Gemini parallel → Sonnet-Synthese), oder "ollama" (lokal).
# Default claude — fällt auf lokal zurück wenn Key/Paket fehlt.
CODEGEN_BACKEND = os.environ.get("VIBELIKE_CODEGEN_BACKEND", "claude").lower()
CODEGEN_MODEL = os.environ.get("VIBELIKE_CODEGEN_MODEL", "claude-sonnet-4-6")
# Rat-Modus (Council, via '??'-Präfix): A=lokal (KNOWLEDGE_ANSWER_MODEL/qwen3),
# B=zugeschaltetes Frontier (Haiku), Synthese=stärkeres Modell (Sonnet) → Konsens+Unterschiede.
COUNCIL_MODEL = os.environ.get("VIBELIKE_COUNCIL_MODEL", "claude-haiku-4-5-20251001")
SYNTH_MODEL = os.environ.get("VIBELIKE_SYNTH_MODEL", "claude-sonnet-4-6")

# ==== GEMINI-FLASH INTEGRATION - BEGIN ====
# Gemini-Rat-Modi: ??g = lokal + gemini-2.5-flash, ??a = lokal + Haiku + gemini-2.5-flash
GEMINI_COUNCIL_MODEL = os.environ.get("VIBELIKE_GEMINI_COUNCIL_MODEL", "gemini-2.5-flash")
# HINWEIS: Die Gemini API hat Quote-Limits. Bei hohen max_output_tokens kommt 503-Fehler.
# Mit max_output_tokens <= 256 funktioniert es, aber Antworten sind kurz.
GEMINI_SYNTH_MODEL = os.environ.get("VIBELIKE_GEMINI_SYNTH_MODEL", "gemini-2.5-pro")
# ==== GEMINI-FLASH INTEGRATION - END ====

# ==== MISTRAL INTEGRATION - BEGIN ====
# Mistral-Rat-Modi: ??m = lokal + mistral-large, ??a erweitert um Mistral
MISTRAL_COUNCIL_MODEL = os.environ.get("VIBELIKE_MISTRAL_COUNCIL_MODEL", "mistral-large-latest")
MISTRAL_SYNTH_MODEL = os.environ.get("VIBELIKE_MISTRAL_SYNTH_MODEL", "mistral-large-latest")
# RÜCKGÄNGIG MACHEN: Lösche diese beiden Zeilen.
# ==== MISTRAL INTEGRATION - END ====

# Großer Wissens-Vault: general-knowledge Korpus (188k Docs), PARALLEL zum Code-Vault
# abgefragt. Beide werden je Query durchsucht (ChaosRetrieval-Recall) und per Cosine
# auf gemeinsamer Skala fair zusammengeführt. VIBELIKE_DUAL_VAULT=0 schaltet ihn aus.
KNOWLEDGE_VAULT_FILE = os.environ.get(
    "VIBELIKE_KNOWLEDGE_VAULT", "/home/jnrabit/collect/data/monolith_archive.monolith")
KNOWLEDGE_CACHE_FILE = os.environ.get(
    "VIBELIKE_KNOWLEDGE_CACHE", "/home/jnrabit/collect/data/monolith_embedding_cache.pkl")
DUAL_VAULT = os.environ.get("VIBELIKE_DUAL_VAULT", "1") != "0"
# Query-Decomposition: mehr-aspektige Fragen in Teilfragen zerlegen + per RRF fusionieren,
# damit crossdomäne Anker alle getroffen werden (nicht nur der dominante). Nur bei
# Mehr-Aspekt-Heuristik aktiv, einfache Queries bleiben schnell. =0 schaltet aus.
QUERY_DECOMPOSE = os.environ.get("VIBELIKE_QUERY_DECOMPOSE", "1") != "0"
# REPL-Antwortmodell für Q&A über die Vaults: GENERALIST (qwen3:8b), nicht der Coder —
# sonst weist das Modell Nicht-Code-Fragen ab ("ich kann nur Code").
KNOWLEDGE_ANSWER_MODEL = os.environ.get("VIBELIKE_KNOWLEDGE_ANSWER_MODEL", ANALYSIS_MODEL)
# Kanonische ossifikat-DB — EINE Quelle (Dashboard/Web lesen dieselbe). Confirmte Fakten
# von hier erden Antworten (Grounding-Schleife). =0/leer schaltet Fakten-Grounding aus.
OSSIFIKAT_DB = os.environ.get("VIBELIKE_OSSIFIKAT_DB", os.path.join(ROOT, "data", "ossifikat.db"))
GROUND_ON_FACTS = os.environ.get("VIBELIKE_GROUND_ON_FACTS", "1") != "0"
# Architektur-Modus: "default" (Claude codet) oder "mitte" (Claude plant/reviewt,
# qwen-coder codet als Worker). Experiment "ehrliche Mitte".
VIBELIKE_ARCH = os.environ.get("VIBELIKE_ARCH", "default").lower()
OLLAMA_URL = "http://localhost:11434/api/generate"
LOG_FILE = os.path.join(ROOT, "logs", "triplets.jsonl")

# Erstelle Log-Verzeichnis
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


# =============================================================================
# Hardware State Logger
# =============================================================================

class HardwareLogger:
    """Loggt Hardware-State als binärnahes Format."""
    
    def __init__(self, protocol):
        self.protocol = protocol
        self.logs = []
    
    def log_state(self, query: str = None, label: str = None) -> dict:
        """Loggt aktuellen Hardware-State."""
        state = self.protocol.get_hardware_state()
        lorenz = self.protocol.get_lorenz_params()
        
        entry = {
            "timestamp": time.time(),
            "type": "hardware_state",
            "query": query,
            "label": label,
            "lorenz": {
                "x1": state["x1"], "y1": state["y1"], "z1": state["z1"], "w1": state["w1"],
                "x2": state["x2"], "y2": state["y2"],
            },
            "thermodynamics": {
                "entropy": state["entropy"],
                "temperature": state["temperature"],
                "cortex_bias": state["cortex_bias"],
            },
            "params": {
                "rho": lorenz["rho"], "sigma": lorenz["sigma"], "beta": lorenz["beta"],
                "reason": lorenz["reason"], "cycle": lorenz["cycle"],
            }
        }
        self.logs.append(entry)
        return entry
    
    def log_triplet(self, query: str, context: list, response: str) -> dict:
        """Loggt ein Triplet (Query, Context, Response)."""
        # Kontext als binärnahe Repräsentation
        context_bin = [{
            "id": c.get("id"),
            "distance": c.get("distance", 0),
            "source": c.get("source", ""),
            "content_hash": hash(str(c.get("content", "") or "")) % 2**32,
            "content_len": len(str(c.get("content", "") or ""))
        } for c in context]
        
        entry = {
            "timestamp": time.time(),
            "type": "triplet",
            "query": query,
            "query_hash": hash(query) % 2**32,
            "context": context_bin,
            "context_count": len(context),
            "response": response,
            "response_len": len(response),
            "response_hash": hash(response) % 2**32,
        }
        self.logs.append(entry)
        
        # Schreibe direkt in Log-Datei
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
        
        return entry


# =============================================================================
# Code Retriever
# =============================================================================

class CodeRetriever:
    """Code-Vault Retrieval mit C++ Engine + Advanced Chaos Retrieval."""

    EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, remote_url: str = "__env__"):
        # Remote-Modus: Suche läuft über den warmen Retrieval-Daemon (retrieval_service.py),
        # damit nicht jede frisch gespawnte terminal.py die ~40s Vault-Ladezeit zahlt.
        # remote_url=None erzwingt lokal (so lädt der Daemon selbst die Vaults, ohne sich
        # zu proxien). "__env__" = aus VIBELIKE_RETRIEVAL_URL lesen.
        if remote_url == "__env__":
            remote_url = os.environ.get("VIBELIKE_RETRIEVAL_URL")
        self.remote_url = (remote_url or "").rstrip("/") or None

        # Code-Vault lokal: leichtgewichtig (~1733 docs, <2s), liefert Telemetrie
        # (hw_logger/state) + ossifikat-Logging — in BEIDEN Modi gebraucht.
        self.protocol = Protocol(vault_file=CODE_VAULT_FILE, cache_file=CODE_CACHE_FILE)
        self.hw_logger = HardwareLogger(self.protocol)
        self._facts_cache = {}  # content-key → embedding (confirmte Fakten, lazy)

        # Ossifikat Integration (leicht) — auf die KANONISCHE DB (data/ossifikat.db)
        try:
            if ADAPTERS_AVAILABLE:
                self.terminal_adapter = TerminalAdapter(ossifikat_db_path=OSSIFIKAT_DB)
                print("[OK] 📊 Ossifikat TerminalAdapter aktiviert")
            else:
                self.terminal_adapter = None
        except Exception as e:
            print(f"[WARN] Ossifikat nicht verfügbar: {e}")
            self.terminal_adapter = None

        if self.remote_url:
            # ── Remote: kein Encoder/Vault/Chaos lokal — der Daemon hält alles warm ──
            self.encoder = None
            self.resonance_field = None
            self.chaos_retrieval = None
            self.use_chaos_retrieval = False
            self.query_translator = None
            self.decomposer = None
            self._engines = []
            print(f"[OK] 🔌 Retrieval-Daemon: {self.remote_url} (kein lokaler Vault-Load)")
            return

        # ── Lokal: Encoder + Chaos + beide Vaults selbst laden ──
        try:
            from sentence_transformers import SentenceTransformer
            device = "cuda" if self._has_cuda() else "cpu"
            self.encoder = SentenceTransformer(self.EMBEDDING_MODEL, device=device)
            print("[OK] SentenceTransformer geladen")
        except ImportError as e:
            print(f"[ERR] sentence-transformers nicht installiert: {e}")
            self.encoder = None

        try:
            self.resonance_field = ResonanceField()
            self.chaos_retrieval = ChaosRetrieval(protocol=self.protocol, field=self.resonance_field)
            print("[OK] ⚡ Chaos Retrieval mit Resonance Field aktiviert")
            self.use_chaos_retrieval = True
        except Exception as e:
            print(f"[WARN] Chaos Retrieval nicht verfügbar: {e}")
            self.chaos_retrieval = None
            self.use_chaos_retrieval = False

        # Pre-Retrieval Query-Translator (DE→EN): deutsche Queries treffen sonst
        # die englischen Wikipedia/RFC/PEP-Docs schlecht. Heuristik + Cache, kein
        # LLM-Call wenn Query eh englisch.
        try:
            from query_translator import QueryTranslator
            self.query_translator = QueryTranslator()
            print("[OK] 🌐 Query-Translator (DE→EN) aktiv")
        except Exception as e:
            print(f"[WARN] Query-Translator nicht verfügbar: {e}")
            self.query_translator = None

        # Query-Decomposer (crossdomäne Mehr-Aspekt-Fragen → Teilfragen + RRF-Fusion)
        self.decomposer = None
        if QUERY_DECOMPOSE:
            try:
                from query_decomposer import QueryDecomposer
                self.decomposer = QueryDecomposer()
                print("[OK] 🧭 Query-Decomposer (Multi-Aspekt) aktiv")
            except Exception as e:
                print(f"[WARN] Query-Decomposer nicht verfügbar: {e}")

        # Multi-Vault: primär Code-Vault; optional großer Wissens-Vault parallel.
        # Beide Engines werden je Query abgefragt und per Cosine fair gemerged.
        self._engines = [self._make_engine(self.protocol, self.chaos_retrieval, "code")]
        if DUAL_VAULT:
            try:
                if os.path.exists(KNOWLEDGE_VAULT_FILE):
                    kproto = Protocol(vault_file=KNOWLEDGE_VAULT_FILE, cache_file=KNOWLEDGE_CACHE_FILE)
                    kchaos = ChaosRetrieval(protocol=kproto, field=ResonanceField())
                    self._engines.append(self._make_engine(kproto, kchaos, "knowledge"))
                    print(f"[OK] 📚 Wissens-Vault: {len(kproto.archive):,} docs (parallel zum Code-Vault)")
                else:
                    print(f"[WARN] Wissens-Vault nicht gefunden: {KNOWLEDGE_VAULT_FILE}")
            except Exception as e:
                print(f"[WARN] Wissens-Vault nicht geladen: {e}")

        print(f"[OK] Code-Vault: {len(self.protocol.archive):,} docs, {len(self.protocol._doc_cache):,} vectors")
    
    @staticmethod
    def _has_cuda() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False
    
    def search(self, query: str, k: int = 10, source_boost: dict = None) -> tuple:
        """Such im Code-Vault via ChaosRetrieval. Rückgabe: (Dokumente, State vor/nach).

        ChaosRetrieval ist der primäre und einzige semantisch korrekte Pfad.
        Der frühere C++ raw_search-Fallback ist ENTFERNT — er lieferte
        query-unabhängig dieselben Docs mit dist=0 (Engine-Bug). Schlägt
        ChaosRetrieval fehl, greift ein numpy-Cosine-Fallback auf derselben
        Doc-Matrix: korrekt, nur ohne Chaos-Warp.

        source_boost: optional {source: factor}. factor<1 boostet (kleinere
        Distanz = höherer Rang), factor>1 bestraft. Re-Ranking nach Over-Fetch,
        damit z.B. {"PROJEKT_SELFCODE": 0.6} eigenen Code vor generische
        Wiki-Artikel zieht. Default None = unverändertes Ranking.

        Remote-Modus (self.remote_url gesetzt): delegiert die Suche an den warmen
        Retrieval-Daemon; lokal wird kein Vault/Encoder geladen.
        """
        if self.remote_url:
            return self._remote_search(query, k, source_boost)
        if not self.encoder:
            return [], None, None

        # Bei aktivem Boost mehr Kandidaten holen, damit Re-Ranking Material hat
        fetch_n = k * 3 if source_boost else k

        # Decomposition ZUERST auf dem Original — die Anker sind noch intakt (der
        # Übersetzer würde "biochemisch und biophysisch" zu "Biochemistry-Physiology"
        # kollabieren). Der Decomposer gibt direkt ENGLISCHE Teilfragen aus.
        sub_queries = None
        if self.decomposer is not None:
            try:
                dec = self.decomposer.decompose(query)
                if not dec.get("skipped") and len(dec.get("subqueries", [])) > 1:
                    sub_queries = dec["subqueries"]
                    print("[🧭 zerlegt: " + " | ".join(s[:30] for s in sub_queries) + "]")
            except Exception:
                sub_queries = None

        if sub_queries:
            # Multi-Query: Teilfragen sind bereits Englisch → direkt einbetten, je über
            # beide Vaults, dann Reciprocal Rank Fusion (rang-basiert, skaleninvariant,
            # jeder Anker kommt zum Zug). Kein Translator nötig.
            search_query = sub_queries[0]
            state_before = self.hw_logger.log_state(query, "search_start")
            ranked = [self._multi_search(self._embed(sq), fetch_n) for sq in sub_queries]
            docs = self._rrf_fuse(ranked, fetch_n)
        else:
            # Einzel-Aspekt: DE→EN übersetzen (Heuristik skippt englische Queries), dann
            # Multi-Vault via ChaosRetrieval-Recall + Cosine-Merge.
            search_query = query
            if self.query_translator is not None:
                try:
                    tr = self.query_translator.translate(query)
                    search_query = tr.get("translated") or query
                    if not tr.get("skipped") and search_query != query:
                        print(f"[🌐 '{query[:34]}' → '{search_query[:34]}']")
                except Exception:
                    search_query = query
            state_before = self.hw_logger.log_state(search_query, "search_start")
            docs = self._multi_search(self._embed(search_query), fetch_n)

        # Optionaler Source-Boost + Trim auf k
        if source_boost:
            docs = self._apply_source_boost(docs, source_boost)
        docs = docs[:k]

        # Grounding-Schleife: VERBÜRGTE Fakten autoritativ VORANSTELLEN (nicht vom
        # Vault-Trim betroffen) — was du bestätigt hast, erdet die Antwort.
        facts = self._confirmed_facts(self._embed(search_query))
        if facts:
            print(f"[🔖 {len(facts)} verbürgte(r) Fakt(en) als Grounding]")
            docs = facts + docs

        # Hardware-State nach Suche
        state_after = self.hw_logger.log_state(search_query, "search_end")

        return docs, state_before, state_after

    def _remote_search(self, query: str, k: int, source_boost: dict = None) -> tuple:
        """Suche über den warmen Retrieval-Daemon. hw_logger bleibt lokal (Code-Vault)
        für Telemetrie/Triplet-Log. Daemon nicht erreichbar ⇒ leeres Ergebnis (kein
        40s-Fallback-Load)."""
        state_before = self.hw_logger.log_state(query, "search_start")
        docs = []
        try:
            payload = {"query": query, "k": k}
            if source_boost:
                payload["source_boost"] = source_boost
            resp = requests.post(f"{self.remote_url}/search", json=payload, timeout=60)
            resp.raise_for_status()
            docs = resp.json().get("docs", [])
        except Exception as e:
            print(f"[WARN] Retrieval-Daemon ({self.remote_url}) nicht erreichbar: {e}\n"
                  f"        Läuft retrieval_service.py? (leeres Ergebnis)")
        state_after = self.hw_logger.log_state(query, "search_end")
        return docs, state_before, state_after

    def _numpy_cosine_search(self, query_vec: np.ndarray, k: int) -> list:
        """Korrekter Fallback: Cosine-Similarity direkt auf der Doc-Matrix (numpy).

        Ersetzt den kaputten C++ raw_search, der query-unabhängig immer dieselben
        Docs mit dist=0 lieferte. Nutzt dieselbe Matrix wie ChaosRetrieval.
        """
        matrix = self.protocol._matrix
        id_map = self.protocol._id_map
        if matrix is None or not id_map:
            return []
        q = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        m_norms = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8)
        sims = m_norms @ q
        top_idx = np.argsort(-sims)[:k]
        # distance = 1 - cosine (kleiner = ähnlicher, konsistent mit Konvention)
        results = [(id_map[i], float(1.0 - sims[i])) for i in top_idx]
        return self._docs_from_results(results, k, method="numpy_cosine")

    def _apply_source_boost(self, docs: list, source_boost: dict) -> list:
        """Re-Rankt Docs nach {source: factor}. factor<1 = Boost, >1 = Penalty.

        Multipliziert die Distanz (kleiner = besser) und sortiert neu. Quellen
        ohne Eintrag bleiben unverändert (factor 1.0).
        """
        for d in docs:
            factor = source_boost.get(d.get("source", ""), 1.0)
            d["distance"] = d["distance"] * factor
        docs.sort(key=lambda d: d["distance"])
        return docs

    def _docs_from_results(self, results: list, k: int, method: str = "chaos") -> list:
        """Helper: Konvertiere (doc_id, distance)-Ergebnisse in Doc-Dicts."""
        docs = []
        archive_index = {str(d.get("id", "")): d for d in self.protocol.archive}
        for doc_id, distance in results[:k]:
            doc = archive_index.get(str(doc_id))
            if doc:
                docs.append({
                    "id": doc_id,
                    "content": doc.get("text", doc.get("content", "")),
                    "title": doc.get("title", ""),
                    "source": doc.get("source", "code-vault"),
                    "distance": float(distance),
                    "retrieval_method": method,
                })
        return docs

    def _embed(self, text: str) -> np.ndarray:
        """Query-Text → 1D float32-Vektor (MiniLM, 384-dim)."""
        v = self.encoder.encode(text, convert_to_numpy=True).astype(np.float32)
        return v[0] if v.ndim > 1 else v

    def _rrf_fuse(self, ranked_lists: list, k: int, rrf_k: int = 60) -> list:
        """Reciprocal Rank Fusion mehrerer Ergebnislisten (je Teilfrage eine). Score =
        Σ 1/(rrf_k + rang) über alle Listen → rang-basiert, skaleninvariant, jeder Anker
        kommt zum Zug. Distanz bleibt die beste echte Cosine (fürs Grounding-Signal)."""
        agg = {}
        for docs in ranked_lists:
            for rank, d in enumerate(docs):
                key = (d.get("vault"), str(d.get("id")))
                e = agg.get(key)
                if e is None:
                    agg[key] = {"doc": d, "rrf": 1.0 / (rrf_k + rank),
                                "best": d.get("distance", 1.0)}
                else:
                    e["rrf"] += 1.0 / (rrf_k + rank)
                    e["best"] = min(e["best"], d.get("distance", 1.0))
        fused = []
        for e in agg.values():
            doc = dict(e["doc"])
            doc["distance"] = e["best"]   # echte Cosine-Distanz für assess_grounding
            doc["rrf"] = e["rrf"]
            fused.append(doc)
        fused.sort(key=lambda d: -d["rrf"])
        return fused[:k]

    def _fact_rationales(self) -> dict:
        """triple_id → Rationale aus data/bridge_rationales.jsonl (für reicheres Grounding)."""
        rats, p = {}, os.path.join(ROOT, "data", "bridge_rationales.jsonl")
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    rats[int(d["triple_id"])] = d.get("rationale", "")
        except Exception:
            pass
        return rats

    def _confirmed_facts(self, query_vec, k: int = 3, max_dist: float = 0.55) -> list:
        """Relevante VERBÜRGTE (confirmte) ossifikat-Tripel, per Cosine zur Query gewählt.
        Grounding-Schleife: was du bestätigt hast, erdet die Antwort. Frisch pro Query
        gelesen (neu Verbürgtes greift sofort, kein Neustart). Embeddings gecacht."""
        if not GROUND_ON_FACTS or self.encoder is None:
            return []
        try:
            from ossifikat.store import OssifikatStore
            s = OssifikatStore(OSSIFIKAT_DB)
            try:
                rows = s.query()  # confirmte, nicht-retracted Tripel
            finally:
                s.close()
        except Exception:
            return []
        if not rows:
            return []
        rats = self._fact_rationales()
        q = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        vecs = []
        for t in rows:
            rat = rats.get(t.id, "")
            key = f"{t.id}:{t.subject}|{t.predicate}|{t.object}|{rat[:40]}"
            v = self._facts_cache.get(key)
            if v is None:
                v = self._embed(f"{t.subject} {t.predicate} {t.object}. {rat}".strip())
                v = v / (np.linalg.norm(v) + 1e-8)
                self._facts_cache[key] = v
            vecs.append(v)
        sims = np.asarray(vecs) @ q
        out = []
        for i in np.argsort(-sims)[:k]:
            dist = float(1.0 - sims[i])
            if dist > max_dist:
                continue
            t = rows[i]
            rat = rats.get(t.id, "")
            out.append({
                "id": t.id,
                "content": f"{t.subject} —[{t.predicate}]→ {t.object}" + (f"  ({rat})" if rat else ""),
                "title": f"{t.subject} → {t.object}",
                "source": "ossifikat",
                "vault": "verbürgt",
                "distance": dist,
                "rationale": rat,
                "retrieval_method": "confirmed-fact",
            })
        return out

    def _make_engine(self, protocol, chaos, label: str) -> dict:
        """Bündelt eine Vault-Engine: Protocol + ChaosRetrieval + Matrix/ID-Maps."""
        id_map = list(getattr(protocol, "_id_map", None) or [])
        matrix = getattr(protocol, "_matrix", None)
        inv = {str(idv): row for row, idv in enumerate(id_map)}
        index = {str(d.get("id", "")): d for d in protocol.archive}
        return {"label": label, "protocol": protocol, "chaos": chaos,
                "matrix": matrix, "id_map": id_map, "inv": inv, "index": index}

    def _engine_candidates(self, eng: dict, query_vec, q_unit, fetch_n: int) -> list:
        """[(doc_id, cosine_distance)] einer Engine. ChaosRetrieval liefert Kandidaten
        (Recall), Cosine auf der Doc-Matrix rankt sie auf gemeinsamer Skala (Precision)."""
        matrix = eng["matrix"]
        inv = eng["inv"]
        if matrix is None or not inv:
            return []
        cand_ids = []
        chaos = eng["chaos"]
        if chaos is not None:
            try:
                chaos.warp.update(eng["protocol"].get_lorenz_params())
                res = chaos.search(query_vec, top_k=fetch_n * 3)
                cand_ids = [str(r[0]) for r in res if str(r[0]) in inv]
            except Exception:
                cand_ids = []
        if cand_ids:
            rows = np.array([inv[i] for i in cand_ids])
            sub = matrix[rows]
            sub = sub / (np.linalg.norm(sub, axis=1, keepdims=True) + 1e-8)
            sims = sub @ q_unit
            order = np.argsort(-sims)[:fetch_n]
            return [(cand_ids[j], float(1.0 - sims[j])) for j in order]
        # Fallback (Chaos leer/aus): volle Cosine über die Matrix.
        mn = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8)
        sims = mn @ q_unit
        top = np.argsort(-sims)[:fetch_n]
        return [(eng["id_map"][i], float(1.0 - sims[i])) for i in top]

    def _multi_search(self, query_vec, fetch_n: int) -> list:
        """Fragt alle Engines ab und merged per gemeinsamer Cosine-Distanz (kleiner=besser)."""
        q_unit = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        merged, seen = [], set()
        for eng in self._engines:
            for doc_id, dist in self._engine_candidates(eng, query_vec, q_unit, fetch_n):
                key = (eng["label"], str(doc_id))
                if key in seen:
                    continue
                seen.add(key)
                doc = eng["index"].get(str(doc_id))
                if not doc:
                    continue
                merged.append({
                    "id": doc_id,
                    "content": doc.get("text", doc.get("content", "")),
                    "title": doc.get("title", ""),
                    "source": doc.get("source", eng["label"]),
                    "vault": eng["label"],
                    "distance": float(dist),
                    "retrieval_method": "chaos+cosine",
                })
        merged.sort(key=lambda d: d["distance"])
        return merged


# =============================================================================
# qwen2.5-coder
# =============================================================================

class QwenCoder:
    """qwen-Wrapper über Ollama. Modell pro Instanz wählbar (Foreground/Validator)."""

    def __init__(self, model: str = None, num_predict: int = 2048, keep_alive: str = "30m"):
        self.model = model or MODEL
        self.num_predict = num_predict
        self.keep_alive = keep_alive
        self.session = requests.Session()
        try:
            self.session.get("http://localhost:11434/api/tags", timeout=5)
            print(f"[OK] Ollama läuft (model={self.model})")
        except Exception:
            print("[WARN] Ollama nicht erreichbar")

    def generate(self, prompt: str, system: str = None, temperature: float = 0.2,
                 stream: bool = False, fmt=None, cache_prefix: str = None) -> str:
        """Generiere mit dem konfigurierten Modell.

        stream=True: Tokens werden live nach stdout geschrieben (Vordergrund-Calls).
        stream=False: ein Block, kein Live-Output (Hintergrund-Threads, sonst Interleaving).
        fmt: Ollama `format` — "json" oder ein JSON-Schema-Dict. Schema wird intern
        zu GBNF kompiliert → grammar-constrained decoding (ungültige Ausgabe unmöglich).
        cache_prefix: stabiler Präfix → vorne in system gefaltet, damit llama.cpp den
        KV-Präfix über Calls hinweg recycelt (Signatur-Kompat mit ClaudeCoder).
        Rückgabe ist in beiden Fällen der volle Antworttext.
        """
        if cache_prefix:
            system = f"{cache_prefix}\n\n{system}" if system else cache_prefix
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature, "top_p": 0.9, "num_predict": self.num_predict},
        }
        if system:
            payload["system"] = system
        if fmt is not None:
            payload["format"] = fmt

        try:
            if not stream:
                response = self.session.post(OLLAMA_URL, json=payload, timeout=600)
                if response.status_code == 200:
                    return response.json().get("response", "")
                return f"[ERR] HTTP {response.status_code}"

            # Streaming: zeilenweise JSON-Chunks parsen, jedes "response"-Feld printen
            chunks = []
            with self.session.post(OLLAMA_URL, json=payload, stream=True, timeout=600) as resp:
                if resp.status_code != 200:
                    return f"[ERR] HTTP {resp.status_code}"
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    token = obj.get("response", "")
                    if token:
                        print(token, end="", flush=True)
                        chunks.append(token)
                    if obj.get("done"):
                        break
            print()  # Newline nach dem Stream
            return "".join(chunks)
        except Exception as e:
            return f"[ERR] {str(e)}"


class ClaudeCoder:
    """Anthropic-API-Backend mit QwenCoder-kompatiblem Interface (drop-in fürs Code-Gen).

    Gleiche generate()-Signatur wie QwenCoder, damit der Workflow nichts merkt.
    Grund: ~7b-lokal scheitert an semantischer Instruktionstreue (nicht Refusal/
    Format) — diese Schicht braucht ein Frontier-Modell. Die deterministischen
    Guards (Regression-Guard, Static-Validator) bleiben als Netz davor.

    .usable == False, wenn Key oder Paket fehlt → Aufrufer kann auf lokal zurückfallen.
    """

    def __init__(self, model: str = None, num_predict: int = 8192, **_ignored):
        self.model = model or CODEGEN_MODEL
        self.num_predict = num_predict          # → max_tokens
        self._client = None
        self.usable = False

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("[WARN] ANTHROPIC_API_KEY nicht gesetzt — ClaudeCoder nicht nutzbar")
            return
        try:
            import anthropic
        except ImportError:
            print("[WARN] anthropic-Paket fehlt — `pip install anthropic`")
            return
        try:
            self._client = anthropic.Anthropic(api_key=api_key)
            self.usable = True
            print(f"[OK] Claude-API bereit (model={self.model})")
        except Exception as e:
            print(f"[WARN] Claude-Init fehlgeschlagen: {e}")

    def generate(self, prompt: str, system: str = None, temperature: float = 0.2,
                 stream: bool = False, fmt=None, cache_prefix: str = None) -> str:
        """Generiere via Claude-API. stream=True schreibt Tokens live nach stdout;
        Rückgabe ist in beiden Fällen der volle Antworttext. Fehler → '[ERR] ...'.

        fmt: nur für Signatur-Kompat mit QwenCoder (Ollama-Schema) — hier ignoriert.
        cache_prefix: stabiler Präfix → gecachter system-Block (cache_control ephemeral).
        Über mehrere Calls mit identischem Präfix (z.B. Codegen-Retries) wird der Block
        nur einmal berechnet → cache_read statt Neuberechnung.
        """
        if not self.usable:
            return "[ERR] ClaudeCoder nicht initialisiert (Key/Paket fehlt)"

        kwargs = {
            "model": self.model,
            "max_tokens": self.num_predict,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if cache_prefix:
            blocks = [{"type": "text", "text": cache_prefix,
                       "cache_control": {"type": "ephemeral"}}]
            if system:
                blocks.append({"type": "text", "text": system})
            kwargs["system"] = blocks
        elif system:
            kwargs["system"] = system

        try:
            if not stream:
                msg = self._client.messages.create(**kwargs)
                return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

            chunks = []
            with self._client.messages.stream(**kwargs) as s:
                for text in s.text_stream:
                    print(text, end="", flush=True)
                    chunks.append(text)
            print()  # Newline nach dem Stream
            return "".join(chunks)
        except Exception as e:
            return f"[ERR] {str(e)}"


# ==== GEMINI-FLASH INTEGRATION - BEGIN ====
class GeminiCoder:
    """Google Gemini-API-Backend mit QwenCoder-kompatiblem Interface.

    Gleiche generate()-Signatur wie QwenCoder/ClaudeCoder für Drop-in-Kompatibilität.
    Nutzt google-genai SDK. .usable == False wenn Key oder Paket fehlt.
    
    RÜCKGÄNGIG MACHEN: Lösche diese Klasse und alle Referenzen auf GeminiCoder.
    """

    def __init__(self, model: str = None, num_predict: int = 8192, **_ignored):
        self.model = model or GEMINI_COUNCIL_MODEL
        # Mit dem kostenpflichtigen Google Plan: max_output_tokens bis 8192 möglich!
        self.num_predict = num_predict
        self._client = None
        self.usable = False

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("[WARN] GEMINI_API_KEY nicht gesetzt — GeminiCoder nicht nutzbar")
            return
        try:
            import google.genai as genai
        except ImportError:
            print("[WARN] google-genai Paket fehlt — `pip install google-genai`")
            return
        try:
            self._client = genai.Client(api_key=api_key)
            # Client erstellt = Verbindung OK (kein models.list() - zu langsam)
            self.usable = True
            print(f"[OK] Gemini-API bereit (model={self.model})")
        except Exception as e:
            print(f"[WARN] Gemini-Init fehlgeschlagen: {e}")

    def generate(self, prompt: str, system: str = None, temperature: float = 0.2,
                 stream: bool = False, fmt=None, cache_prefix: str = None) -> str:
        """Generiere via Gemini-API. stream=True schreibt Tokens live nach stdout.
        Rückgabe ist in beiden Fällen der volle Antworttext. Fehler → '[ERR] ...'.
        
        fmt: nur für Signatur-Kompat mit QwenCoder — hier ignoriert.
        cache_prefix: nur für Signatur-Kompat — hier ignoriert.
        
        ==== GEMINI-FLASH INTEGRATION - FIX ====
        Korrigierte API: google-genai nutzt models.generate_content() statt chat.completions
        """
        if not self.usable:
            return "[ERR] GeminiCoder nicht initialisiert (GEMINI_API_KEY fehlt)"

        try:
            from google.genai import types
            # Korrekte google-genai-API: System gehört in config.system_instruction
            # (NICHT als 'system'-Rolle in contents — die kennt Gemini nicht), Streaming
            # ist eine EIGENE Methode generate_content_stream (kein stream=-Flag).
            cfg = types.GenerateContentConfig(
                system_instruction=system or None,
                max_output_tokens=self.num_predict,
                temperature=temperature,
            )
            # HINWEIS: Google Generative AI streaming gibt oft unvollständige chunks zurück
            # Daher nutzen wir immer non-streaming und geben die volle antwort aus
            r = self._client.models.generate_content(
                model=self.model, contents=prompt, config=cfg)
            text = r.text or ""
            if stream and text:
                # Wenn stream=True gewünscht, zumindest die volle antwort ausgeben
                print(text, flush=True)
            return text
        except Exception as e:
            return f"[ERR] {type(e).__name__}: {e}"


# ==== GEMINI-FLASH INTEGRATION - END ====

# ==== MISTRAL INTEGRATION - BEGIN ====
class MistralCoder:
    """Mistral-API-Backend mit QwenCoder-kompatiblem Interface.

    Gleiche generate()-Signatur wie QwenCoder/ClaudeCoder/GeminiCoder für Drop-in-Kompatibilität.
    Nutzt mistralai SDK. .usable == False wenn Key oder Paket fehlt.
    
    RÜCKGÄNGIG MACHEN: Lösche diese Klasse und alle Referenzen auf MistralCoder.
    """

    def __init__(self, model: str = None, num_predict: int = 8192, **_ignored):
        self.model = model or MISTRAL_COUNCIL_MODEL
        self.num_predict = num_predict
        self._client = None
        self.usable = False

        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            print("[WARN] MISTRAL_API_KEY nicht gesetzt — MistralCoder nicht nutzbar")
            return
        try:
            from mistralai.client import Mistral
        except ImportError:
            print("[WARN] mistralai Paket fehlt — `pip install mistralai`")
            return
        try:
            self._client = Mistral(api_key=api_key)
            self.usable = True
            print(f"[OK] Mistral-API bereit (model={self.model})")
        except Exception as e:
            print(f"[WARN] Mistral-Init fehlgeschlagen: {e}")

    def generate(self, prompt: str, system: str = None, temperature: float = 0.2,
                 stream: bool = False, fmt=None, cache_prefix: str = None) -> str:
        """Generiere via Mistral-API. stream=True schreibt Tokens live nach stdout.
        Rückgabe ist in beiden Fällen der volle Antworttext. Fehler → '[ERR] ...'.
        
        ==== MISTRAL INTEGRATION - FIX ====
        Korrigierte API: mistralai v2 nutzt client.chat.complete() statt client.chat()
        
        fmt: nur für Signatur-Kompat mit QwenCoder — hier ignoriert.
        cache_prefix: nur für Signatur-Kompat — hier ignoriert.
        """
        if not self.usable:
            return "[ERR] MistralCoder nicht initialisiert (MISTRAL_API_KEY fehlt)"

        try:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            if not stream:
                response = self._client.chat.complete(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=self.num_predict,
                )
                return response.choices[0].message.content or ""

            # Streaming
            chunks = []
            response = self._client.chat.stream(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=self.num_predict,
            )
            for chunk in response:
                if hasattr(chunk, 'choices') and chunk.choices:
                    text = chunk.choices[0].delta.content or ""
                    if text:
                        print(text, end="", flush=True)
                        chunks.append(text)
            print()  # Newline nach dem Stream
            return "".join(chunks)
        except Exception as e:
            return f"[ERR] {str(e)}"


# ==== MISTRAL INTEGRATION - END ====


# =============================================================================
# System Prompt Builder
# =============================================================================

def assess_grounding(context: list) -> dict:
    """Wie gut stützen die Quellen die Query? Basis: kleinste Cosine-Distanz (0=ideal).
    Liefert Banner (für die Konsole) + Direktive (in den System-Prompt), damit hótr̥ bei
    schwacher Deckung ehrlich hedged statt souverän zu konfabulieren — genau die
    'Souveränität-vortäuschen'-Falle, die bei crossdomänen Fragen auftritt."""
    if not context:
        return {"level": "leer", "best": None,
                "banner": "[⚠ keine Quellen — Antwort ist reines Modellwissen, unbelegt]",
                "directive": "Es wurden KEINE Quellen gefunden. Sag das offen; antworte "
                             "vorsichtig aus eigenem Wissen und markiere alles als unbelegt."}
    best = min(d.get("distance", 1.0) for d in context)
    if best <= 0.30:
        return {"level": "stark", "best": best, "banner": "", "directive": ""}
    if best <= 0.45:
        return {"level": "schwach", "best": best,
                "banner": f"[⚠ Quellen schwach: beste Distanz {best:.2f} — Antwort eher Schlussfolgerung als Beleg]",
                "directive": (f"ACHTUNG: Beste Quellen-Distanz nur {best:.2f} (mäßige Passung). "
                              "Stütze dich nur so weit auf die Quellen, wie sie wirklich tragen, "
                              "und markiere klar, was Schlussfolgerung statt Beleg ist.")}
    return {"level": "sehr schwach", "best": best,
            "banner": f"[⚠ Quellen sehr schwach: beste Distanz {best:.2f} — größtenteils Spekulation]",
            "directive": (f"ACHTUNG: Selbst die beste Quelle passt kaum (Distanz {best:.2f}). Sag "
                          "ausdrücklich, dass die Quellen das Thema kaum abdecken; spekuliere NICHT "
                          "souverän, sondern trenne klar Beleg von Vermutung.")}


def build_system_prompt(context: list) -> str:
    """Baue System-Prompt aus VERBÜRGTEN Fakten (ratifiziert) + Vault-Kontext.
    Bei schwacher Quellen-Deckung wird eine Ehrlichkeits-Direktive vorangestellt."""
    context = context or []
    head = assess_grounding(context)["directive"]
    head = (head + "\n\n") if head else ""

    # Grounding-Schleife: von dir bestätigte Fakten sind autoritativ.
    facts = [d for d in context if d.get("vault") == "verbürgt"]
    sources = [d for d in context if d.get("vault") != "verbürgt"]
    fact_block = ""
    if facts:
        fl = "\n".join("- " + (d.get("content") or "") for d in facts[:5])
        fact_block = ("VERBÜRGTE FAKTEN (von dir bestätigt — als gesichert behandeln, bei "
                      "Widerspruch haben sie Vorrang vor den QUELLEN):\n" + fl + "\n\n")

    if not sources:
        body = ("Du bist ein präziser, sachkundiger Assistent. Antworte auf Deutsch. "
                "Bei Code: Markdown-Codeblöcke mit Sprachen-Tag. Wenn du etwas nicht "
                "sicher weißt, sage es explizit.")
        return head + fact_block + body

    src = []
    for i, d in enumerate(sources[:4]):  # Top 4 für Fokus, vault-übergreifend gerankt
        vault = d.get("vault", "")
        tag = d.get("source", "vault") + (f" · {vault}" if vault else "")
        dist = d.get("distance", 0) or 0
        # content kann in seltenen Vault-Docs ein Dict/Objekt sein → immer str
        raw = d.get("content", "") or ""
        content = str(raw)[:450] if not isinstance(raw, str) else raw[:450]
        src.append(f"QUELLE {i+1} (d={dist:.2f}, {tag}):\n{content}")

    rules = ("Du bist ein präziser Recherche- und Fachassistent.\n\n"
             "REGELN:\n"
             "1. Antworte primär anhand der VERBÜRGTEN FAKTEN und QUELLEN — Fakten haben Vorrang.\n"
             "2. Code immer in Markdown-Codeblöcken mit Sprachen-Tag.\n"
             "3. Reichen sie nicht, sag das explizit und ergänze vorsichtig aus eigenem Wissen.\n"
             "4. Präzise, auf Deutsch.\n\n"
             "QUELLEN:\n\n")
    return head + fact_block + rules + "\n\n".join(src)


def run_council(query: str, system_prompt: str, local_coder, council_coder, synth_coder) -> str:
    """Rat-Modus: lokale Antwort (A) + zugeschaltete Frontier-Antwort (B) + Synthese
    (stärkeres Modell) mit KONSENS/UNTERSCHIEDEN. Übereinstimmung = sicher, Divergenz =
    ehrlich markiert (nicht weggeglättet). Rückgabe = Text für die Gesprächshistorie."""
    sep = "-" * 60

    # A — lokal (grounded, wie sonst)
    print(f"\n── Antwort A (lokal · {local_coder.model}) ──\n{sep}")
    ans_a = local_coder.generate(query, system=system_prompt, stream=True)
    ans_a = re.sub(r"<think>.*?</think>", "", ans_a, flags=re.DOTALL).strip()
    print(sep)

    # B — zugeschaltetes Frontier-Modell, gleicher Kontext
    if not (council_coder and council_coder.usable):
        print("[WARN] Rat-Modell nicht nutzbar (ANTHROPIC_API_KEY?) — nur lokale Antwort A.")
        return ans_a
    print(f"\n── Antwort B ({council_coder.model}) ──\n{sep}")
    ans_b = council_coder.generate(query, system=system_prompt, stream=True)
    print(sep)

    # Synthese — stärkeres Modell vergleicht A & B
    if not (synth_coder and synth_coder.usable):
        print("[WARN] Synthese-Modell nicht nutzbar — A und B stehen oben nebeneinander.")
        return f"{ans_a}\n\n---\n\n{ans_b}"
    synth_prompt = (
        f"FRAGE:\n{query}\n\n"
        f"ANTWORT A (lokales Modell):\n{ans_a}\n\n"
        f"ANTWORT B (Frontier-Modell):\n{ans_b}\n\n"
        "Vergleiche A und B. Antworte auf Deutsch in genau zwei Abschnitten:\n"
        "KONSENS: worauf sich beide einigen (das Verlässliche), knapp.\n"
        "UNTERSCHIEDE: jeder Punkt, an dem sie divergieren — konkret benannt, mit ehrlicher "
        "Einschätzung, welche Seite plausibler ist und warum (oder dass es offen bleibt). "
        "Glätte den Dissens NICHT weg — die Unterschiede sind das Wichtigste."
    )
    synth_system = ("Du bist ein präziser Schiedsrichter zweier Modell-Antworten. Ehrlich, "
                    "knapp, kein Geschwafel; Unsicherheit offen markieren.")
    print(f"\n── 🜂 Synthese ({synth_coder.model}) ──\n{sep}")
    synth = synth_coder.generate(synth_prompt, system=synth_system, stream=True)
    print(sep)
    return synth or f"{ans_a}\n\n---\n\n{ans_b}"


# ==== GEMINI-FLASH INTEGRATION - BEGIN ====
def run_council_gemini(query: str, system_prompt: str, local_coder, gemini_council_coder, gemini_synth_coder) -> str:
    """Gemini-Rat-Modus: lokale Antwort (A) + gemini-2.5-flash (B) + gemini-2.5-pro Synthese.
    
    ==== GEMINI-FLASH INTEGRATION - FIX ====
    Fehlerbehandlung für API-Fehler (z.B. 503 UNAVAILABLE) hinzugefügt.
    
    RÜCKGÄNGIG MACHEN: Lösche diese Funktion und alle Aufrufe.
    """
    sep = "-" * 60
    
    def _is_valid_answer(ans):
        """Prüfe ob eine Antwort gültig ist (nicht leer und kein Fehler)."""
        if not ans or not isinstance(ans, str):
            return False
        if ans.strip().startswith("[ERR]"):
            return False
        return bool(ans.strip())

    # A — lokal (grounded, wie sonst)
    print(f"\n── Antwort A (lokal · {local_coder.model}) ──\n{sep}")
    ans_a = local_coder.generate(query, system=system_prompt, stream=True)
    ans_a = re.sub(r"<think>.*?</think>", "", ans_a, flags=re.DOTALL).strip()
    print(sep)

    # B — gemini-2.5-flash
    if not (gemini_council_coder and gemini_council_coder.usable):
        print("[WARN] Gemini-Rat-Modell nicht nutzbar (GEMINI_API_KEY?) — nur lokale Antwort A.")
        return ans_a
    print(f"\n── Antwort B ({gemini_council_coder.model}) ──\n{sep}")
    ans_b = gemini_council_coder.generate(query, system=system_prompt, stream=True)
    print(sep)
    
    # Prüfe ob die Antwort gültig ist (kein API-Fehler)
    if not _is_valid_answer(ans_b):
        print(f"[WARN] Gemini lieferte keinen gültigen Text — nur A. Grund: {str(ans_b).strip()[:160]}")
        return ans_a

    # Synthese — gemini-2.5-pro
    if not (gemini_synth_coder and gemini_synth_coder.usable):
        print("[WARN] Gemini-Synthese-Modell nicht nutzbar — A und B stehen oben nebeneinander.")
        return f"{ans_a}\n\n---\n\n{ans_b}"
    synth_prompt = (
        f"FRAGE:\n{query}\n\n"
        f"ANTWORT A (lokales Modell):\n{ans_a}\n\n"
        f"ANTWORT B (Gemini-Flash):\n{ans_b}\n\n"
        "Vergleiche A und B. Antworte auf Deutsch in genau zwei Abschnitten:\n"
        "KONSENS: worauf sich beide einigen (das Verlässliche), knapp.\n"
        "UNTERSCHIEDE: jeder Punkt, an dem sie divergieren — konkret benannt, mit ehrlicher "
        "Einschätzung, welche Seite plausibler ist und warum (oder dass es offen bleibt). "
        "Glätte den Dissens NICHT weg — die Unterschiede sind das Wichtigste."
    )
    synth_system = ("Du bist ein präziser Schiedsrichter zweier Modell-Antworten. Ehrlich, "
                    "knapp, kein Geschwafel; Unsicherheit offen markieren.")
    print(f"\n── 🜂 Synthese ({gemini_synth_coder.model}) ──\n{sep}")
    synth = gemini_synth_coder.generate(synth_prompt, system=synth_system, stream=True)
    print(sep)
    return synth or f"{ans_a}\n\n---\n\n{ans_b}"


# ==== MISTRAL INTEGRATION - BEGIN ====
def run_council_mistral(query: str, system_prompt: str, local_coder, mistral_council_coder, mistral_synth_coder) -> str:
    """Mistral-Rat-Modus: lokale Antwort (A) + mistral-large (B) + mistral-large Synthese.
    
    ==== MISTRAL INTEGRATION - FIX ====
    Fehlerbehandlung für API-Fehler hinzugefügt.
    
    RÜCKGÄNGIG MACHEN: Lösche diese Funktion und alle Aufrufe.
    """
    sep = "-" * 60
    
    def _is_valid_answer(ans):
        """Prüfe ob eine Antwort gültig ist (nicht leer und kein Fehler)."""
        if not ans or not isinstance(ans, str):
            return False
        if ans.strip().startswith("[ERR]"):
            return False
        return bool(ans.strip())

    # A — lokal (grounded, wie sonst)
    print(f"\n── Antwort A (lokal · {local_coder.model}) ──\n{sep}")
    ans_a = local_coder.generate(query, system=system_prompt, stream=True)
    ans_a = re.sub(r"<think>.*?</think>", "", ans_a, flags=re.DOTALL).strip()
    print(sep)

    # B — mistral-large
    if not (mistral_council_coder and mistral_council_coder.usable):
        print("[WARN] Mistral-Rat-Modell nicht nutzbar (MISTRAL_API_KEY?) — nur lokale Antwort A.")
        return ans_a
    print(f"\n── Antwort B ({mistral_council_coder.model}) ──\n{sep}")
    ans_b = mistral_council_coder.generate(query, system=system_prompt, stream=True)
    print(sep)
    
    # Prüfe ob die Antwort gültig ist (kein API-Fehler)
    if not _is_valid_answer(ans_b):
        print(f"[WARN] Mistral lieferte keinen gültigen Text — nur A. Grund: {str(ans_b).strip()[:160]}")
        return ans_a

    # Synthese — mistral-large (gleiches Modell)
    if not (mistral_synth_coder and mistral_synth_coder.usable):
        print("[WARN] Mistral-Synthese-Modell nicht nutzbar — A und B stehen oben nebeneinander.")
        return f"{ans_a}\n\n---\n\n{ans_b}"
    synth_prompt = (
        f"FRAGE:\n{query}\n\n"
        f"ANTWORT A (lokales Modell):\n{ans_a}\n\n"
        f"ANTWORT B (Mistral):\n{ans_b}\n\n"
        "Vergleiche A und B. Antworte auf Deutsch in genau zwei Abschnitten:\n"
        "KONSENS: worauf sich beide einigen (das Verlässliche), knapp.\n"
        "UNTERSCHIEDE: jeder Punkt, an dem sie divergieren — konkret benannt, mit ehrlicher "
        "Einschätzung, welche Seite plausibler ist und warum (oder dass es offen bleibt). "
        "Glätte den Dissens NICHT weg — die Unterschiede sind das Wichtigste."
    )
    synth_system = ("Du bist ein präziser Schiedsrichter zweier Modell-Antworten. Ehrlich, "
                    "knapp, kein Geschwafel; Unsicherheit offen markieren.")
    print(f"\n── 🜂 Synthese ({mistral_synth_coder.model}) ──\n{sep}")
    synth = mistral_synth_coder.generate(synth_prompt, system=synth_system, stream=True)
    print(sep)
    return synth or f"{ans_a}\n\n---\n\n{ans_b}"


# ==== MISTRAL INTEGRATION - END ====

def run_council_all(query: str, system_prompt: str, local_coder, council_coder, gemini_council_coder, synth_coder, mistral_council_coder=None, mistral_synth_coder=None) -> str:
    """ALL-IN Rat-Modus: lokal + Haiku + gemini-2.5-flash + mistral-large mit Synthese.
    
    A = lokal, B = Haiku, C = gemini-2.5-flash, D = mistral-large (falls verfügbar)
    Synthese = stärkstes verfügbares Modell.
    
    ==== GEMINI-FLASH + MISTRAL INTEGRATION - FIX ====
    Fehlerbehandlung für API-Fehler (z.B. 503 UNAVAILABLE) hinzugefügt.
    Antworten die mit [ERR] beginnen werden als ungültig behandelt.
    
    RÜCKGÄNGIG MACHEN: Lösche diese Funktion und alle Aufrufe.
    """
    sep = "-" * 60
    
    def _is_valid_answer(ans):
        """Prüfe ob eine Antwort gültig ist (nicht leer und kein Fehler)."""
        if not ans or not isinstance(ans, str):
            return False
        # Fehler-Antworten erkennen
        if ans.strip().startswith("[ERR]"):
            return False
        return bool(ans.strip())

    # A — lokal
    print(f"\n── Antwort A (lokal · {local_coder.model}) ──\n{sep}")
    ans_a = local_coder.generate(query, system=system_prompt, stream=True)
    ans_a = re.sub(r"<think>.*?</think>", "", ans_a, flags=re.DOTALL).strip()
    print(sep)

    # B — Haiku
    if not (council_coder and council_coder.usable):
        print("[WARN] Haiku-Modell nicht nutzbar (ANTHROPIC_API_KEY?) — nur lokal + Gemini falls verfügbar")
        ans_b = None
    else:
        print(f"\n── Antwort B ({council_coder.model}) ──\n{sep}")
        ans_b = council_coder.generate(query, system=system_prompt, stream=True)
        print(sep)

    # C — gemini-2.5-flash
    if not (gemini_council_coder and gemini_council_coder.usable):
        print("[WARN] Gemini-Flash-Modell nicht nutzbar (GEMINI_API_KEY?) — nur lokal + Haiku falls verfügbar")
        ans_c = None
    else:
        print(f"\n── Antwort C ({gemini_council_coder.model}) ──\n{sep}")
        ans_c = gemini_council_coder.generate(query, system=system_prompt, stream=True)
        print(sep)
        # Prüfe ob die Antwort gültig ist (kein API-Fehler)
        if not _is_valid_answer(ans_c):
            print(f"[WARN] Gemini-Flash-Antwort ungültig (API-Fehler wie 503) — werde ignoriert")
            ans_c = None

    # D — mistral-large (optional)
    ans_d = None
    if mistral_council_coder and mistral_council_coder.usable:
        print(f"\n── Antwort D ({mistral_council_coder.model}) ──\n{sep}")
        ans_d = mistral_council_coder.generate(query, system=system_prompt, stream=True)
        print(sep)
        # Prüfe ob die Antwort gültig ist (kein API-Fehler)
        if not _is_valid_answer(ans_d):
            print(f"[WARN] Mistral-Antwort ungültig (API-Fehler) — werde ignoriert")
            ans_d = None

    # Synthese — stärkeres Modell vergleicht A, B, C, D
    if not (synth_coder and synth_coder.usable):
        # Falls Synthese-Modell nicht nutzbar, alle gültigen Antworten zusammenfassen
        print("[WARN] Synthese-Modell nicht nutzbar — alle Antworten stehen oben nebeneinander.")
        result = [a for a in [ans_a, ans_b, ans_c, ans_d] if _is_valid_answer(a)]
        return "\n\n---\n\n".join(result) if result else ans_a

    # Build synth prompt nur mit gültigen Antworten
    answers = []
    if _is_valid_answer(ans_a):
        answers.append(f"ANTWORT A (lokales Modell):\n{ans_a}")
    if _is_valid_answer(ans_b):
        answers.append(f"ANTWORT B (Haiku):\n{ans_b}")
    if _is_valid_answer(ans_c):
        answers.append(f"ANTWORT C (Gemini-Flash):\n{ans_c}")
    if _is_valid_answer(ans_d):
        answers.append(f"ANTWORT D (Mistral):\n{ans_d}")
    
    # Wenn weniger als 2 gültige Antworten, keine Synthese möglich
    if len(answers) < 2:
        print(f"[WARN] Nur {len(answers)} gültige Antwort(en) für Synthese — Synthese übersprungen")
        # Extrahiere nur die Antwort-Inhalte (ohne "ANTWORT X:"-Prefix)
        valid_answers = []
        for a in [ans_a, ans_b, ans_c, ans_d]:
            if _is_valid_answer(a):
                valid_answers.append(a)
        return "\n\n---\n\n".join(valid_answers)

    synth_prompt = (
        f"FRAGE:\n{query}\n\n"
        + "\n\n".join(answers) + "\n\n"
        "Vergleiche alle Antworten. Antworte auf Deutsch in genau zwei Abschnitten:\n"
        "KONSENS: worauf sich alle einigen (das Verlässliche), knapp.\n"
        "UNTERSCHIEDE: jeder Punkt, an dem sie divergieren — konkret benannt, mit ehrlicher "
        "Einschätzung, welche Antwort plausibler ist und warum (oder dass es offen bleibt). "
        "Glätte den Dissens NICHT weg — die Unterschiede sind das Wichtigste."
    )
    synth_system = ("Du bist ein präziser Schiedsrichter mehrerer Modell-Antworten. Ehrlich, "
                    "knapp, kein Geschwafel; Unsicherheit offen markieren.")
    print(f"\n── 🜂 Synthese ({synth_coder.model}) ──\n{sep}")
    synth = synth_coder.generate(synth_prompt, system=synth_system, stream=True)
    print(sep)
    return synth or "\n\n---\n\n".join(a for a in [ans_a, ans_b, ans_c, ans_d] if _is_valid_answer(a))


# ==== GEMINI-FLASH + MISTRAL INTEGRATION - END ====


# =============================================================================
# CLI Interface
# =============================================================================

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    clear_screen()
    print("=" * 60)
    print("CODE-VAULT TERMINAL")
    print("=" * 60)
    print("[q] beenden | [l] logs | [s] state | [r] review | [c] clear | [w] workflow")
    print("[Agent-Modus] search_vault · read_file · query_ossifikat · verify · done")
    # ==== GEMINI-FLASH + MISTRAL INTEGRATION - BEGIN ====
    print("[??h] Rat: lokal + Haiku + Sonnet | [??g] Rat: lokal + Gemini-Flash + Pro")
    print("[??m] Rat: lokal + Mistral | [??a] Rat: ALLE 4 (lokal + Haiku + Gemini + Mistral)")
    # RÜCKGÄNGIG MACHEN: Ersetze durch die alte Version ohne Mistral.
    # ==== GEMINI-FLASH + MISTRAL INTEGRATION - END ====
    print("-" * 60)


def print_state(retriever):
    """Zeige aktuellen Hardware-State."""
    state = retriever.protocol.get_hardware_state()
    lorenz = retriever.protocol.get_lorenz_params()
    
    print("\n" + "=" * 40)
    print("HARDWARE STATE")
    print("=" * 40)
    print(f"Lorenz: x1={state['x1']:.2f} y1={state['y1']:.2f} z1={state['z1']:.2f} w1={state['w1']:.2f}")
    print(f"        x2={state['x2']:.2f} y2={state['y2']:.2f}")
    print(f"Thermo: entropy={state['entropy']:.2f} temp={state['temperature']:.2f} cortex={state['cortex_bias']:.2f}")
    print(f"Params: rho={lorenz['rho']:.2f} sigma={lorenz['sigma']:.2f} beta={lorenz['beta']:.2f}")
    print(f"        reason={lorenz['reason']:.2f} cycle={lorenz['cycle']}")
    print("=" * 40 + "\n")


def print_logs():
    """Zeige letzte Log-Einträge."""
    if not os.path.exists(LOG_FILE):
        print("\n[INFO] Keine Logs vorhanden")
        return
    
    print("\n" + "=" * 40)
    print("LOGS (letzte 10)")
    print("=" * 40)
    
    with open(LOG_FILE, "r") as f:
        lines = f.readlines()
    
    for line in lines[-10:]:
        entry = json.loads(line)
        if entry["type"] == "triplet":
            print(f"[{time.strftime('%H:%M:%S', time.localtime(entry['timestamp']))}] QUERY: {entry['query'][:50]}...")
            print(f"  -> Context: {entry['context_count']} docs, Response: {entry['response_len']} chars")
        elif entry["type"] == "hardware_state":
            print(f"[{time.strftime('%H:%M:%S', time.localtime(entry['timestamp']))}] HARDWARE: entropy={entry['thermodynamics']['entropy']:.2f} temp={entry['thermodynamics']['temperature']:.2f}")
    
    print("=" * 40 + "\n")


def review_triples(retriever):
    """Review ossifikat staging with TerminalAdapter."""
    if not ADAPTERS_AVAILABLE or not retriever.terminal_adapter:
        print("[WARN] Ossifikat TerminalAdapter nicht verfügbar")
        return

    try:
        from ossifikat.cli import review_staging
        print("[REVIEW] Öffne ossifikat Staging-Review...")
        review_staging()
    except ImportError:
        print("[WARN] ossifikat nicht installiert: pip install ossifikat")
    except Exception as e:
        print(f"[ERR] Review fehlgeschlagen: {e}")


def research_mode(retriever):
    """Deep multi-retrieval mode for exploration without workflow start."""
    print("\n" + "=" * 60)
    print("RESEARCH MODE - Tiefe Vault-Exploration")
    print("=" * 60)

    query = input("\n🔍 Research-Query eingeben: ").strip()
    if not query:
        print("❌ Keine Query eingegeben.")
        return

    # DE->EN Pre-Retrieval Hook (deutsche Queries -> englische Suche)
    search_query = query
    try:
        from query_translator import QueryTranslator
        translator = QueryTranslator()
        tx = translator.translate(query)
        if not tx["skipped"] and tx["translated"] != tx["original"]:
            search_query = tx["translated"]
            cache_marker = "📦" if tx["cache_hit"] else "🌐"
            print(f"  {cache_marker} Translated: \"{search_query}\"  ({tx['duration_ms']:.0f}ms)")
    except Exception as e:
        print(f"[WARN] Translation skipped: {e}")

    # Multi-retrieval: Haupt-Query + Varianten (auf der englischen Fassung)
    queries = [
        search_query,
        f"how {search_query}",
        f"implementation {search_query}",
    ]

    all_docs = []
    for q in queries:
        try:
            docs, _, _ = retriever.search(q, k=10)
            all_docs.extend(docs)
        except Exception as e:
            print(f"[WARN] Retrieval für '{q}' fehlgeschlagen: {e}")

    # Deduplicate und sortieren nach distance
    seen_ids = set()
    unique_docs = []
    for doc in sorted(all_docs, key=lambda d: d.get("distance", 999)):
        doc_id = doc.get("id")
        if doc_id not in seen_ids:
            seen_ids.add(doc_id)
            unique_docs.append(doc)

    if not unique_docs:
        print("[NO HITS] Keine Dokumente gefunden")
        return

    print(f"\n[OK] Gefunden: {len(unique_docs)} einzigartige Dokumente\n")

    for i, doc in enumerate(unique_docs[:15], 1):
        title = doc.get("title", "unknown")
        distance = doc.get("distance", 0)
        content = doc.get("content", "")[:800]

        print(f"[{i}] {title}")
        print(f"    Distance: {distance:.2f}")
        print(f"    Content: {content}")
        print("    " + "-" * 56)

    # Optionale Babel-Synthese (Feynman/Science) ueber die Top-Docs
    print()
    synth_choice = input("📚 Synthese-Modus? [f]eynman / [s]cience / [Enter]=keine: ").strip().lower()
    if synth_choice in ("f", "feynman", "s", "science"):
        mode = "feynman" if synth_choice.startswith("f") else "science"
        try:
            from babel_synthesizer import BabelSynthesizer
            synth = BabelSynthesizer(default_mode=mode)
            print(f"\n[BABEL] Synthese laeuft (mode={mode}, model={synth.qwen.model})...")
            result = synth.synthesize(query, unique_docs)
            print("\n" + "=" * 60)
            print(f"BABEL-SYNTHESE ({result['mode'].upper()})")
            print("=" * 60)
            print(result["analysis"])
            print()
            print(f"[Quellen: {result['source_stats']} | {result['duration_s']}s]")
        except ImportError as e:
            print(f"[WARN] babel_synthesizer nicht ladbar: {e}")
        except Exception as e:
            print(f"[ERR] Babel-Synthese fehlgeschlagen: {e}")


def start_workflow():
    """Start the 5-phase development workflow."""
    if not WORKFLOW_AVAILABLE:
        print("[WARN] Workflow Agent nicht verfügbar. Installiere workflow_agent.py")
        return

    print("\n" + "=" * 60)
    print("VIBELIKE WORKFLOW AGENT - 5-Phasen Development")
    print("=" * 60)

    task = input("\n📝 Aufgabe eingeben: ").strip()

    if not task:
        print("❌ Keine Aufgabe eingegeben.")
        return

    try:
        agent = WorkflowAgent()
        workflow = agent.run_workflow(task)

        # Show workflow summary
        print("\n" + "=" * 60)
        print("✅ WORKFLOW SUMMARY")
        print("=" * 60)
        phase_labels = {
            "briefing":           "1.  BRIEFING            ",
            "planning_strategy":  "2a. PLANNING-STRATEGIE  ",
            "planning_detailed":  "2b. PLANNING-DETAIL     ",
            "execution":          "3.  EXECUTION           ",
            "verification":       "4.  VERIFICATION        ",
            "failure_analysis":   "4b. FAILURE-ANALYSIS    ",
            "commit":             "5.  COMMIT              ",
            "report":             "R.  ANALYSIS-REPORT     ",
        }
        # Erfolgs-Indikatoren je Phase: approved (User-Gate), tests_passed,
        # committed, oder completed (für ANALYSIS-Phasen ohne Gate).
        success_keys = ("approved", "tests_passed", "committed", "completed")
        if workflow.get("iteration"):
            print(f"Iteration: {workflow['iteration']} (parent: {workflow.get('parent_id')})")
        for phase_name, phase_data in workflow.get("phases", {}).items():
            if phase_data:
                ok = any(phase_data.get(k) for k in success_keys)
                status = "✓" if ok else "✗"
                label = phase_labels.get(phase_name, phase_name.upper())
                print(f"{status} {label} {phase_data.get('timestamp', 'N/A')}")
        if workflow.get("phases", {}).get("commit", {}).get("steps"):
            print("\nCommits:")
            for s in workflow["phases"]["commit"]["steps"]:
                if "hash" in s:
                    print(f"  {s['hash']}  {s['title']}")

    except Exception as e:
        print(f"\n[ERR] Workflow fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print_header()

    # Initialisierung
    print("[INIT] Lade Vaults...")
    retriever = CodeRetriever()
    coder = QwenCoder(model=KNOWLEDGE_ANSWER_MODEL)  # Generalist, nicht der Coder
    history = []  # gehaltener Gesprächskontext: [(frage, antwort), …] für Folgefragen
    council_coder = None  # lazy: Frontier-Modelle erst beim ersten '??' (Rat-Modus)
    synth_coder = None
    _agent_loop = [None]  # lazy: Agent-Loop erst beim ersten Query (Liste für mutability)
    # Warmen Retriever in VaultTool injizieren → kein Doppel-Load beim ersten Agent-Step
    try:
        from agent_tools import ToolsFactory
        ToolsFactory.inject_retriever(retriever)
    except Exception:
        pass
    # ==== GEMINI-FLASH INTEGRATION - BEGIN ====
    gemini_council_coder = None  # lazy: Gemini-Modelle erst beim ersten '??g' oder '??a'
    gemini_synth_coder = None    # lazy: Gemini-Synthese erst beim ersten '??g' oder '??a'
    # RÜCKGÄNGIG MACHEN: Lösche diese beiden Zeilen und alle Referenzen darauf.
    # ==== GEMINI-FLASH INTEGRATION - END ====
    # ==== MISTRAL INTEGRATION - BEGIN ====
    mistral_council_coder = None  # lazy: Mistral-Modelle erst beim ersten '??m' oder '??a'
    mistral_synth_coder = None    # lazy: Mistral-Synthese erst beim ersten '??m' oder '??a'
    # RÜCKGÄNGIG MACHEN: Lösche diese beiden Zeilen und alle Referenzen darauf.
    # ==== MISTRAL INTEGRATION - END ====
    print()

    while True:
        try:
            query = input("\n> ").strip()
            
            if not query:
                continue
            
            if query.lower() == "q":
                break
            
            if query.lower() == "l":
                print_logs()
                continue
            
            if query.lower() == "s":
                print_state(retriever)
                continue
            
            if query.lower() == "c":
                clear_screen()
                print_header()
                history.clear()  # Gesprächskontext zurücksetzen
                print("[OK] Gesprächskontext geleert")
                continue

            if query.lower() == "r":
                review_triples(retriever)
                continue

            if query.lower() == "w":
                start_workflow()
                continue

            if query.upper() == "R":
                research_mode(retriever)
                continue

            # Workflow via "briefing:" prefix
            if query.startswith("briefing:"):
                task = query[9:].strip()
                if task:
                    try:
                        agent = WorkflowAgent()
                        workflow = agent.run_workflow(task)
                    except Exception as e:
                        print(f"\n[ERR] Workflow fehlgeschlagen: {e}")
                else:
                    print("[ERR] Keine Aufgabe nach 'briefing:' eingegeben")
                continue

            # ==== GEMINI-FLASH + MISTRAL INTEGRATION - BEGIN ====
            # Rat-Modus: Präfixe für verschiedene Modi
            # ??h = lokal + Haiku (Claude) + Sonnet-Synthese
            # ??g = lokal + gemini-2.5-flash + gemini-2.5-pro-Synthese
            # ??m = lokal + mistral-large + mistral-large-Synthese
            # ??a = ALL-IN: lokal + Haiku + gemini-2.5-flash + mistral-large + Synthese
            # ?? = Backward-Kompat: wie ??h (lokal + Haiku)
            council_h = query.startswith("??h")
            council_g = query.startswith("??g")
            council_m = False  # Mistral deaktiviert (Abo gekündigt)
            council_a = query.startswith("??a")
            council = query.startswith("??")
            
            # Bestimme den Modus und bereinige Query
            mode = None
            if council_a:
                mode = "all"
                query = query[3:].strip()
            elif council_g:
                mode = "gemini"
                query = query[3:].strip()
            elif council_h:
                mode = "haiku"
                query = query[3:].strip()
            elif council:
                mode = "haiku"  # Backward-Kompat: ?? = ??h
                query = query[2:].strip()
            
            if council and not query:
                print("[ERR] Keine Frage nach dem Rat-Präfix")
                continue
            # ==== GEMINI-FLASH + MISTRAL INTEGRATION - END ====
            # RÜCKGÄNGIG MACHEN: Ersetze die 4 council_*-Zeilen durch die alten 2 Zeilen (council_h, council_g) und lösche die Mistral-Referenzen.

            # Suche in beiden Vaults (Code + Wissen), fair gemerged
            print("[SEARCH] Suche in den Vaults...")
            context, _, _ = retriever.search(query, k=6)

            if context:
                print(f"[OK] Gefunden: {len(context)} Dokumente")
                for i, doc in enumerate(context):
                    title = doc.get("title", "Unbekannt")[:40]
                    print(f"  [{i+1}] {title}... (Dist: {doc['distance']:.1f})")
                # (Kein opakes query/response-Hash-Staging mehr — war Lärm. Meaningful
                #  Kandidaten kommen künftig über den QwenExtractor.)
            else:
                print("[WARN] Keine Dokumente gefunden")
            
            # Ehrlichkeits-Signal: schwache Quellen-Deckung sichtbar machen
            g = assess_grounding(context)
            if g["banner"]:
                print(g["banner"])

            # System-Prompt bauen (Schwäche-Direktive ist bei Bedarf vorangestellt)
            system_prompt = build_system_prompt(context)
            
            # Gehaltener Gesprächskontext für Folgefragen — bewusst KURZ (letzte 2 Turns,
            # gekürzt): zu viel Historie erstickt das kleine Modell (Klein-Modell-Decke).
            sys_full = system_prompt
            if history:
                convo = "\n\n".join(
                    f"FRÜHER gefragt: {q}\nDeine Antwort (gekürzt): {a[:400]}"
                    for q, a in history[-2:]
                )
                sys_full += "\n\nBISHERIGES GESPRÄCH (Kontext für Folgefragen, nicht wiederholen):\n" + convo
                print(f"[💬 {min(len(history),2)} Turn(s) Kontext]")

            # Generieren — Rat-Modus oder normal (nur lokal)
            # ==== GEMINI-FLASH + MISTRAL INTEGRATION - BEGIN ====
            if mode == "gemini":
                if gemini_council_coder is None:
                    print("[RAT] Schalte Gemini-Modelle zu…")
                    gemini_council_coder = GeminiCoder(model=GEMINI_COUNCIL_MODEL)
                    gemini_synth_coder = GeminiCoder(model=GEMINI_SYNTH_MODEL)
                response = run_council_gemini(query, sys_full, coder, gemini_council_coder, gemini_synth_coder)
            elif mode == "all":
                if council_coder is None:
                    print("[RAT] Schalte Frontier-Modelle zu…")
                    council_coder = ClaudeCoder(model=COUNCIL_MODEL)
                    synth_coder = ClaudeCoder(model=SYNTH_MODEL)
                if gemini_council_coder is None:
                    print("[RAT] Schalte Gemini-Modelle zu…")
                    gemini_council_coder = GeminiCoder(model=GEMINI_COUNCIL_MODEL)
                # Für ALL-Modus: Synthese mit verfügbarem Modell (Sonnet oder gemini-2.5-pro)
                if synth_coder and synth_coder.usable:
                    pass  # Sonnet bereit
                elif gemini_synth_coder is not None and gemini_synth_coder.usable:
                    synth_coder = gemini_synth_coder  # gemini-2.5-pro
                else:
                    if synth_coder is None:
                        synth_coder = ClaudeCoder(model=SYNTH_MODEL)
                response = run_council_all(query, sys_full, coder, council_coder, gemini_council_coder, synth_coder, None, None)
            elif mode == "haiku":
                if council_coder is None:
                    print("[RAT] Schalte Frontier-Modelle zu…")
                    council_coder = ClaudeCoder(model=COUNCIL_MODEL)
                    synth_coder = ClaudeCoder(model=SYNTH_MODEL)
                response = run_council(query, sys_full, coder, council_coder, synth_coder)
            else:
                # Agent-Mode: Single-Agent (qwen2.5-coder:1.5b)
                # P3 (Multi-Agent) disabled due to model-routing complexity
                try:
                    import asyncio
                    from agent_loop import AgentLoop

                    if _agent_loop[0] is None:
                        _agent_loop[0] = AgentLoop(model_name=KNOWLEDGE_ANSWER_MODEL)
                    response = await _agent_loop[0].step(query)

                    print("\n" + "-" * 60)
                    print(response or "[kein Output]")
                    print("-" * 60)
                except Exception as e:
                    # Fallback: direkter Flow
                    print(f"[WARN] Agent-Loop Fehler ({e}) → direkter Flow")
                    print(f"[GEN] {KNOWLEDGE_ANSWER_MODEL}...\n" + "-" * 60)
                    response = coder.generate(query, system=sys_full, stream=True)
                    print("-" * 60)

            # Historie pflegen (<think> raus, gekappt) + Triplet loggen
            clean = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            history.append((query, clean))
            if len(history) > 6:
                del history[:-6]
            retriever.hw_logger.log_triplet(query, context, response)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n[ERR] {e}")
            import traceback
            traceback.print_exc()
    
    print("\n[BYE] Auf Wiedersehen")
    retriever.protocol.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
