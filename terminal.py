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

# Import fallback: Try package-based imports (if installed), fall back to sys.path for script execution
try:
    from vibelike.task_classifier import TaskClassifier, confirm_classification
    from vibelike.framework.quelibrium.core.protocol import Protocol
    from vibelike.framework.quelibrium.core.paths import CODE_VAULT_FILE, CODE_CACHE_FILE
    from vibelike.framework.quelibrium.intelligence.retrieval import ChaosRetrieval, RiemannianWarp, ThompsonSampler
    from vibelike.framework.quelibrium.intelligence.resonance import ResonanceField
except ImportError:
    # Fallback: Add ROOT to path for script execution
    sys.path.insert(0, ROOT)
    from task_classifier import TaskClassifier, confirm_classification
    from framework.quelibrium.core.protocol import Protocol
    from framework.quelibrium.core.paths import CODE_VAULT_FILE, CODE_CACHE_FILE
    from framework.quelibrium.intelligence.retrieval import ChaosRetrieval, RiemannianWarp, ThompsonSampler
    from framework.quelibrium.intelligence.resonance import ResonanceField

# Import UI helpers (extracted to separate module)
try:
    from terminal_ui import clear_screen, print_header, print_state, print_logs, review_triples, research_mode
except ImportError:
    # Fallback: Define minimal stubs if terminal_ui not available
    def clear_screen(): os.system("cls" if os.name == "nt" else "clear")
    def print_header(): print("CODE-VAULT TERMINAL")
    def print_state(r): print("State info not available")
    def print_logs(): print("Logs not available")
    def review_triples(r): print("Review not available")
    def research_mode(r): print("Research mode not available")


# =============================================================================
# Konfiguration (all settings now centralized in config.py via Pydantic)
# =============================================================================

from config import settings

# Model configuration (from config.py)
MODEL = settings.coder_model  # "deepseek-coder:6.7b-instruct"
VALIDATOR_MODEL = settings.validator_model
ANALYSIS_MODEL = settings.analysis_model  # "claude-haiku-4-5-20251001"
CODEGEN_BACKEND = settings.codegen_backend
CODEGEN_MODEL = settings.codegen_model
COUNCIL_MODEL = settings.council_model
SYNTH_MODEL = settings.synth_model
GEMINI_COUNCIL_MODEL = settings.gemini_council_model
GEMINI_SYNTH_MODEL = settings.gemini_synth_model
MISTRAL_COUNCIL_MODEL = settings.mistral_council_model
MISTRAL_SYNTH_MODEL = settings.mistral_synth_model

# Vault configuration
# Zu str casten: die vendored Quelibrium-Engine (Vault.load) ruft .endswith() auf
# dem Pfad → ein Path-Objekt (aus den Pydantic-settings) crasht dort. None bleibt None.
KNOWLEDGE_VAULT_FILE = str(settings.knowledge_vault_file) if settings.knowledge_vault_file else None
KNOWLEDGE_CACHE_FILE = str(settings.knowledge_cache_file) if settings.knowledge_cache_file else None
DUAL_VAULT = settings.dual_vault
QUERY_DECOMPOSE = settings.query_decompose
KNOWLEDGE_ANSWER_MODEL = settings.knowledge_answer_model

# Ossifikat & facts
OSSIFIKAT_DB = settings.ossifikat_db
GROUND_ON_FACTS = settings.ground_on_facts

# Architecture
VIBELIKE_ARCH = settings.arch
POWER_USER = settings.power_user

# API endpoints
OLLAMA_URL = settings.ollama_url
LOG_FILE = settings.log_file

# Note: Log directories are now created by config.py in model_post_init()

# Initialize terminal_ui with runtime config
import terminal_ui
terminal_ui.POWER_USER = POWER_USER
terminal_ui.LOG_FILE = LOG_FILE
terminal_ui.ADAPTERS_AVAILABLE = ADAPTERS_AVAILABLE


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
        from vibelike.crypto import stable_hash_sha256, stable_hash_int
        
        # Kontext als binärnahe Repräsentation (mit stabilen Hashes)
        context_bin = [{
            "id": c.get("id"),
            "distance": c.get("distance", 0),
            "source": c.get("source", ""),
            "content_hash": stable_hash_int(str(c.get("content", "") or ""), modulo=2**32),  # NEW: stable
            "content_hash_sha256": stable_hash_sha256(str(c.get("content", "") or ""), hex_length=16),
            "content_len": len(str(c.get("content", "") or ""))
        } for c in context]
        
        entry = {
            "timestamp": time.time(),
            "type": "triplet",
            "query": query,
            "query_hash": stable_hash_int(query, modulo=2**32),  # NEW: stable instead of hash()
            "query_hash_sha256": stable_hash_sha256(query, hex_length=16),
            "context": context_bin,
            "context_count": len(context),
            "response": response,
            "response_len": len(response),
            "response_hash": stable_hash_int(response, modulo=2**32),  # NEW: stable
            "response_hash_sha256": stable_hash_sha256(response, hex_length=16),
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
    
    def search(self, query: str, k: int = 10, source_boost: dict = None, mode: str = "balanced") -> tuple:
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

        mode: "balanced" (default) | "code_focused" | "conceptual". Steuert den
        source_boost dynamisch, um die Suche für den jeweiligen Anwendungsfall
        zu optimieren.

        Remote-Modus (self.remote_url gesetzt): delegiert die Suche an den warmen
        Retrieval-Daemon; lokal wird kein Vault/Encoder geladen.
        """
        # Dynamische Anpassung des source_boost basierend auf dem Modus
        if mode == "code_focused":
            source_boost = {"PROJEKT_SELFCODE": 0.2}
            print("[🔎 Retrieval-Modus: code_focused]")
        elif mode == "conceptual":
            source_boost = {"PROJEKT_SELFCODE": 1.5}
            print("[🔎 Retrieval-Modus: conceptual]")

        if self.remote_url:
            return self._remote_search(query, k, source_boost, mode)
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

    def intensive_search(self, query: str, vault_type: str = "hybrid", k: int = 10,
                        max_hops: int = 1, max_docs: int = 30, rerank: bool = True,
                        qwen_coder=None) -> tuple:
        """
        Intensive Retrieval: Over-fetch → Rerank → Optional Multi-Hop → Full Files.
        
        Args:
            query: Suchquery
            vault_type: "code" | "knowledge" | "hybrid" | "none" (aus vault_router)
            k: Finale Anzahl Docs (wird zu Top-k nach Reranking)
            max_hops: 1=Single Query (default), 2-3=Multi-Hop Follow-up Queries
            max_docs: Maximum Over-fetch (default 30, dann rerankt zu k)
            rerank: deepseek-Reranking via qwen_coder (optional, braucht qwen_coder)
            qwen_coder: QwenCoder instance für Reranking (optional)
        
        Returns:
            (docs, state_before, state_after) wie .search()
        """
        if vault_type == "none":
            print("[⚠️  intensive_search] vault_type=none → keine Retrieval")
            return [], None, None
        
        state_before = self.hw_logger.log_state(query, "intensive_search_start")
        fetch_n = max_docs if max_docs > k else k * 3
        
        print(f"[🔍 intensive_search] query='{query[:50]}...' vault={vault_type} "
              f"fetch_n={fetch_n} hops={max_hops}")
        
        try:
            # STEP 1: Over-fetch initial results
            query_vec = self._embed(query)
            initial_docs = self._multi_search(query_vec, fetch_n)
            
            if not initial_docs:
                print(f"[⚠️  intensive_search] Keine Docs gefunden für Query")
                state_after = self.hw_logger.log_state(query, "intensive_search_end")
                return [], state_before, state_after
            
            print(f"  → Schritt 1: Over-fetch {len(initial_docs)} Docs")
            
            # STEP 2: Rerank via deepseek (optional)
            if rerank and qwen_coder and len(initial_docs) > k:
                initial_docs = self._rerank_with_deepseek(query, initial_docs, k, qwen_coder)
                print(f"  → Schritt 2: Reranked zu Top {k}")
            else:
                initial_docs = initial_docs[:k]
            
            # STEP 3: Multi-Hop (optional)
            all_docs = dict({(d.get("id"), d.get("vault")): d for d in initial_docs})
            if max_hops > 1 and qwen_coder:
                for hop in range(2, max_hops + 1):
                    followup_queries = self._extract_followup_queries(initial_docs[:3], query)
                    if not followup_queries:
                        break
                    print(f"  → Schritt {hop+1}: Follow-up Queries: {followup_queries[:2]}")
                    
                    for fq in followup_queries[:2]:  # Max 2 Follow-ups pro Hop
                        fq_vec = self._embed(fq)
                        hop_docs = self._multi_search(fq_vec, fetch_n // 2)
                        for doc in hop_docs:
                            key = (doc.get("id"), doc.get("vault"))
                            if key not in all_docs:
                                all_docs[key] = doc
                    
                    initial_docs = list(all_docs.values())[:k]
            
            # STEP 4: Full Files für Top-3, Skeletons für Rest
            result_docs = self._enrich_with_full_content(initial_docs[:k])
            
            state_after = self.hw_logger.log_state(query, "intensive_search_end")
            return result_docs, state_before, state_after
            
        except Exception as e:
            print(f"[ERR] intensive_search fehlgeschlagen: {e}")
            state_after = self.hw_logger.log_state(query, "intensive_search_error")
            return [], state_before, state_after

    def _rerank_with_deepseek(self, query: str, docs: list, k: int, qwen_coder) -> list:
        """
        Reranke Top-Docs via deepseek (Grammar-Constrained).
        Gibt Top-k Docs in neuer Reihenfolge zurück.
        """
        if not docs or not qwen_coder:
            return docs[:k]
        
        # Baue Doc-Listing
        doc_list = "\n".join(
            f"{i+1}. [{d.get('source', '?')}] {d.get('title', 'untitled')[:60]}"
            for i, d in enumerate(docs[:15])
        )
        
        prompt = f"""Aufgabe: {query}

Verfügbare Dokumentationen (nach initialer Suche):
{doc_list}

Welche {min(k, len(docs))} Docs sind für diese Aufgabe AM relevantesten?
Antworte als JSON: {{"ranked_indices": [0, 2, 1, ...]}} (in Reihenfolge der Relevanz, 0-basiert)"""
        
        try:
            raw = qwen_coder.generate(prompt, temperature=0.0, stream=False)
            m = re.search(r'\[.*?\]', raw)
            if m:
                indices = json.loads(m.group(0))
                ranked = [docs[i] for i in indices if i < len(docs)]
                if ranked:
                    print(f"    ✓ Reranked via deepseek ({len(ranked)} selected)")
                    return ranked
        except Exception as e:
            print(f"    ⚠️  Rerank fehlgeschlagen: {e}")
        
        return docs[:k]

    def _extract_followup_queries(self, top_docs: list, original_query: str, max_queries: int = 2) -> list:
        """
        Extrahiere Folge-Fragen aus Top-Docs (Imports, Funktionsaufrufe, Typen, etc.).
        Einfache Heuristik: Scan nach import/from, call patterns, type hints.
        """
        followups = []
        for doc in top_docs[:3]:
            content = doc.get("content", "")
            # Heuristic: Imports extrahieren
            imports = re.findall(r'from ([\w.]+) import|import ([\w.]+)', content)
            for imp in imports[:1]:
                mod = imp[0] or imp[1]
                if mod and len(mod) > 2:
                    followups.append(f"How does {mod} module work?")
            
            # Funktionsaufrufe
            calls = re.findall(r'\b([a-z_]\w+)\s*\(', content)
            if calls:
                followups.append(f"What does {calls[0]}() function do?")
        
        return followups[:max_queries]

    def _enrich_with_full_content(self, docs: list, full_for_top: int = 3) -> list:
        """
        Enriche Docs mit vollem Inhalt (Top-3) oder Skeleton (Rest).
        """
        result = []
        for i, doc in enumerate(docs):
            if i < full_for_top:
                # Full content (schon vorhanden)
                result.append(doc)
            else:
                # Skeleton: nur titel + first 500 chars
                doc_copy = dict(doc)
                content = doc.get("content", "")
                if len(content) > 500:
                    doc_copy["content"] = content[:500] + "\n... [gekürzt]"
                doc_copy["is_skeleton"] = True
                result.append(doc_copy)
        
        return result

    def _remote_search(self, query: str, k: int, source_boost: dict = None, mode: str = "balanced") -> tuple:
        """Suche über den warmen Retrieval-Daemon. hw_logger bleibt lokal (Code-Vault)
        für Telemetrie/Triplet-Log. Daemon nicht erreichbar ⇒ leeres Ergebnis (kein
        40s-Fallback-Load)."""
        state_before = self.hw_logger.log_state(query, "search_start")
        docs = []
        try:
            payload = {"query": query, "k": k, "mode": mode}
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
                response = self.session.post(OLLAMA_URL, json=payload, timeout=60)
                if response.status_code == 200:
                    return response.json().get("response", "")
                return f"[ERR] HTTP {response.status_code}"

            # Streaming: zeilenweise JSON-Chunks parsen, jedes "response"-Feld printen
            chunks = []
            with self.session.post(OLLAMA_URL, json=payload, stream=True, timeout=60) as resp:
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
                 stream: bool = False, fmt=None, cache_prefix: str = None,
                 raise_on_quota: bool = False) -> str:
        """Generiere via Claude-API. stream=True schreibt Tokens live nach stdout;
        Rückgabe ist in beiden Fällen der volle Antworttext. Fehler → '[ERR] ...'.

        fmt: nur für Signatur-Kompat mit QwenCoder (Ollama-Schema) — hier ignoriert.
        cache_prefix: stabiler Präfix → gecachter system-Block (cache_control ephemeral).
        Über mehrere Calls mit identischem Präfix (z.B. Codegen-Retries) wird der Block
        nur einmal berechnet → cache_read statt Neuberechnung.
        raise_on_quota: wenn True, werden Quota/Overload/Timeout-Fehler als typisierte
        ModelError-Exception GEWORFEN statt in '[ERR] ...' verschluckt — so kann ein
        FallbackCoder auf lokal umschalten. Default False → altes Verhalten (kompatibel).
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
            if raise_on_quota:
                from model_fallback import classify_model_exception
                typed = classify_model_exception(e)
                if typed is not None:
                    raise typed from e
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


def analyze_deep(query: str, context: list, coder) -> str:
    """DEEP ANALYSIS Phase: 30 Docs (20 Top + 10 Random) mit Widerspruch-Analyse.

    Input: Top 30 Docs aus Vault-Suche
    Output: Tiefe Analyse mit Widersprüchen + Synthesized Knowledge

    Basiert auf BabelFeynman.analyze_spectral_field() aus AI neu/babel_deep.py
    """
    if not context or len(context) < 1:
        return ""

    # === 20 TOP + 10 RANDOM STRATEGIE ===
    # Filter: nur echte Vault-Docs (nicht verbürgt)
    vault_docs = [d for d in context if d.get("vault") != "verbürgt"]

    if len(vault_docs) < 1:
        return ""

    # Top 20
    top_20 = vault_docs[:20]

    # Random 10 aus dem Rest (für Diversity + Hidden Patterns)
    import random
    remaining = vault_docs[20:]
    random_10 = random.sample(remaining, min(10, len(remaining)))

    used_docs = top_20 + random_10  # 20-30 Docs total

    print(f"[ANALYZE-DEEP] 20 Top + {len(random_10)} Random = {len(used_docs)} Docs")

    # === CONTEXT BLOCK FÜR LLM ===
    context_parts = []
    if used_docs:
        context_parts.append("=== WISSENSBASIS ===\n")
        for i, doc in enumerate(used_docs, 1):
            title = doc.get('title', 'Unbekannt')
            content = doc.get('content', '')[:600]  # Mehr Context
            source = doc.get('source', '?')
            dist = doc.get('distance', 0.99)

            # Top 20 vs Random 10 Markierung
            tag = "[TOP]" if i <= 20 else "[RANDOM]"
            context_parts.append(f"QUELLE {i} {tag} (d={dist:.2f}, {source}): {title}")
            context_parts.append(f"{content}\n")

    full_context = "\n".join(context_parts)
    if not full_context:
        full_context = "KEINE DATEN."

    # === DEEP ANALYSIS PROMPT (wie BabelFeynman) ===
    analysis_prompt = f"""DU BIST: Ein wissenschaftlicher Analytiker der tief in spezifische Aspekte eintaucht.
FRAGE: "{query}"

DEINE QUELLEN ({len(used_docs)} Dokumente):
{full_context}

AUFGABE: Erstelle eine TIEFE, ASPEKT-FOKUSSIERTE Analyse mit Widerspruch-Erkennung.

STRUKTUR:

**1. KERNKONZEPT** (Präzise Definition)
- Was ist das zentrale Konzept? Definiere mit Fachbegriffen.

**2. WISSENSCHAFTLICHE PERSPEKTIVEN** (Hauptteil)
Analysiere 3-4 spezifische Aspekte aus den Quellen:
• **Kernaspekt**: Was sind die Basics? (Quellen X, Y...)
• **Kontroversen/Widersprüche**: Wo widersprechen sich die Quellen?
• **Neue Erkenntnisse**: Was zeigen die Random-Quellen? Überraschungen?
• **Verbindungen**: Wie hängen die Aspekte zusammen?

Gehe TIEF: Nenne spezifische Werte, Methoden, Ergebnisse aus den Quellen.

**3. SYNTHESIS & TIEFE EINSICHT**
- Verbinde die Aspekte zu einem Gesamtbild.
- Nenne ein faszinierendes Detail (Deep Dive).
- Ausblick: Wohin führt die Forschung?

REGELN:
- Antworte auf DEUTSCH.
- Referenziere Quellen ("Laut Quelle 3...", "Studie X zeigt...").
- Sei ausführlich (ca. 800-1200 Wörter).
- Widersprüche sind NICHT schlecht — sie zeigen Forschungs-Edge!

ANALYSE:"""

    print(f"  🧠 Deep Analysis mit {len(used_docs)} Docs (Claude)...")

    try:
        analysis = coder.generate(
            analysis_prompt,
            system="Du bist ein präziser wissenschaftlicher Analytiker. Antworte auf Deutsch, tiefgründig und mit Quellenreferenzen.",
            stream=False
        )
        print(f"  ✅ Analyse generiert ({len(analysis)} chars)")
        return analysis.strip()
    except Exception as e:
        print(f"  [WARN] Deep Analysis fehlgeschlagen: {e}")
        return ""


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
        body = ("Du bist ein sachkundiger Assistent. Antworte auf Deutsch, knapp und präzise. "
                "Code in Markdown-Blöcken. Wenn unsicher: sag es explizit.")
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

    rules = ("Du bist ein präziser Recherche- und Fachassistent. Antworte auf Deutsch.\n"
             "1. Nutze die VERBÜRGTEN FAKTEN und QUELLEN unten.\n"
             "2. Code in Markdown mit Sprachen-Tag.\n"
             "3. Falls nicht ausreichend: sag das und ergänze vorsichtig.\n"
             "4. Sei knapp und präzise.\n\n"
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
# NOTE: UI helper functions (clear_screen, print_header, print_state, 
#       print_logs, review_triples, research_mode) are now imported from terminal_ui.py
# See: terminal_ui.py for these implementations


def start_workflow():
    """Start the Hybrid Workflow Agent (Auto-Klassifikation: Wissen vs. Coding)."""
    if not WORKFLOW_AVAILABLE:
        print("[WARN] Workflow Agent nicht verfügbar. Installiere workflow_agent.py")
        return

    print("\n" + "=" * 60)
    print("VIBELIKE HYBRID AGENT - Auto-Klassifikation")
    print("(EXPLAIN → Schlank | IMPL/BUG_FIX/REFACTOR → 6-Phasen)")
    print("=" * 60)

    task = input("\n📝 Aufgabe eingeben: ").strip()

    if not task:
        print("❌ Keine Aufgabe eingegeben.")
        return

    try:
        agent = WorkflowAgent()
        workflow = agent.dispatch(task)

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


# TODO: FileTool-Integration für Query-Mode (später: agentic_query() mit Tool-Support)

async def main():
    # UTF-8 Encoding-Fix für Terminal-Input (verhindert UnicodeDecodeError)
    if sys.stdin.encoding != 'utf-8':
        import io
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')

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
            try:
                query = input("\n> ").strip()
            except UnicodeDecodeError:
                print("[ERR] Encoding-Fehler, bitte erneut eingeben")
                continue

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

            if query.upper() == "R":
                research_mode(retriever)
                continue

            # ──── AUTOMATISCHE KLASSIFIKATION + ORCHESTRIERUNG ────
            # Jeder Input wird klassifiziert → Workflow oder Query
            
            # Power-User Präfixe (nur wenn POWER_USER=1)
            explicit_workflow = False
            council = False
            mode = None
            
            if POWER_USER:
                # Workflow via "briefing:" prefix (Power-User nur)
                if query.startswith("briefing:"):
                    explicit_workflow = True
                    query = query[9:].strip()
                    if not query:
                        print("[ERR] Keine Aufgabe nach 'briefing:' eingegeben")
                        continue
                
                # Council/Rat-Modus Präfixe (Power-User nur)
                council_h = query.startswith("??h")
                council_g = query.startswith("??g")
                council_a = query.startswith("??a")
                council = query.startswith("??")
                
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
                    mode = "haiku"
                    query = query[2:].strip()
                
                if council and not query:
                    print("[ERR] Keine Frage nach dem Rat-Präfix")
                    continue
            
            # ─── AUTO-KLASSIFIKATION (wenn nicht explicitly_workflow oder council-mode) ───
            if not explicit_workflow and not council:
                print(f"[CLASSIFY] Analysiere Anfrage...")
                try:
                    if _agent_loop[0] is None:
                        _agent_loop[0] = WorkflowAgent()
                    agent = _agent_loop[0]
                    
                    # Klassifizierung durchführen
                    classification = agent.classifier.classify(query)
                    task_type = classification.get("type", "IMPLEMENTATION")
                    confidence = classification.get("confidence", 0.5)
                    vault_type = classification.get("vault_type", "hybrid")
                    
                    print(f"[CLASSIFY] Typ: {task_type} (Conf: {confidence:.0%}) | Vault: {vault_type}")
                    
                    # Entscheidung: Workflow oder Query?
                    # WORKFLOW: IMPLEMENTATION, BUG_FIX, REFACTOR
                    # QUERY: EXPLAIN, ANALYSIS
                    is_workflow = task_type in ["IMPLEMENTATION", "BUG_FIX", "REFACTOR"]
                    
                    if is_workflow:
                        # ╔═══════════════════════════════════════════════╗
                        # ║         WORKFLOW MODE (6 Phasen)              ║
                        # ╚═══════════════════════════════════════════════╝
                        print(f"\n[WORKFLOW] Starte 6-Phasen-Orchestrierung...\n")
                        try:
                            workflow = agent.dispatch(query)
                        except Exception as e:
                            print(f"\n[ERR] Workflow fehlgeschlagen: {e}")
                            import traceback
                            traceback.print_exc()
                        continue
                    else:
                        # ╔═══════════════════════════════════════════════╗
                        # ║         QUERY MODE (schnelle Antwort)         ║
                        # ╚═══════════════════════════════════════════════╝
                        print(f"[QUERY] Schnelle Abfrage mit Vault-Context...\n")
                        # Fallen durch zur normalen Query-Verarbeitung unten
                
                except Exception as e:
                    print(f"[WARN] Klassifikation fehlgeschlagen ({e}) → Query-Mode")
                    # Fallback: Query-Mode

            # Suche in beiden Vaults (Code + Wissen), fair gemerged
            # k=30 für 20 Top + 10 Random Strategie
            print("[SEARCH] Suche in den Vaults (30 Docs für Deep Analysis)...")
            context, _, _ = retriever.search(query, k=30)

            if context:
                print(f"[OK] Gefunden: {len(context)} Dokumente")
                for i, doc in enumerate(context):
                    title = doc.get("title", "Unbekannt")[:60]
                    dist = doc['distance']
                    # Farbcode für Treffer-Qualität
                    quality = "✅" if dist < 0.3 else "⚠️" if dist < 0.4 else "❌"
                    print(f"  [{i+1:2d}] {quality} {title}... (Dist: {dist:.2f})")
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

            # ===== DEEP ANALYSIS (optional - für jetzt deaktiviert) =====
            # Zu komplex für diese Phase - wird später mit Tool-Support implementiert
            analysis_summary = ""
            # TODO: Deep Analysis mit Deepseek + streaming neu implementieren

            # Gehaltener Gesprächskontext für Folgefragen — bewusst KURZ (letzte 2 Turns,
            # gekürzt): zu viel Historie erstickt das kleine Modell (Klein-Modell-Decke).
            sys_full = system_prompt
            if analysis_summary:
                sys_full += f"\n\n[VAULT-ANALYSE (aus Top 4 Quellen)]:\n{analysis_summary}"
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
                # ===== STANDARD MODE: Generalist mit Vault-Context =====
                # Schnelle Query mit dem Wissens-Generalisten + Vault-Kontext (60s Timeout)
                print(f"[GEN] {coder.model} mit Vault-Context (60s Timeout)...\n" + "-" * 60)
                try:
                    response = coder.generate(query, system=sys_full, stream=True)
                except requests.exceptions.Timeout:
                    response = "\n[TIMEOUT] Ollama antwortet zu langsam (>60s). Versuche später erneut."
                except Exception as e:
                    response = f"\n[ERR] Generation fehlgeschlagen: {e}"
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
