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
import time
import pickle
import numpy as np
import requests

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
# Empfehlung: qwen3:8b (bestes Reasoning) oder qwen2.5:3b (parallel-fit).
ANALYSIS_MODEL = os.environ.get("VIBELIKE_ANALYSIS_MODEL", "qwen3:8b")
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
            "content_hash": hash(c.get("content", "")) % 2**32,
            "content_len": len(c.get("content", ""))
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

    def __init__(self):
        self.protocol = Protocol(vault_file=CODE_VAULT_FILE, cache_file=CODE_CACHE_FILE)
        self.hw_logger = HardwareLogger(self.protocol)

        # SentenceTransformer laden
        try:
            from sentence_transformers import SentenceTransformer
            device = "cuda" if self._has_cuda() else "cpu"
            self.encoder = SentenceTransformer(self.EMBEDDING_MODEL, device=device)
            print("[OK] SentenceTransformer geladen")
        except ImportError as e:
            print(f"[ERR] sentence-transformers nicht installiert: {e}")
            self.encoder = None

        # Advanced Retrieval: ResonanceField + ChaosRetrieval
        try:
            self.resonance_field = ResonanceField()
            self.chaos_retrieval = ChaosRetrieval(protocol=self.protocol, field=self.resonance_field)
            print("[OK] ⚡ Chaos Retrieval mit Resonance Field aktiviert")
            self.use_chaos_retrieval = True
        except Exception as e:
            print(f"[WARN] Chaos Retrieval nicht verfügbar: {e}")
            self.chaos_retrieval = None
            self.use_chaos_retrieval = False

        # Ossifikat Integration
        try:
            if ADAPTERS_AVAILABLE:
                self.terminal_adapter = TerminalAdapter()
                print("[OK] 📊 Ossifikat TerminalAdapter aktiviert")
            else:
                self.terminal_adapter = None
        except Exception as e:
            print(f"[WARN] Ossifikat nicht verfügbar: {e}")
            self.terminal_adapter = None

        print(f"[OK] Code-Vault: {len(self.protocol.archive):,} docs, {len(self.protocol._doc_cache):,} vectors")
    
    @staticmethod
    def _has_cuda() -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False
    
    def search(self, query: str, k: int = 10) -> tuple:
        """Such im Code-Vault mit optionalem Chaos Retrieval. Rückgabe: (Dokumente, Hardware-State vor/nach)"""
        if not self.encoder:
            return [], None, None

        # Hardware-State vor Suche
        state_before = self.hw_logger.log_state(query, "search_start")

        # Query embedden
        query_vec = self.encoder.encode(query, convert_to_numpy=True).astype(np.float32)
        if query_vec.ndim > 1:
            query_vec = query_vec[0]

        # Suche mit Chaos Retrieval (wenn verfügbar) oder Standard
        if self.use_chaos_retrieval and self.chaos_retrieval:
            try:
                # Update Warp mit aktuellem Lorenz-State
                lorenz_state = self.protocol.get_lorenz_params()
                self.chaos_retrieval.warp.update(lorenz_state)

                # Chaos-basierte Suche — returnt [(doc_id, distance), ...]
                results = self.chaos_retrieval.search(query_vec, top_k=k * 2)

                # Dokumente auflösen
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
                            "retrieval_method": "chaos",
                        })
            except Exception as e:
                print(f"[WARN] Chaos Retrieval fehlgeschlagen, fallback zu raw_search: {e}")
                results = self.protocol.raw_search(query_vec, density=1.0)
                docs = self._docs_from_results(results, k)
        else:
            # Standard-Suche
            results = self.protocol.raw_search(query_vec, density=1.0)
            docs = self._docs_from_results(results, k)

        # Hardware-State nach Suche
        state_after = self.hw_logger.log_state(query, "search_end")

        return docs, state_before, state_after

    def _docs_from_results(self, results: list, k: int) -> list:
        """Helper: Konvertiere Raw-Search Ergebnisse in Doc-Dicts."""
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
                    "retrieval_method": "raw_search",
                })
        return docs


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
                 stream: bool = False) -> str:
        """Generiere mit dem konfigurierten Modell.

        stream=True: Tokens werden live nach stdout geschrieben (Vordergrund-Calls).
        stream=False: ein Block, kein Live-Output (Hintergrund-Threads, sonst Interleaving).
        Rückgabe ist in beiden Fällen der volle Antworttext.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature, "top_p": 0.9, "num_predict": self.num_predict},
        }
        if system:
            payload["system"] = system

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


# =============================================================================
# System Prompt Builder
# =============================================================================

def build_system_prompt(context: list) -> str:
    """Baue System-Prompt mit Code-Kontext."""
    if not context:
        return """Du bist ein Senior Software Engineer.
Antworte technisch präzise auf Deutsch. Code in Markdown-Codeblöcken.
Wenn unsicher: explizit markieren."""
    
    sources = []
    for i, d in enumerate(context[:3]):  # Max 3 Quellen für Fokus
        sources.append(
            f"QUELLE {i+1} ({d.get('distance', 0):.1f}, {d.get('source', 'code-vault')}):\n"
            f"{d.get('content', '')[:400]}"
        )
    
    return f"""Du bist ein Senior Software Engineer mit Quellen-Fokus.

REGELN:
1. Antworte primär basierend auf den QUELLEN.
2. Code IMMER in Markdown-Codeblöcken mit Sprachen-Tag.
3. Wenn Quellen nicht ausreichen: explizit sagen.
4. Technisch präzise, auf Deutsch.

QUELLEN:\n\n""" + "\n\n".join(sources)


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

    # Multi-retrieval: Haupt-Query + Varianten
    queries = [
        query,
        f"how {query}",
        f"implementation {query}",
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
        }
        if workflow.get("iteration"):
            print(f"Iteration: {workflow['iteration']} (parent: {workflow.get('parent_id')})")
        for phase_name, phase_data in workflow.get("phases", {}).items():
            if phase_data:
                status = "✓" if phase_data.get("approved") or phase_data.get("tests_passed") or phase_data.get("committed") else "✗"
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


def main():
    print_header()

    # Initialisierung
    print("[INIT] Lade Code-Vault...")
    retriever = CodeRetriever()
    coder = QwenCoder()
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

            # Suche im Vault
            print("[SEARCH] Suche im Code-Vault...")
            context, _, _ = retriever.search(query, k=5)

            if context:
                print(f"[OK] Gefunden: {len(context)} Dokumente")
                for i, doc in enumerate(context):
                    title = doc.get("title", "Unbekannt")[:40]
                    print(f"  [{i+1}] {title}... (Dist: {doc['distance']:.1f})")

                # Log to ossifikat
                if ADAPTERS_AVAILABLE and retriever.terminal_adapter:
                    context_ids = [str(c.get("id", "")) for c in context]
                    retriever.terminal_adapter.store_query_response(
                        query=query,
                        response="",
                        context_ids=context_ids
                    )
            else:
                print("[WARN] Keine Dokumente gefunden")
            
            # System-Prompt bauen
            system_prompt = build_system_prompt(context)
            
            # Generieren (streaming → Live-Output)
            print("[GEN] qwen2.5-coder...\n" + "-" * 60)
            response = coder.generate(query, system=system_prompt, stream=True)
            print("-" * 60)

            # Triplet loggen
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
    main()
