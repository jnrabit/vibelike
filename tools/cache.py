"""Tool-Cache für das Vibelike-Sandbox-System.

Verwaltet gecachte Tool-Versionen, um Mount-Zeiten zu reduzieren.
"""

import hashlib
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class CachedTool:
    """Repräsentiert ein gecachtes Tool."""
    name: str
    hash: str
    path: Path
    size_bytes: int
    last_accessed: datetime
    hit_count: int


class ToolCache:
    """Verwaltet den Cache für Tools und deren Abhängigkeiten."""

    def __init__(self, cache_dir: Path = Path("/vibelike/tools/.cache")):
        """
        Initialisiert den Tool-Cache.

        Args:
            cache_dir: Verzeichnis für den Cache (Default: /vibelike/tools/.cache)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_db = self.cache_dir / "index.db"
        self._init_db()
        self._init_cache_dir()

    def _init_db(self) -> None:
        """Erstellt die SQLite-Tabellen, falls nicht vorhanden."""
        with sqlite3.connect(self.cache_db) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tool_cache (
                    tool_name TEXT PRIMARY KEY,
                    hash TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size_bytes INTEGER,
                    last_accessed TIMESTAMP,
                    hit_count INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_hash ON tool_cache(hash);
                CREATE INDEX IF NOT EXISTS idx_last_accessed ON tool_cache(last_accessed);
            """)

    def _init_cache_dir(self) -> None:
        """Erstellt das Cache-Verzeichnis, falls nicht vorhanden."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, tool_path: Path) -> Optional[CachedTool]:
        """
        Gibt die gecachte Version eines Tools zurück, falls vorhanden.

        Args:
            tool_path: Pfad zum Tool-Verzeichnis auf dem Host (z. B. /host/tools/gcc-13)

        Returns:
            CachedTool-Objekt oder None, falls nicht gecacht
        """
        tool_hash = self._compute_hash(tool_path)
        if tool_hash is None:
            return None

        with sqlite3.connect(self.cache_db) as conn:
            row = conn.execute(
                "SELECT * FROM tool_cache WHERE hash = ?",
                (tool_hash,)
            ).fetchone()

            if row:
                # Update last_accessed und hit_count
                conn.execute(
                    """
                    UPDATE tool_cache
                    SET last_accessed = CURRENT_TIMESTAMP,
                        hit_count = hit_count + 1
                    WHERE hash = ?
                    """,
                    (tool_hash,)
                )
                return CachedTool(
                    name=row[0],
                    hash=row[1],
                    path=Path(row[2]),
                    size_bytes=row[3],
                    last_accessed=datetime.fromisoformat(row[4]),
                    hit_count=row[5]
                )
        return None

    def put(self, tool_path: Path) -> CachedTool:
        """
        Fügt ein Tool zum Cache hinzu.

        Args:
            tool_path: Pfad zum Tool-Verzeichnis auf dem Host

        Returns:
            CachedTool-Objekt der gecachten Version
        """
        tool_name = tool_path.name
        tool_hash = self._compute_hash(tool_path)
        if tool_hash is None:
            raise ValueError(f"Could not compute hash for {tool_path}")

        # Zielpfad im Cache
        cache_subdir = self.cache_dir / tool_hash[:2] / tool_hash[2:]
        cache_subdir.mkdir(parents=True, exist_ok=True)
        cached_path = cache_subdir / tool_name

        # Kopiere Tool in Cache
        shutil.copytree(tool_path, cached_path)
        size_bytes = sum(f.stat().st_size for f in cached_path.rglob('*') if f.is_file())

        # Speichere in DB
        with sqlite3.connect(self.cache_db) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tool_cache
                (tool_name, hash, path, size_bytes, last_accessed, hit_count)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
                """,
                (tool_name, tool_hash, str(cached_path), size_bytes)
            )

        return CachedTool(
            name=tool_name,
            hash=tool_hash,
            path=cached_path,
            size_bytes=size_bytes,
            last_accessed=datetime.now(),
            hit_count=1
        )

    def _compute_hash(self, path: Path) -> Optional[str]:
        """
        Berechnet den SHA256-Hash eines Verzeichnisses (rekursiv).

        Args:
            path: Pfad zum Verzeichnis

        Returns:
            SHA256-Hash als Hex-String oder None bei Fehler
        """
        if not path.exists():
            return None

        hasher = hashlib.sha256()
        for root, dirs, files in os.walk(path):
            # Sortiere für deterministisches Ergebnis
            dirs.sort()
            files.sort()

            # Füge Verzeichnisnamen ein
            hasher.update(root.encode('utf-8'))

            # Füge alle Dateien ein
            for file in files:
                file_path = Path(root) / file
                # Ignoriere bestimmte Verzeichnisse/Dateien
                if any(
                    part.startswith(('.', '__pycache__', '.git', 'node_modules'))
                    for part in file_path.parts
                ):
                    continue
                if file.endswith(('.tmp', '.swp', '.log')):
                    continue

                # Hash Dateiname + Inhalt
                hasher.update(file.encode('utf-8'))
                try:
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(8192):
                            hasher.update(chunk)
                except (PermissionError, IsADirectoryError):
                    continue

        return hasher.hexdigest()

    def clean(self, max_age_days: int = 30, min_hits: int = 5) -> int:
        """
        Bereinigt den Cache von alten/ungebräuchlichen Tools.

        Args:
            max_age_days: Löscht Tools, die länger als X Tage nicht genutzt wurden
            min_hits: Behält Tools mit mindestens X Zugriffen

        Returns:
            Anzahl der gelöschten Tools
        """
        deleted_count = 0
        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        with sqlite3.connect(self.cache_db) as conn:
            # Finde Tools zum Löschen
            rows = conn.execute(
                """
                SELECT path FROM tool_cache
                WHERE last_accessed < ? AND hit_count < ?
                """,
                (cutoff_date.isoformat(), min_hits)
            ).fetchall()

            for row in rows:
                cache_path = Path(row[0])
                if cache_path.exists():
                    shutil.rmtree(cache_path, ignore_errors=True)
                    deleted_count += 1

            # Lösche aus DB
            conn.execute(
                """
                DELETE FROM tool_cache
                WHERE last_accessed < ? AND hit_count < ?
                """,
                (cutoff_date.isoformat(), min_hits)
            )

        return deleted_count
