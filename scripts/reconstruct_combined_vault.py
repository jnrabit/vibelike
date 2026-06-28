#!/usr/bin/env python3
"""Rekonstruiert den kombinierten ~260k-Wissens-Vault: 188k-Basis + 70k ARXIV.

Die andere Session ersetzte die kombinierte Version durch die 188k-Basis. Die
ARXIV-Teile (monolith_archive_OLD.json, 70k Docs) sind noch da, aber ihre
Embeddings fehlen → werden hier neu berechnet (paraphrase-multilingual-MiniLM-
L12-v2, 384-dim, UNNORMALISIERT wie die Basis).

Schreibt NEUE Dateien (_combined), die Originale (188k) bleiben unberührt.
"""
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/jnrabit/vibelike")
from framework.quelibrium.core.vault import Vault

DATA = Path("/home/jnrabit/collect/data")
BASE_VAULT = DATA / "monolith_archive.monolith"
BASE_CACHE = DATA / "monolith_embedding_cache.pkl"
ARXIV = Path("/home/jnrabit/Project_AI/monolith_archive_OLD.json")
OUT_VAULT = DATA / "monolith_archive_combined.monolith"
OUT_CACHE = DATA / "monolith_embedding_cache_combined.pkl"
MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

t0 = time.time()

print("[1/6] Lade Basis-Vault (188k)...", flush=True)
base = Vault(str(BASE_VAULT)).load()
base_ids = {str(d.get("id")) for d in base}
print(f"      {len(base):,} docs, {len(base_ids):,} eindeutige IDs", flush=True)

print("[2/6] Lade Basis-Cache...", flush=True)
with open(BASE_CACHE, "rb") as f:
    cache = pickle.load(f)
print(f"      {len(cache):,} Vektoren", flush=True)

print("[3/6] Lade ARXIV (70k) + Dedup gegen Basis...", flush=True)
arx = json.load(open(ARXIV))
seen = set(base_ids)
new_docs = []
for d in arx:
    i = str(d.get("id"))
    if i and i not in seen:
        seen.add(i)
        new_docs.append(d)
print(f"      {len(new_docs):,} neue Docs (von {len(arx):,})", flush=True)

print(f"[4/6] Embedde {len(new_docs):,} Docs ({MODEL}, unnormalisiert)...", flush=True)
from sentence_transformers import SentenceTransformer
try:
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
except Exception:
    device = "cpu"
model = SentenceTransformer(MODEL, device=device)
print(f"      device={device}", flush=True)
texts = [str(d.get("content") or d.get("text") or d.get("title") or "") for d in new_docs]
embs = model.encode(
    texts, batch_size=64, convert_to_numpy=True,
    normalize_embeddings=False,  # Basis ist unnormalisiert (Norm≈3.15) → matchen
    show_progress_bar=True,
)
for d, e in zip(new_docs, embs):
    cache[str(d.get("id"))] = e.astype("float32")
print(f"      Cache jetzt {len(cache):,} Vektoren", flush=True)

print("[5/6] Kombiniere + schreibe (verschlüsselt + Cache)...", flush=True)
combined = base + new_docs
Vault(str(OUT_VAULT)).save(combined)
tmp = str(OUT_CACHE) + ".tmp"
with open(tmp, "wb") as f:
    pickle.dump(cache, f, protocol=4)
Path(tmp).replace(OUT_CACHE)
print(f"      {len(combined):,} docs → {OUT_VAULT.name}", flush=True)

print("[6/6] Verifiziere Reload...", flush=True)
check = Vault(str(OUT_VAULT)).load()
ok = len(check) == len(combined)
print(f"      Reload: {len(check):,} docs  {'✓' if ok else '✗ MISMATCH'}", flush=True)

print(f"\nFERTIG in {time.time()-t0:.0f}s — kombiniert: {len(combined):,} docs, "
      f"{len(cache):,} Vektoren", flush=True)
print(f"  Vault: {OUT_VAULT}", flush=True)
print(f"  Cache: {OUT_CACHE}", flush=True)
