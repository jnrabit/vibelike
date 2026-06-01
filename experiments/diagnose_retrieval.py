#!/usr/bin/env python3
"""
Diagnostic: Wie werden Queries ins Code-Vault Embedding gemapped?

Zeigt:
1. Query-Embedding vs Dokument-Embeddings (Distanzen)
2. Wann ChaosRetrieval vs Raw Search besser ist
3. Ob QueryTranslator helfen würde
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from terminal import CodeRetriever
from query_translator import QueryTranslator
import numpy as np


def diagnose_query(retriever, query: str, k=5):
    """Teste einen Query gegen den Code-Vault."""
    print(f"\n{'='*70}")
    print(f"QUERY: {query}")
    print(f"{'='*70}")

    # Query embedden
    if not retriever.encoder:
        print("[ERR] SentenceTransformer nicht verfügbar")
        return

    # Pre-Retrieval-Translation (wie im echten search())
    search_query = query
    if retriever.query_translator is not None:
        tr = retriever.query_translator.translate(query)
        search_query = tr.get("translated") or query
        if search_query != query:
            print(f"🌐 Übersetzt → '{search_query}'")

    query_vec = retriever.encoder.encode(search_query, convert_to_numpy=True)
    if query_vec.ndim > 1:
        query_vec = query_vec[0]
    print(f"Query-Vector Shape: {query_vec.shape}")
    print(f"Query-Vector Norm: {np.linalg.norm(query_vec):.4f}")

    # numpy-cosine (neuer Fallback) durchführen
    print(f"\n[NUMPY-COSINE] Top {k} Ergebnisse:")
    try:
        for i, doc in enumerate(retriever._numpy_cosine_search(query_vec, k)[:k], 1):
            title = doc.get("title", "")[:50]
            source = doc.get("source", "?")
            print(f"  {i}. [dist={doc['distance']:.4f}] {title} ({source})")
    except Exception as e:
        print(f"  [ERR] {e}")

    # ChaosRetrieval durchführen (wenn verfügbar)
    if retriever.use_chaos_retrieval and retriever.chaos_retrieval:
        print(f"\n[CHAOS RETRIEVAL] Top {k} Ergebnisse:")
        try:
            # Update Warp mit aktuellem Lorenz-State
            lorenz_state = retriever.protocol.get_lorenz_params()
            retriever.chaos_retrieval.warp.update(lorenz_state)

            results_chaos = retriever.chaos_retrieval.search(query_vec, top_k=k)
            for i, (doc_id, distance) in enumerate(results_chaos[:k], 1):
                for doc in retriever.protocol.archive:
                    if str(doc.get("id")) == str(doc_id):
                        title = doc.get("title", "")[:50]
                        source = doc.get("source", "?")
                        print(f"  {i}. [dist={distance:.4f}] {title} ({source})")
                        break
        except Exception as e:
            print(f"  [WARN] ChaosRetrieval fehlgeschlagen: {e}")
    else:
        print(f"\n[CHAOS RETRIEVAL] nicht verfügbar")

    # Statistics
    print(f"\n[ARCHIVE STATS]")
    print(f"  Gesamt-Dokumente: {len(retriever.protocol.archive)}")
    sources = {}
    for doc in retriever.protocol.archive:
        src = doc.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    for src, count in sorted(sources.items(), key=lambda x: -x[1])[:5]:
        print(f"    {src}: {count}")


if __name__ == "__main__":
    print("[INIT] Starten CodeRetriever...")
    retriever = CodeRetriever()

    # Test-Queries: Mix aus DE (Translator triggert) und EN
    queries = [
        "Wie funktioniert binäre Suche in einem Baum?",
        "Wie wird search() mit dem Code-Vault integriert?",
        "Transport Layer Security Handshake",
        "How does a hash table work?",
    ]

    print("\n" + "="*70)
    print("QUERY EMBEDDING DIAGNOSTICS")
    print("="*70)
    print(f"Encoding Model: {retriever.encoder.get_sentence_embedding_dimension()} dims")
    print(f"ChaosRetrieval: {'enabled' if retriever.use_chaos_retrieval else 'disabled'}")

    for query in queries:
        diagnose_query(retriever, query, k=5)

    print("\n" + "="*70)
    print("INTERPRETATION")
    print("="*70)
    print("""
Wenn Raw Search und ChaosRetrieval sehr unterschiedliche Ergebnisse geben:
  → ChaosRetrieval versucht, semantische Muster zu finden (via Lorenz/Resonance)

Wenn beide niedrige Scores haben (>0.5 distance bei normalized):
  → Query passt nicht zu Vault-Dokumenten (Vocabulary Mismatch)
  → QueryTranslator könnte helfen: Query reformulieren zu technischen Keywords

Falls sehr hohe Varianz zwischen Queries:
  → Vault-Dokumente sind zu heterogen
  → Könnten in Kategorien gruppiert werden (Tech vs Docs vs Code)
""")
