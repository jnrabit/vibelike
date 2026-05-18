"""Health-Check für das Vibelike-System."""

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from reqqueue.manager import QueueStatus
except ImportError:
    from vibelike.reqqueue.manager import QueueStatus


@dataclass
class HealthStatus:
    """Status des Health-Checks."""
    is_healthy: bool
    last_check: datetime
    queue_status: Optional[QueueStatus] = None
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class HealthCheck:
    """Überwacht den Status der Request-Queue und des Workers."""

    def __init__(
        self,
        queue_db_path: str = "/vibelike/logs/queue.db",
        health_file: str = "/tmp/vibelike_queue_health",
        max_age_seconds: int = 30
    ):
        """
        Initialisiert den Health-Check.

        Args:
            queue_db_path: Pfad zur Queue-Datenbank
            health_file: Pfad zur Health-Check-Datei
            max_age_seconds: Maximales Alter der Health-Datei (in Sekunden)
        """
        self.queue_db_path = Path(queue_db_path)
        self.health_file = Path(health_file)
        self.max_age_seconds = max_age_seconds

    def check(self) -> HealthStatus:
        """
        Führt einen Health-Check durch.

        Returns:
            HealthStatus-Objekt
        """
        status = HealthStatus(
            is_healthy=True,
            last_check=datetime.now()
        )

        # 1. Prüfe Health-Datei
        if not self._check_health_file():
            status.is_healthy = False
            status.errors.append("Health file not updated recently")

        # 2. Prüfe Queue-DB
        try:
            queue_status = self._check_queue_db()
            status.queue_status = queue_status
            if queue_status.stale > 0:
                status.is_healthy = False
                status.errors.append(f"{queue_status.stale} stale requests detected")
        except Exception as e:
            status.is_healthy = False
            status.errors.append(f"Queue DB check failed: {e}")

        # 3. Prüfe auf hängende Requests
        try:
            stale = self._count_stale_requests()
            if stale > 0:
                status.is_healthy = False
                status.errors.append(f"{stale} requests stuck in 'running' state")
        except Exception as e:
            status.is_healthy = False
            status.errors.append(f"Stale request check failed: {e}")

        return status

    def _check_health_file(self) -> bool:
        """Prüft, ob die Health-Datei aktuell ist."""
        if not self.health_file.exists():
            return False

        # Prüfe Modifikationszeit
        mtime = datetime.fromtimestamp(self.health_file.stat().st_mtime)
        return (datetime.now() - mtime).total_seconds() < self.max_age_seconds

    def _check_queue_db(self) -> QueueStatus:
        """Prüft den Status der Queue-Datenbank."""
        with sqlite3.connect(self.queue_db_path) as conn:
            # Zähle Requests nach Status
            pending = conn.execute(
                "SELECT COUNT(*) FROM request_queue WHERE status = 'pending'"
            ).fetchone()[0]
            running = conn.execute(
                "SELECT COUNT(*) FROM request_queue WHERE status = 'running'"
            ).fetchone()[0]

            # Prüfe auf "stale" Requests (länger als 24h in running/pending)
            stale = conn.execute(
                """
                SELECT COUNT(*) FROM request_queue
                WHERE status IN ('running', 'pending')
                AND created_at < datetime('now', '-24 hours')
                """
            ).fetchone()[0]

            return QueueStatus(
                pending=pending,
                running=running,
                stale=stale
            )

    def _count_stale_requests(self) -> int:
        """Zählt Requests, die zu lange in 'running' sind."""
        with sqlite3.connect(self.queue_db_path) as conn:
            return conn.execute(
                """
                SELECT COUNT(*) FROM request_queue
                WHERE status = 'running'
                AND updated_at < datetime('now', '-1 hour')
                """
            ).fetchone()[0]

    def update(self) -> None:
        """Aktualisiert die Health-Check-Datei."""
        self.health_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.health_file, "w") as f:
            f.write(datetime.now().isoformat())

    def is_worker_running(self) -> bool:
        """Prüft, ob der Worker läuft (Health-Datei aktuell)."""
        return self._check_health_file()

    def force_recovery(self) -> None:
        """
        Erzwingt eine Wiederherstellung bei hängendem Worker.
        - Setzt alle 'running'-Requests zurück auf 'pending'
        - Aktualisiert Health-Check
        """
        with sqlite3.connect(self.queue_db_path) as conn:
            # Setze alle 'running'-Requests zurück
            conn.execute(
                """
                UPDATE request_queue
                SET status = 'pending', retries = retries + 1
                WHERE status = 'running'
                """
            )
        self.update()
