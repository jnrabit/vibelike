"""
bridge_finder.py — Divergente Ideenfindung / Brücken-Skizze.

Prinzip (chaos/exploration): viel aus dem fokussierten IT/Code-Vault (vibelike),
+ ein paar Wildcards aus dem großen Wissens-Vault (collect, ~189k Docs) →
qwen3:8b skizziert mögliche Brücken zwischen den Konzepten.

Output = KANDIDATEN (mit Rauschen — das ist der Sinn). Du/Claude kuratierst.
Optional landen bestätigte Brücken später als Staging-Tripel in ossifikat.

Aufruf:
    python3 experiments/bridge_finder.py "deine Frage / dein Thema"
"""
import os
import re
import sys
import pickle
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from terminal import CodeRetriever, QwenCoder, ANALYSIS_MODEL
from framework.quelibrium.core.vault import Vault

COLLECT = Path("/home/jnrabit/collect/data")
COLLECT_VAULT = COLLECT / "monolith_archive.monolith"
COLLECT_CACHE = COLLECT / "monolith_embedding_cache.pkl"

IT_TOPK = 12       # viel aus dem fokussierten Vault
WILDCARDS = 3      # wenige Wildcards aus dem großen Vault


def load_collect_wildcards(query_vec: np.ndarray, k: int = WILDCARDS):
    """Top-k aus collects großem Wissens-Vault via numpy-cosine. Graceful []."""
    if not COLLECT_VAULT.exists() or not COLLECT_CACHE.exists():
        print("[WARN] collect-Vault nicht gefunden — nur IT-Vault.")
        return []
    try:
        print(f"[…] lade collect-Vault ({COLLECT_VAULT.stat().st_size//1_000_000}MB) "
              f"+ Cache ({COLLECT_CACHE.stat().st_size//1_000_000}MB)…")
        docs = Vault(str(COLLECT_VAULT)).load()
        with open(COLLECT_CACHE, "rb") as f:
            cache = pickle.load(f)
        ids = list(cache.keys())
        mat = np.stack([np.asarray(cache[i], dtype=np.float32) for i in ids])
        # cosine
        q = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        m = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8)
        sims = m @ q
        top = np.argsort(-sims)[:k]
        index = {str(d.get("id")): d for d in docs}
        out = []
        for i in top:
            d = index.get(str(ids[i]), {})
            out.append({
                "source": "COLLECT_BIG",
                "title": (d.get("title") or str(ids[i]))[:60],
                "content": (d.get("text") or d.get("content") or "")[:400],
                "sim": float(sims[i]),
            })
        # Sanity: streuen die sims? (sonst evtl. Modell-Mismatch)
        spread = float(sims.max() - np.median(sims))
        print(f"[…] collect Wildcards: top-sim={sims[top[0]]:.3f}, spread={spread:.3f}"
              + ("  ⚠️ niedrige Streuung → evtl. Embedder-Mismatch" if spread < 0.05 else ""))
        return out
    except Exception as e:
        print(f"[WARN] collect-Vault Laden fehlgeschlagen: {e}")
        return []


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else \
        "Wie hängen chaotische Dynamik und Wissens-Retrieval zusammen?"
    print(f"\n{'='*70}\nQUERY: {query}\n{'='*70}\n")

    retr = CodeRetriever()

    # 1. Viel aus dem fokussierten IT/Code-Vault (ChaosRetrieval, inkl. Exploration)
    it_docs, _, _ = retr.search(query, k=IT_TOPK)
    # 2. Query-Vektor (für collect denselben Embedder nutzen)
    qvec = retr.encoder.encode(query, convert_to_numpy=True).astype(np.float32)
    if qvec.ndim > 1:
        qvec = qvec[0]
    wild = load_collect_wildcards(qvec)

    # Konzept-Liste bauen
    pool = []
    for d in it_docs:
        pool.append({"source": d.get("source", "IT"), "title": d.get("title", "?")[:60],
                     "content": (d.get("content") or "")[:400]})
    pool.extend(wild)

    print(f"\n--- Konzept-Pool ({len(it_docs)} IT + {len(wild)} Wildcards) ---")
    for i, c in enumerate(pool, 1):
        tag = "🃏" if c["source"] == "COLLECT_BIG" else "  "
        print(f"{tag}[{i}] {c['title']}  ({c['source']})")

    # 3. qwen3:8b skizziert Brücken
    listing = "\n".join(f"[{i}] {c['title']} ({c['source']}): {c['content'][:200]}"
                        for i, c in enumerate(pool, 1))
    prompt = (
        f"Frage/Thema: {query}\n\n"
        f"Hier sind abgerufene Konzepte (die mit 🃏/COLLECT_BIG sind Wildcards aus einem "
        f"breiten Wissens-Vault — gerade die nicht-offensichtlichen Verbindungen sind "
        f"interessant):\n\n{listing}\n\n"
        f"Skizziere 3-5 MÖGLICHE BRÜCKEN (nicht-offensichtliche Verbindungen) zwischen "
        f"diesen Konzepten, die zur Frage/zum Thema beitragen könnten. Je Brücke EINE Zeile:\n"
        f"  <Konzept A> ↔ <Konzept B>: <die Verbindung in einem Satz>\n"
        f"Bevorzuge überraschende, cross-domain Verbindungen. Spekulation ist erlaubt "
        f"(es sind Kandidaten, kein Beweis)."
    )
    print(f"\n{'='*70}\n🌉 BRÜCKEN-SKIZZE (qwen3:8b, Kandidaten):\n{'='*70}")
    # qwen3:8b ist Reasoning-Modell (<think>): num_predict großzügig, Block strippen.
    qwen = QwenCoder(model=ANALYSIS_MODEL, num_predict=2000)
    raw = qwen.generate(prompt, temperature=0.7, stream=False) or ""
    bridges = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    print(bridges if bridges else "(qwen lieferte leer)")
    print()


if __name__ == "__main__":
    main()
