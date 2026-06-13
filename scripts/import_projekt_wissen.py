"""
import_projekt_wissen.py
========================
Indexiert ~/MASTER_VAULT/documents/Projekt_Wissen (top-level Code-Files)
in vibelikes Code-Vault, damit Retrieval endlich Projekt-eigenen Code findet.

Design-Entscheidungen:
- Nur top-level Files (maxdepth=1). Die 14 GB im Unterordner TimeCrystal/
  sind Phone-Recovery-Dumps, nicht primaerer Code.
- Whitelist von Code-/Text-Extensions. .tar.gz/.db/.json-Dumps werden geskippt.
- Backup von Vault + Cache vor jedem Schreibvorgang (--no-backup zum Deaktivieren).
- Dry-Run als sichtbares Default-Verhalten.
- Embeddings: das gleiche Modell wie vibelike selbst nutzt
  (paraphrase-multilingual-MiniLM-L12-v2, 384 dim). Falls
  ~/Project_AI/my_multilingual_brain/ existiert, wird das geladen
  (selbes Modell, lokaler Cache).
- ID-Schema: 'PROJEKT_WISSEN-{stem}' fuer Stabilitaet ueber Re-Runs.
  Duplikate werden uebersprungen.

Nutzung:
    # Sichten was passieren wuerde
    python scripts/import_projekt_wissen.py --dry-run

    # Test mit 5 Files
    python scripts/import_projekt_wissen.py --limit 5

    # Voll importieren
    python scripts/import_projekt_wissen.py
"""

from __future__ import annotations

import argparse
import os
import pickle
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from framework.quelibrium.core.vault import Vault  # noqa: E402
from framework.quelibrium.core.paths import CODE_VAULT_FILE, CODE_CACHE_FILE  # noqa: E402


DEFAULT_INPUT = Path.home() / "MASTER_VAULT" / "documents" / "Projekt_Wissen"
LOCAL_MODEL_DIR = Path.home() / "Project_AI" / "my_multilingual_brain"
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

WHITELIST_SUFFIXES = {
    ".py", ".md", ".txt", ".cpp", ".c", ".h", ".hpp",
    ".sh", ".ino", ".rs", ".go", ".js", ".ts", ".pyx",
}
MAX_FILE_BYTES = 256 * 1024   # 256 KB pro File
MIN_FILE_BYTES = 50           # alles < 50 B ist vermutlich Stub
MAX_CONTENT_CHARS = 32_000    # Content-Snippet im Vault (Embeddings sehen
                              # nur die ersten 128 Tokens, mehr ist Doku)

SECTOR_BY_SUFFIX = {
    ".py": "PYTHON",
    ".md": "MARKDOWN",
    ".txt": "TEXT",
    ".cpp": "CPP",
    ".c": "C",
    ".h": "C_HEADER",
    ".hpp": "CPP_HEADER",
    ".sh": "SHELL",
    ".ino": "ARDUINO",
    ".rs": "RUST",
    ".go": "GO",
    ".js": "JS",
    ".ts": "TS",
    ".pyx": "CYTHON",
}


# ---------------------------------------------------------------------------
# File-Discovery
# ---------------------------------------------------------------------------

def collect_files(root: Path) -> list[Path]:
    """Sammle whitelisted Top-Level-Files mit Groessenfilter."""
    if not root.exists():
        raise FileNotFoundError(f"Eingabeordner fehlt: {root}")

    out: list[Path] = []
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in WHITELIST_SUFFIXES:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size < MIN_FILE_BYTES or size > MAX_FILE_BYTES:
            continue
        out.append(p)
    return out


def read_text(path: Path) -> str | None:
    """Versuche UTF-8 mit BOM/Latin-1 Fallback. Skip wenn nicht decodierbar."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with path.open("r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, OSError):
            continue
    return None


def build_doc(path: Path, content: str) -> dict:
    """Erzeuge Doc-Dict im vibelike-Schema."""
    stem = path.stem
    suffix = path.suffix.lower()
    sector = SECTOR_BY_SUFFIX.get(suffix, "OTHER")
    ts = time.strftime("%Y-%m-%d %H:%M:%S",
                       time.localtime(path.stat().st_mtime))
    return {
        "id":        f"PROJEKT_WISSEN-{stem}{suffix}",
        "content":   content[:MAX_CONTENT_CHARS],
        "title":     path.name,
        "source":    "PROJEKT_WISSEN_LEGACY",
        "sector":    sector,
        "url":       f"file://{path}",
        "lang":      "de",  # Code-Kommentare sind ueberwiegend Deutsch
        "timestamp": ts,
    }


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def load_embedder():
    """Lade Sentence-Transformer (lokales Modell bevorzugt)."""
    from sentence_transformers import SentenceTransformer  # lazy import

    device = "cuda"
    try:
        import torch  # noqa: F401
        if not __import__("torch").cuda.is_available():
            device = "cpu"
    except Exception:
        device = "cpu"

    if LOCAL_MODEL_DIR.exists():
        print(f"[INFO] Lade lokales Modell: {LOCAL_MODEL_DIR} (device={device})")
        try:
            return SentenceTransformer(str(LOCAL_MODEL_DIR), device=device)
        except Exception as e:
            print(f"[WARN] Lokales Modell schlug fehl: {e}")

    print(f"[INFO] Lade Default-Modell: {DEFAULT_MODEL} (device={device})")
    return SentenceTransformer(DEFAULT_MODEL, device=device)


def embed_texts(model, texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Embedde Texte normalisiert (cosine-ready), float32."""
    arr = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return arr.astype(np.float32)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def make_backup(*paths: Path) -> list[Path]:
    """Kopiere existierende Files zu `<name>.bak-<timestamp>`."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backups: list[Path] = []
    for p in paths:
        if p.exists():
            bak = p.with_suffix(p.suffix + f".bak-{stamp}")
            shutil.copy2(p, bak)
            backups.append(bak)
            print(f"[BACKUP] {p.name} -> {bak.name}")
    return backups


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help=f"Quelle (default: {DEFAULT_INPUT})")
    parser.add_argument("--vault", type=Path, default=Path(CODE_VAULT_FILE),
                        help="Pfad zum Vault-File")
    parser.add_argument("--cache", type=Path, default=Path(CODE_CACHE_FILE),
                        help="Pfad zum Embedding-Cache")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur zeigen was passieren wuerde, nichts schreiben")
    parser.add_argument("--limit", type=int, default=None,
                        help="Nur erste N Files importieren (Test)")
    parser.add_argument("--no-backup", action="store_true",
                        help="Vault/Cache-Backup ueberspringen")
    args = parser.parse_args()

    # --- 1. Files sammeln
    files = collect_files(args.input)
    print(f"[INFO] {len(files)} Files in {args.input}")
    if args.limit is not None:
        files = files[:args.limit]
        print(f"[INFO] Limitiert auf {len(files)} Files")
    if not files:
        print("[ERR] Keine Files gefunden — Filter zu strikt oder Pfad falsch.")
        return 1

    # Verteilung nach Sector
    sectors: dict[str, int] = {}
    for f in files:
        s = SECTOR_BY_SUFFIX.get(f.suffix.lower(), "OTHER")
        sectors[s] = sectors.get(s, 0) + 1
    print(f"[INFO] Verteilung: {sectors}")
    print()

    # --- 2. Existing vault laden zum Duplikat-Check
    vault = Vault(str(args.vault))
    existing_docs = vault.load() if args.vault.exists() else []
    existing_ids = {d["id"] for d in existing_docs}
    print(f"[INFO] Vault hat aktuell {len(existing_docs)} Docs")

    existing_cache: dict = {}
    if args.cache.exists():
        with args.cache.open("rb") as f:
            existing_cache = pickle.load(f)
        print(f"[INFO] Cache hat aktuell {len(existing_cache)} Embeddings")
    print()

    # --- 3. Files lesen, Docs bauen, Duplikate skippen
    new_docs: list[dict] = []
    new_texts: list[str] = []
    skipped_dup = 0
    skipped_read = 0
    for path in files:
        content = read_text(path)
        if content is None or len(content.strip()) < MIN_FILE_BYTES:
            skipped_read += 1
            continue
        doc = build_doc(path, content)
        if doc["id"] in existing_ids:
            skipped_dup += 1
            continue
        new_docs.append(doc)
        # Fuer Embedding: title + content (verbessert Treffer auf Filename-Queries)
        new_texts.append(f"{doc['title']}\n\n{doc['content'][:8000]}")

    print(f"[INFO] {len(new_docs)} neue Docs (skipped: {skipped_dup} Duplikat, {skipped_read} unlesbar)")

    if args.dry_run:
        print()
        print("DRY-RUN — nichts geschrieben.")
        if new_docs:
            print("Erste 3 Doc-Stubs (ohne content):")
            for d in new_docs[:3]:
                preview = {k: v for k, v in d.items() if k != "content"}
                print(f"  {preview}")
        return 0

    if not new_docs:
        print("[INFO] Nichts zu tun — alle Files schon im Vault.")
        return 0

    # --- 4. Backup
    if not args.no_backup:
        make_backup(args.vault, args.cache)
        print()

    # --- 5. Embeddings
    print("[STEP] Lade Embedder...")
    model = load_embedder()
    print(f"[STEP] Embedde {len(new_texts)} Texte...")
    new_vecs = embed_texts(model, new_texts)
    print(f"[OK] Embeddings: shape={new_vecs.shape}, dtype={new_vecs.dtype}")
    print()

    # --- 6. In Vault + Cache mergen
    merged_docs = existing_docs + new_docs
    merged_cache = dict(existing_cache)
    for doc, vec in zip(new_docs, new_vecs):
        merged_cache[doc["id"]] = vec

    # Schreiben (atomar: erst tmp, dann rename)
    tmp_vault = args.vault.with_suffix(args.vault.suffix + ".tmp")
    tmp_cache = args.cache.with_suffix(args.cache.suffix + ".tmp")

    print(f"[STEP] Schreibe Vault: {args.vault} ({len(merged_docs)} docs)")
    Vault(str(tmp_vault)).save(merged_docs)
    os.replace(tmp_vault, args.vault)

    print(f"[STEP] Schreibe Cache: {args.cache} ({len(merged_cache)} embeddings)")
    with tmp_cache.open("wb") as f:
        pickle.dump(merged_cache, f)
    os.replace(tmp_cache, args.cache)

    print()
    print(f"[DONE] Vault: {len(existing_docs)} -> {len(merged_docs)} (+{len(new_docs)})")
    print(f"[DONE] Cache: {len(existing_cache)} -> {len(merged_cache)} (+{len(new_docs)})")
    print()
    print("Naechster Schritt: vibelike-terminal neu starten, dann test-query stellen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
