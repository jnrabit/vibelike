"""
Terminal UI helpers extracted from terminal.py.

Functions for displaying information to the user:
- clear_screen()
- print_header()
- print_state()
- print_logs()
- review_triples()
- research_mode()

This module keeps UI logic separate from core terminal logic.
"""

import os
import json
import time
from pathlib import Path

from config import settings

# Will be set by terminal.py at runtime
POWER_USER = False
LOG_FILE = None
ADAPTERS_AVAILABLE = False


def clear_screen():
    """Clear the terminal screen (cross-platform)."""
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    """Print terminal header and help text."""
    clear_screen()
    print("=" * 60)
    print("CODE-VAULT TERMINAL - ORCHESTRIERUNG")
    print("=" * 60)
    print("[q] beenden | [l] logs | [s] state | [r] review | [c] clear")
    print("[Auto-Klassifikation] Jeder Input → Workflow oder Query")
    print("[EXPLAIN/ANALYSIS] → Query-Mode (Deepseek + FileTool)")
    print("[IMPLEMENTATION/BUG_FIX/REFACTOR] → Workflow (6 Phasen)")
    if POWER_USER:
        print("\n[POWER-USER MODE AKTIV]")
        print("[briefing:] Direkter Workflow-Start | [??] Rat-Modi verfügbar")
    print("-" * 60)


def print_state(retriever):
    """Display current hardware state from retriever."""
    try:
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
    except Exception as e:
        print(f"[ERR] Hardware state retrieval failed: {e}")


def print_logs():
    """Display last 10 log entries from triplets.jsonl."""
    log_path = Path(LOG_FILE) if LOG_FILE else settings.log_file
    
    if not log_path.exists():
        print("\n[INFO] Keine Logs vorhanden")
        return
    
    print("\n" + "=" * 40)
    print("LOGS (letzte 10)")
    print("=" * 40)
    
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        
        for line in lines[-10:]:
            entry = json.loads(line)
            timestamp = time.strftime('%H:%M:%S', time.localtime(entry['timestamp']))
            
            if entry["type"] == "triplet":
                query_preview = entry['query'][:50]
                context_count = entry.get('context_count', 0)
                response_len = entry.get('response_len', 0)
                print(f"[{timestamp}] QUERY: {query_preview}...")
                print(f"  -> Context: {context_count} docs, Response: {response_len} chars")
            elif entry["type"] == "hardware_state":
                entropy = entry['thermodynamics']['entropy']
                temperature = entry['thermodynamics']['temperature']
                print(f"[{timestamp}] HARDWARE: entropy={entropy:.2f} temp={temperature:.2f}")
        
        print("=" * 40 + "\n")
    except Exception as e:
        print(f"[ERR] Log reading failed: {e}")


def review_triples(retriever):
    """Open ossifikat staging review interface."""
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
    """
    Deep exploration mode: multi-retrieval without workflow.
    
    Allows user to search vaults deeply and optionally synthesize
    results using Babel synthesizer.
    """
    print("\n" + "=" * 60)
    print("RESEARCH MODE - Tiefe Vault-Exploration")
    print("=" * 60)

    query = input("\n🔍 Research-Query eingeben: ").strip()
    if not query:
        print("❌ Keine Query eingegeben.")
        return

    # DE->EN translation hook
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

    # Multi-retrieval: main query + variants
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

    # Deduplicate and sort by distance
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

    # Optional Babel synthesis
    print()
    synth_choice = input("📚 Synthese-Modus? [f]eynman / [s]cience / [Enter]=keine: ").strip().lower()
    if synth_choice in ("f", "feynman", "s", "science"):
        mode = "feynman" if synth_choice.startswith("f") else "science"
        try:
            from babel_synthesizer import BabelSynthesizer
            synth = BabelSynthesizer(default_mode=mode)
            print(f"\n[BABEL] Synthese läuft (mode={mode}, model={synth.qwen.model})...")
            result = synth.synthesize(query, unique_docs)
            print("\n" + "=" * 60)
            print("SYNTHESE RESULT")
            print("=" * 60)
            print(result)
            print("=" * 60 + "\n")
        except ImportError:
            print("[WARN] babel_synthesizer nicht verfügbar")
        except Exception as e:
            print(f"[ERR] Synthese fehlgeschlagen: {e}")
