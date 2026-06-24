"""Request-Queue für das Vibelike-System (sequentielle Abarbeitung)."""

import json
import sqlite3
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    from vibelike.models.request import Request
    from vibelike.config import QUEUE_DB
except ImportError:
    warnings.warn("Could not import Request model or QUEUE_DB from config", ImportWarning)
    Request = None
    QUEUE_DB = Path("/vibelike/logs/queue.db")


@dataclass
class QueueStatus:
    """Status der Request-Queue."""
    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    timeout: int = 0
    stale: int = 0
    next_request: Optional[dict] = None


class RequestQueue:
    """Verwaltet eine SQLite-basierte Request-Queue für sequentielle Ausführung."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialisiert die Request-Queue.

        Args:
            db_path: Pfad zur SQLite-Datenbank (default: config.QUEUE_DB)
        """
        self.db_path = Path(db_path) if db_path else QUEUE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._health_check_path = Path("/tmp/vibelike_queue_health")
        self._update_health_check()

    def _init_db(self) -> None:
        """Erstellt die Tabellen, falls nicht vorhanden."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS request_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    req_id TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    priority INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    retries INTEGER DEFAULT 0,
                    next_attempt_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    exit_code INTEGER
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    req_id TEXT NOT NULL,
                    user TEXT NOT NULL,
                    message TEXT NOT NULL,
                    due_at TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'pending',
                    sent_at TIMESTAMP,
                    FOREIGN KEY (req_id) REFERENCES request_queue(req_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_queue_status ON request_queue(status);
                CREATE INDEX IF NOT EXISTS idx_queue_priority ON request_queue(priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_queue_next_attempt ON request_queue(next_attempt_at);
                CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at);
                CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
            """)

            # Migrate existing database schema
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Add missing columns to existing tables."""
        cursor = conn.cursor()

        # Check if columns exist and add them if missing
        cursor.execute("PRAGMA table_info(request_queue)")
        columns = {row[1] for row in cursor.fetchall()}

        migrations = [
            ("started_at", "ALTER TABLE request_queue ADD COLUMN started_at TIMESTAMP"),
            ("completed_at", "ALTER TABLE request_queue ADD COLUMN completed_at TIMESTAMP"),
            ("exit_code", "ALTER TABLE request_queue ADD COLUMN exit_code INTEGER"),
        ]

        for col_name, alter_sql in migrations:
            if col_name not in columns:
                try:
                    cursor.execute(alter_sql)
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Column already exists

    def _update_health_check(self) -> None:
        """Aktualisiert die Health-Check-Datei."""
        self._health_check_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._health_check_path, "w") as f:
            f.write(datetime.now().isoformat())

    def enqueue(
        self,
        request: Request,
        user: str = "",
        add_default_reminders: bool = True
    ) -> str:
        """
        Fügt einen Request zur Queue hinzu.

        Args:
            request: Request-Objekt
            user: Benutzer, der den Request hinzufügt
            add_default_reminders: Füge Standard-Erinnerungen hinzu

        Returns:
            req_id des Requests
        """
        # Speichere Request in Queue
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO request_queue
                (req_id, payload, priority, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (request.req_id, request.to_json(), request.priority)
            )

            # Füge Standard-Erinnerungen hinzu (falls gewünscht)
            if add_default_reminders:
                # Erinnerungen für Timeout/Blockierung
                self._add_reminder(
                    conn,
                    request.req_id,
                    user,
                    f"Request {request.req_id} (Tool: {request.tool_name}) läuft seit 1 Stunde in der Queue.",
                    datetime.now() + timedelta(hours=1)
                )
                self._add_reminder(
                    conn,
                    request.req_id,
                    user,
                    f"Request {request.req_id} (Tool: {request.tool_name}) läuft seit 24 Stunden in der Queue!",
                    datetime.now() + timedelta(hours=24)
                )

        self._update_health_check()
        return request.req_id

    def _add_reminder(
        self,
        conn: sqlite3.Connection,
        req_id: str,
        user: str,
        message: str,
        due_at: datetime
    ) -> None:
        """Fügt eine Erinnerung zur Datenbank hinzu (interne Methode)."""
        conn.execute(
            """
            INSERT INTO reminders (req_id, user, message, due_at)
            VALUES (?, ?, ?, ?)
            """,
            (req_id, user, message, due_at.isoformat())
        )

    def dequeue(self) -> Optional[Request]:
        """
        Holt den nächsten Request aus der Queue (FIFO mit Priorität).

        Returns:
            Request-Objekt oder None, falls Queue leer
        """
        with sqlite3.connect(self.db_path) as conn:
            # Finde nächsten Request (höchste Priorität, dann ältesten)
            row = conn.execute(
                """
                SELECT req_id, payload FROM request_queue
                WHERE status = 'pending'
                AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """
            ).fetchone()

            if row:
                req_id, payload = row
                # Markiere als "running"
                conn.execute(
                    """
                    UPDATE request_queue
                    SET status = 'running',
                        updated_at = CURRENT_TIMESTAMP,
                        started_at = CURRENT_TIMESTAMP
                    WHERE req_id = ?
                    """,
                    (req_id,)
                )
                self._update_health_check()
                return Request.from_json(payload)

        return None

    def complete(self, req_id: str, exit_code: int = 0) -> None:
        """
        Markiert einen Request als erfolgreich abgeschlossen.

        Args:
            req_id: Request-ID
            exit_code: Exit-Code des Requests
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE request_queue
                SET status = 'completed',
                    exit_code = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE req_id = ?
                """,
                (exit_code, req_id)
            )
            # Erinnerungen für diesen Request als "cancelled" markieren
            conn.execute(
                "UPDATE reminders SET status = 'cancelled' WHERE req_id = ?",
                (req_id,)
            )
        self._update_health_check()

    def fail(
        self,
        req_id: str,
        error: str,
        retries: int = None,
        next_attempt_delay: timedelta = timedelta(minutes=5)
    ) -> None:
        """
        Markiert einen Request als fehlgeschlagen und plant ggf. einen neuen Versuch.

        Args:
            req_id: Request-ID
            error: Fehlermeldung
            retries: Anzahl der bisherigen Versuche (None = automatisch inkrementieren)
            next_attempt_delay: Verzögerung bis zum nächsten Versuch
        """
        with sqlite3.connect(self.db_path) as conn:
            # Aktuelle Versuche abfragen
            if retries is None:
                row = conn.execute(
                    "SELECT retries FROM request_queue WHERE req_id = ?",
                    (req_id,)
                ).fetchone()
                retries = row[0] + 1 if row else 0

            next_attempt = None
            if retries < 3:  # Maximal 3 Versuche
                next_attempt = datetime.now() + next_attempt_delay

            conn.execute(
                """
                UPDATE request_queue
                SET status = 'failed',
                    retries = ?,
                    next_attempt_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE req_id = ?
                """,
                (retries, next_attempt.isoformat() if next_attempt else None, req_id)
            )

            # Erinnerungen für Fehler hinzufügen
            if retries >= 3:  # Endgültiges Scheitern
                self._add_reminder(
                    conn,
                    req_id,
                    "system",
                    f"Request {req_id} gescheitert nach 3 Versuchen: {error[:100]}",
                    datetime.now()
                )
            else:  # Wird neu versucht
                self._add_reminder(
                    conn,
                    req_id,
                    "system",
                    f"Request {req_id} wird neu versucht (Versuch {retries + 1}/3). Fehler: {error[:50]}",
                    datetime.now() + next_attempt_delay
                )
        self._update_health_check()

    def timeout(self, req_id: str) -> None:
        """
        Markiert einen Request als Timeout.

        Args:
            req_id: Request-ID
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE request_queue
                SET status = 'timeout',
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP
                WHERE req_id = ?
                """,
                (req_id,)
            )
            # Sofortige Erinnerung
            self._add_reminder(
                conn,
                req_id,
                "system",
                f"Request {req_id} Timeout nach 20 Sekunden!",
                datetime.now()
            )
        self._update_health_check()

    def requeue_failed(self) -> None:
        """
        Setzt alle fehlgeschlagenen Requests mit next_attempt_at <= jetzt zurück auf "pending".
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE request_queue
                SET status = 'pending'
                WHERE status = 'failed'
                AND next_attempt_at <= CURRENT_TIMESTAMP
                """
            )
        self._update_health_check()

    def get_status(self) -> QueueStatus:
        """
        Gibt den aktuellen Status der Queue zurück.

        Returns:
            QueueStatus-Objekt
        """
        with sqlite3.connect(self.db_path) as conn:
            # Zähle Requests nach Status
            status_counts = {
                "pending": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "timeout": 0
            }
            for status in status_counts.keys():
                count = conn.execute(
                    f"SELECT COUNT(*) FROM request_queue WHERE status = '{status}'"
                ).fetchone()[0]
                status_counts[status] = count

            # Nächster Request (falls vorhanden)
            row = conn.execute(
                """
                SELECT req_id, priority, created_at FROM request_queue
                WHERE status = 'pending'
                AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """
            ).fetchone()

            next_request = None
            if row:
                next_request = {
                    "req_id": row[0],
                    "priority": row[1],
                    "created_at": row[2]
                }

            return QueueStatus(
                pending=status_counts["pending"],
                running=status_counts["running"],
                completed=status_counts["completed"],
                failed=status_counts["failed"],
                timeout=status_counts["timeout"],
                next_request=next_request
            )

    def get_request(self, req_id: str) -> Optional[Request]:
        """
        Lädt einen Request aus der Queue.

        Args:
            req_id: Request-ID

        Returns:
            Request-Objekt oder None
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload FROM request_queue WHERE req_id = ?",
                (req_id,)
            ).fetchone()
            if row:
                return Request.from_json(row[0])
        return None

    def list_requests(
        self,
        status: str = None,
        limit: int = 100
    ) -> list[Request]:
        """
        Listet Requests nach Status.

        Args:
            status: Status-Filter (z. B. "pending")
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von Request-Objekten
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT req_id, payload FROM request_queue"
            params = []

            if status:
                query += " WHERE status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [Request.from_json(row[1]) for row in rows]

    def cleanup(self, older_than_days: int = 7) -> int:
        """
        Löscht abgeschlossene Requests, die älter als X Tage sind.

        Args:
            older_than_days: Alter in Tagen

        Returns:
            Anzahl der gelöschten Requests
        """
        cutoff = datetime.now() - timedelta(days=older_than_days)
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute(
                """
                DELETE FROM request_queue
                WHERE status IN ('completed', 'failed', 'timeout')
                AND completed_at < ?
                """,
                (cutoff.isoformat(),)
            ).rowcount
        self._update_health_check()
        return deleted
