"""Reminder-Manager für das Vibelike-System."""

import json
import smtplib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional


@dataclass
class Reminder:
    """Repräsentiert eine Erinnerung."""
    id: int
    req_id: str
    user: str
    message: str
    due_at: datetime
    status: str  # "pending" | "sent" | "cancelled"
    sent_at: Optional[datetime]


class ReminderManager:
    """Verwaltet Erinnerungen für Requests."""

    def __init__(
        self,
        db_path: str = "/vibelike/logs/queue.db",
        smtp_config: Optional[dict] = None,
        cli_notify: bool = True
    ):
        """
        Initialisiert den Reminder-Manager.

        Args:
            db_path: Pfad zur SQLite-Datenbank (geteilt mit RequestQueue)
            smtp_config: Konfiguration für E-Mail-Benachrichtigungen:
                {
                    "host": "smtp.example.com",
                    "port": 587,
                    "user": "user@example.com",
                    "password": "password",
                    "from_addr": "vibelike@example.com"
                }
            cli_notify: Benachrichtigungen über CLI (notify-send) aktivieren
        """
        self.db_path = Path(db_path)
        self.smtp_config = smtp_config
        self.cli_notify = cli_notify

    def add_reminder(
        self,
        req_id: str,
        user: str,
        message: str,
        due_at: datetime
    ) -> int:
        """
        Fügt eine neue Erinnerung hinzu.

        Args:
            req_id: Request-ID
            user: Benutzer für die Erinnerung
            message: Erinnerungsnachricht
            due_at: Zeitpunkt, zu dem erinnert werden soll

        Returns:
            ID der Erinnerung
        """
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO reminders (req_id, user, message, due_at)
                VALUES (?, ?, ?, ?)
                """,
                (req_id, user, message, due_at.isoformat())
            )
            return cursor.lastrowid

    def get_pending_reminders(self) -> list[Reminder]:
        """
        Gibt alle fälligen Erinnerungen zurück.

        Returns:
            Liste von Reminder-Objekten
        """
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.now().isoformat()
            rows = conn.execute(
                """
                SELECT id, req_id, user, message, due_at, status, sent_at
                FROM reminders
                WHERE due_at <= ? AND status = 'pending'
                """,
                (now,)
            ).fetchall()

            return [
                Reminder(
                    id=row[0],
                    req_id=row[1],
                    user=row[2],
                    message=row[3],
                    due_at=datetime.fromisoformat(row[4]),
                    status=row[5],
                    sent_at=datetime.fromisoformat(row[6]) if row[6] else None
                )
                for row in rows
            ]

    def mark_sent(self, reminder_id: int) -> None:
        """
        Markiert eine Erinnerung als gesendet.

        Args:
            reminder_id: ID der Erinnerung
        """
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE reminders
                SET status = 'sent', sent_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (reminder_id,)
            )

    def check_and_send(self) -> int:
        """
        Prüft auf fällige Erinnerungen und sendet Benachrichtigungen.

        Returns:
            Anzahl der gesendeten Erinnerungen
        """
        reminders = self.get_pending_reminders()
        sent_count = 0

        for reminder in reminders:
            self._send_notification(reminder)
            self.mark_sent(reminder.id)
            sent_count += 1

        return sent_count

    def _send_notification(self, reminder: Reminder) -> None:
        """
        Sendet eine Benachrichtigung für eine Erinnerung.

        Args:
            reminder: Reminder-Objekt
        """
        # 1. CLI-Benachrichtigung (notify-send)
        if self.cli_notify:
            self._send_cli_notification(reminder)

        # 2. E-Mail-Benachrichtigung (falls konfiguriert)
        if self.smtp_config and "@" in reminder.user:
            self._send_email_notification(reminder)

        # 3. Log-Eintrag (immer)
        self._log_reminder(reminder)

    def _send_cli_notification(self, reminder: Reminder) -> None:
        """Sendet eine Benachrichtigung über notify-send."""
        try:
            summary = f"Vibelike: Request {reminder.req_id}"
            body = f"User: {reminder.user}\nMessage: {reminder.message}"
            subprocess.run(
                ["notify-send", summary, body],
                capture_output=True
            )
        except:
            pass  # Ignoriere Fehler (z. B. wenn notify-send nicht verfügbar)

    def _send_email_notification(self, reminder: Reminder) -> None:
        """Sendet eine E-Mail-Benachrichtigung."""
        if not self.smtp_config:
            return

        try:
            msg = MIMEText(reminder.message)
            msg["Subject"] = f"Vibelike Reminder: Request {reminder.req_id}"
            msg["From"] = self.smtp_config["from_addr"]
            msg["To"] = reminder.user

            with smtplib.SMTP(
                self.smtp_config["host"],
                self.smtp_config["port"]
            ) as server:
                if "user" in self.smtp_config:
                    server.starttls()
                    server.login(
                        self.smtp_config["user"],
                        self.smtp_config["password"]
                    )
                server.send_message(msg)
        except Exception as e:
            import logging
            logging.error(f"Failed to send email reminder: {e}")

    def _log_reminder(self, reminder: Reminder) -> None:
        """Schreibt die Erinnerung in die Log-Datei."""
        log_dir = Path("/vibelike/logs/reminders")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{datetime.now().date()}.log"

        with open(log_file, "a") as f:
            f.write(
                json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "reminder_id": reminder.id,
                    "req_id": reminder.req_id,
                    "user": reminder.user,
                    "message": reminder.message,
                    "due_at": reminder.due_at.isoformat(),
                    "status": "sent"
                }) + "\n"
            )

    def cleanup(self, older_than_days: int = 30) -> int:
        """
        Löscht alte Erinnerungen.

        Args:
            older_than_days: Alter in Tagen

        Returns:
            Anzahl der gelöschten Erinnerungen
        """
        import sqlite3
        cutoff = datetime.now() - timedelta(days=older_than_days)
        with sqlite3.connect(self.db_path) as conn:
            deleted = conn.execute(
                """
                DELETE FROM reminders
                WHERE status = 'sent' AND sent_at < ?
                """,
                (cutoff.isoformat(),)
            ).rowcount
        return deleted
