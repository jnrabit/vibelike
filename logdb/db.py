"""Log-Datenbank für das Vibelike-System."""

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from vibelike.models.request import Request


class LogDB:
    """Verwaltet die Log-Datenbank für Requests."""

    def __init__(self, db_path: str = "/vibelike/logs/execution.db"):
        """
        Initialisiert die Log-Datenbank.

        Args:
            db_path: Pfad zur SQLite-Datenbank
        """
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Erstellt die Tabellen, falls nicht vorhanden."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                    req_id TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    duration_ms INTEGER,
                    exit_code INTEGER,
                    user TEXT,
                    comment TEXT,
                    sandbox_path TEXT,
                    host_results_path TEXT
                );

                CREATE TABLE IF NOT EXISTS request_inputs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    req_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    sandbox_path TEXT NOT NULL,
                    size_bytes INTEGER,
                    sha256 TEXT,
                    FOREIGN KEY (req_id) REFERENCES requests(req_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS request_outputs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    req_id TEXT NOT NULL,
                    sandbox_path TEXT NOT NULL,
                    host_path TEXT NOT NULL,
                    size_bytes INTEGER,
                    sha256 TEXT,
                    FOREIGN KEY (req_id) REFERENCES requests(req_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    req_id TEXT NOT NULL,
                    stream TEXT NOT NULL,
                    content TEXT,
                    truncated BOOLEAN DEFAULT 0,
                    FOREIGN KEY (req_id) REFERENCES requests(req_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS request_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    req_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    FOREIGN KEY (req_id) REFERENCES requests(req_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_requests_req_id ON requests(req_id);
                CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
                CREATE INDEX IF NOT EXISTS idx_requests_tool ON requests(tool);
                CREATE INDEX IF NOT EXISTS idx_requests_created ON requests(created_at);
                CREATE INDEX IF NOT EXISTS idx_inputs_req_id ON request_inputs(req_id);
                CREATE INDEX IF NOT EXISTS idx_outputs_req_id ON request_outputs(req_id);
            """)

    def log_request(self, request: Request, sandbox_path: Path = None, host_results_path: Path = None) -> None:
        """
        Speichert einen Request in der Log-Datenbank.

        Args:
            request: Request-Objekt
            sandbox_path: Pfad zur Sandbox (optional)
            host_results_path: Pfad zu den Ergebnissen auf dem Host (optional)
        """
        with sqlite3.connect(self.db_path) as conn:
            # Request speichern
            conn.execute(
                """
                INSERT OR REPLACE INTO requests
                (req_id, tool, operation, status, priority, created_at, started_at, completed_at,
                 duration_ms, exit_code, user, comment, sandbox_path, host_results_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.req_id,
                    request.tool_name,
                    request.operation,
                    request.status,
                    request.priority,
                    request.created_at.isoformat() if request.created_at else None,
                    request.started_at.isoformat() if request.started_at else None,
                    request.completed_at.isoformat() if request.completed_at else None,
                    request.duration_ms,
                    request.exit_code,
                    request.user,
                    request.comment,
                    str(sandbox_path) if sandbox_path else None,
                    str(host_results_path) if host_results_path else None
                )
            )

            # Input-Dateien speichern
            for input_file in request.input_files:
                conn.execute(
                    """
                    INSERT INTO request_inputs
                    (req_id, source_path, sandbox_path, size_bytes, sha256)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        request.req_id,
                        str(input_file),
                        f"/workspace/input/{input_file.name}",
                        input_file.stat().st_size if input_file.exists() else None,
                        self._compute_sha256(input_file) if input_file.exists() else None
                    )
                )

            # Output-Dateien speichern
            for output_file in request.output_files:
                conn.execute(
                    """
                    INSERT INTO request_outputs
                    (req_id, sandbox_path, host_path, size_bytes, sha256)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        request.req_id,
                        f"/workspace/output/{output_file.name}",
                        str(output_file),
                        output_file.stat().st_size if output_file.exists() else None,
                        self._compute_sha256(output_file) if output_file.exists() else None
                    )
                )

            # Logs speichern (stdout/stderr)
            if request.stdout:
                self._log_stream(conn, request.req_id, "stdout", request.stdout)
            if request.stderr:
                self._log_stream(conn, request.req_id, "stderr", request.stderr)

    def _log_stream(self, conn: sqlite3.Connection, req_id: str, stream: str, content: str) -> None:
        """
        Speichert einen Log-Stream (stdout/stderr) in der Datenbank.

        Args:
            conn: SQLite-Connection
            req_id: Request-ID
            stream: "stdout" oder "stderr"
            content: Inhalt des Streams
        """
        # Trunkieren, falls zu lang (>1MB)
        truncated = False
        if len(content) > 1_000_000:
            content = content[:1_000_000] + "\n... [TRUNCATED]"
            truncated = True

        conn.execute(
            """
            INSERT INTO request_logs (req_id, stream, content, truncated)
            VALUES (?, ?, ?, ?)
            """,
            (req_id, stream, content, truncated)
        )

    def log_metric(self, req_id: str, key: str, value: Any) -> None:
        """
        Speichert eine Metrik für einen Request.

        Args:
            req_id: Request-ID
            key: Name der Metrik
            value: Wert der Metrik (wird zu JSON serialisiert)
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO request_metrics (req_id, key, value)
                VALUES (?, ?, ?)
                """,
                (req_id, key, json.dumps(value))
            )

    def get_request(self, req_id: str) -> Optional[Request]:
        """
        Lädt einen Request aus der Datenbank.

        Args:
            req_id: Request-ID

        Returns:
            Request-Objekt oder None
        """
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE req_id = ?",
                (req_id,)
            ).fetchone()

            if not row:
                return None

            request_data = {
                "req_id": row[0],
                "tool_name": row[1],
                "operation": row[2],
                "status": row[3],
                "priority": row[4],
                "created_at": datetime.fromisoformat(row[5]) if row[5] else None,
                "started_at": datetime.fromisoformat(row[6]) if row[6] else None,
                "completed_at": datetime.fromisoformat(row[7]) if row[7] else None,
                "duration_ms": row[8],
                "exit_code": row[9],
                "user": row[10],
                "comment": row[11],
            }

            # Input-Dateien laden
            input_rows = conn.execute(
                "SELECT source_path FROM request_inputs WHERE req_id = ?",
                (req_id,)
            ).fetchall()
            request_data["input_files"] = [Path(r[0]) for r in input_rows]

            # Output-Dateien laden
            output_rows = conn.execute(
                "SELECT host_path FROM request_outputs WHERE req_id = ?",
                (req_id,)
            ).fetchall()
            request_data["output_files"] = [Path(r[0]) for r in output_rows]

            # Logs laden
            for stream in ["stdout", "stderr"]:
                log_row = conn.execute(
                    "SELECT content FROM request_logs WHERE req_id = ? AND stream = ?",
                    (req_id, stream)
                ).fetchone()
                if log_row:
                    request_data[stream] = log_row[0]

            return Request.from_dict(request_data)

    def query_requests(
        self,
        status: str = None,
        tool: str = None,
        since: datetime = None,
        limit: int = 100
    ) -> list[Request]:
        """
        Sucht Requests nach Kriterien.

        Args:
            status: Status-Filter (z. B. "completed")
            tool: Tool-Filter
            since: Nur Requests nach diesem Datum
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von Request-Objekten
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT req_id FROM requests WHERE 1=1"
            params = []

            if status:
                query += " AND status = ?"
                params.append(status)
            if tool:
                query += " AND tool = ?"
                params.append(tool)
            if since:
                query += " AND created_at >= ?"
                params.append(since.isoformat())

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            return [self.get_request(row[0]) for row in rows if row[0]]

    def rotate(self, older_than_days: int = 30) -> int:
        """
        Archiviert Requests, die älter als X Tage sind.

        Args:
            older_than_days: Alter in Tagen

        Returns:
            Anzahl der archivierten Requests
        """
        cutoff = datetime.now() - timedelta(days=older_than_days)
        archived_count = 0

        with sqlite3.connect(self.db_path) as conn:
            # Erstelle Archiv-Datenbank
            archive_db = self.db_path.parent / f"archive/execution_{cutoff.date()}.db"
            archive_db.parent.mkdir(parents=True, exist_ok=True)

            # Kopiere alte Requests in Archiv
            conn.execute(
                f"ATTACH DATABASE '{archive_db}' AS archive"
            )
            conn.execute(
                """
                INSERT INTO archive.requests
                SELECT * FROM requests
                WHERE created_at < ?
                """,
                (cutoff.isoformat(),)
            )
            conn.execute(
                """
                INSERT INTO archive.request_inputs
                SELECT * FROM request_inputs
                WHERE req_id IN (
                    SELECT req_id FROM requests WHERE created_at < ?
                )
                """,
                (cutoff.isoformat(),)
            )
            conn.execute(
                """
                INSERT INTO archive.request_outputs
                SELECT * FROM request_outputs
                WHERE req_id IN (
                    SELECT req_id FROM requests WHERE created_at < ?
                )
                """,
                (cutoff.isoformat(),)
            )
            conn.execute(
                """
                INSERT INTO archive.request_logs
                SELECT * FROM request_logs
                WHERE req_id IN (
                    SELECT req_id FROM requests WHERE created_at < ?
                )
                """,
                (cutoff.isoformat(),)
            )
            conn.execute(
                """
                INSERT INTO archive.request_metrics
                SELECT * FROM request_metrics
                WHERE req_id IN (
                    SELECT req_id FROM requests WHERE created_at < ?
                )
                """,
                (cutoff.isoformat(),)
            )

            # Lösche aus Haupt-DB
            deleted = conn.execute(
                """
                DELETE FROM requests
                WHERE created_at < ?
                """,
                (cutoff.isoformat(),)
            ).rowcount
            archived_count = deleted

        return archived_count

    def _compute_sha256(self, file_path: Path) -> Optional[str]:
        """Berechnet den SHA256-Hash einer Datei."""
        if not file_path.exists():
            return None

        import hashlib
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
