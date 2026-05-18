"""
core/paths.py - Zentrale Pfad-Definitionen für Code-Vault
============================================================
Alle Datenpfade relativ zum Vibelike-Projektroot.
"""
import os

# vibelike/ ist das neue Root
ROOT = "/home/jnrabit/vibelike"

# Core-Verzeichnis für LIB_FILE
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))

# Datenpfade - Code-Vault (Code-Dokumente)
CODE_VAULT_FILE = os.path.join(ROOT, "data", "code_archive.monolith")
CODE_CACHE_FILE = os.path.join(ROOT, "data", "code_embedding_cache.pkl")
CODE_FIELD_FILE = os.path.join(ROOT, "data", "code_resonance_field.pkl")
CODE_CENTROID_FILE = os.path.join(ROOT, "data", "code_centroid.npy")

# C++ Engine
LIB_FILE = os.path.join(_CORE_DIR, "libquelibrium.so")

# Erstelle data-Verzeichnis falls nicht vorhanden
os.makedirs(os.path.dirname(CODE_VAULT_FILE), exist_ok=True)
