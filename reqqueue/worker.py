"""Request-Worker für die sequentielle Abarbeitung von Requests."""

import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from vibelike.models.request import Request
from vibelike.sandbox.manager import SandboxManager
from vibelike.tools.registry import ToolRegistry
from vibelike.tools.cache import ToolCache
from vibelike.reqqueue.manager import RequestQueue
from vibelike.reqqueue.reminders import ReminderManager
from vibelike.reqqueue.health import HealthCheck
from vibelike.logdb.db import LogDB
from ossifikat.store import OssifikatStore


class RequestWorker:
    """Verarbeitet Requests sequentiell aus der Queue."""

    def __init__(
        self,
        queue_db_path: str = "/vibelike/logs/queue.db",
        log_db_path: str = "/vibelike/logs/execution.db",
        ossifikat_db_path: str = "/vibelike/ossifikat/data/ossifikat.db",
        tools_dir: Path = Path("/host/tools"),
        results_dir: Path = Path("/host/results"),
        smtp_config: Optional[dict] = None
    ):
        """
        Initialisiert den Request-Worker.

        Args:
            queue_db_path: Pfad zur Queue-Datenbank
            log_db_path: Pfad zur Log-Datenbank
            ossifikat_db_path: Pfad zur ossifikat-Datenbank
            tools_dir: Verzeichnis mit den Tools
            results_dir: Verzeichnis für Ergebnisse
            smtp_config: SMTP-Konfiguration für E-Mail-Benachrichtigungen
        """
        # Initialisiere Komponenten
        self.queue = RequestQueue(queue_db_path)
        self.log_db = LogDB(log_db_path)
        self.ossifikat_store = OssifikatStore(ossifikat_db_path)  # Feste Connection!
        self.sandbox_manager = SandboxManager(
            sandbox_base=Path("/sandbox"),
            tools_dir=tools_dir,
            cache=ToolCache()
        )
        self.tool_registry = ToolRegistry(tools_dir=tools_dir)
        self.reminder_manager = ReminderManager(
            db_path=queue_db_path,
            smtp_config=smtp_config
        )
        self.health_check = HealthCheck(queue_db_path=queue_db_path)
        self.results_dir = results_dir
        self.running = False

        # Signal-Handler für sauberes Beenden
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame) -> None:
        """Behandelt Signale für sauberes Beenden."""
        print(f"Received signal {signum}, shutting down...")
        self.stop()

    def start(self) -> None:
        """Startet den Worker (blockierend)."""
        self.running = True
        self.health_check.update()  # Aktualisiere Health-Check

        print("RequestWorker started. Waiting for requests...")

        while self.running:
            try:
                # Health-Check alle 30 Sekunden
                if not self._check_health():
                    self._recover_from_failure()

                # Request aus Queue holen
                request = self.queue.dequeue()
                if request is None:
                    # Keine Requests in Queue – warte 1 Sekunde
                    time.sleep(1)
                    continue

                # Request verarbeiten
                self._process_request(request)

            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                import traceback
                print(f"Error in worker: {e}")
                traceback.print_exc()
                # Warte 5 Sekunden, um nicht in einer Schleife zu hängen
                time.sleep(5)

        print("RequestWorker stopped.")

    def stop(self) -> None:
        """Stoppt den Worker."""
        self.running = False
        # Zerstöre alle aktiven Sandboxen
        self.sandbox_manager.destroy_all()
        # Schließe ossifikat-Connection
        self.ossifikat_store.close()
        self.health_check.update()  # Finaler Health-Check

    def _check_health(self) -> bool:
        """Führt einen Health-Check durch und aktualisiert die Datei."""
        status = self.health_check.check()
        if not status.is_healthy:
            print(f"Health check failed: {status.errors}")
            return False
        self.health_check.update()
        return True

    def _recover_from_failure(self) -> None:
        """Versucht, den Worker nach einem Fehler wiederherzustellen."""
        print("Attempting recovery...")
        self.sandbox_manager.destroy_all()
        self.queue.requeue_failed()
        self.health_check.force_recovery()
        self.health_check.update()

    def _process_request(self, request: Request) -> None:
        """
        Verarbeitet einen einzelnen Request.

        Args:
            request: Request-Objekt
        """
        sandbox = None
        tool = None
        host_results_path = self.results_dir / request.req_id
        host_results_path.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Status aktualisieren
            request.status = "running"
            request.started_at = datetime.now()

            # 2. Tool auflösen
            try:
                tool = self.tool_registry.resolve(request.tool_name)
            except ValueError as e:
                request.status = "failed"
                request.stderr = f"Tool not found: {e}"
                self._finalize_request(request, host_results_path, tool=None)
                return

            # 3. Sandbox erstellen
            try:
                sandbox = self.sandbox_manager.create(request.req_id, request.tool_name)
            except Exception as e:
                request.status = "failed"
                request.stderr = f"Sandbox creation failed: {e}"
                self._finalize_request(request, host_results_path, tool=tool)
                return

            # 4. Input-Dateien kopieren
            try:
                for input_file in request.input_files:
                    sandbox.copy_to_workspace(input_file)
            except Exception as e:
                request.status = "failed"
                request.stderr = f"Failed to copy input files: {e}"
                self._finalize_request(request, host_results_path, tool=tool, sandbox=sandbox)
                return

            # 5. Git-Repo mounten (falls angegeben)
            if request.git_project:
                git_path = Path(f"/vibelike/git/{request.git_project}.git")
                if git_path.exists():
                    try:
                        sandbox.mount_tool(git_path, "git", options=["ro"])
                    except Exception as e:
                        request.stderr = f"{request.stderr or ''}\nGit mount failed: {e}" if request.stderr else f"Git mount failed: {e}"

            # 6. Command ausführen
            try:
                # Command generieren (falls nicht vorgegeben)
                if not request.command:
                    command = self._build_command(request, tool)
                else:
                    command = request.command

                # Environment vorbereiten
                env = {**tool.env, **request.env}

                # Execution in Sandbox
                result = sandbox.execute(
                    command,
                    timeout=request.timeout,
                    env=env,
                    cwd=request.working_dir
                )

                # Ergebnisse speichern
                request.exit_code = result["exit_code"]
                request.stdout = result["stdout"]
                request.stderr = result["stderr"]
                request.duration_ms = result["duration_ms"]

                if result["timed_out"]:
                    request.status = "timeout"
                elif result["exit_code"] != 0:
                    request.status = "failed"
                else:
                    request.status = "completed"

            except Exception as e:
                request.status = "failed"
                request.stderr = f"{request.stderr or ''}\nExecution failed: {e}" if request.stderr else f"Execution failed: {e}"

            # 7. Output-Dateien kopieren
            if request.status in ["completed", "failed", "timeout"]:
                try:
                    # Kopiere alle Dateien aus /workspace/output
                    output_dir = sandbox.workspace_path / "output"
                    if output_dir.exists():
                        for output_file in output_dir.rglob("*"):
                            if output_file.is_file():
                                rel_path = output_file.relative_to(output_dir)
                                dest = host_results_path / "output" / rel_path
                                sandbox.copy_from_workspace(output_file, dest)
                                request.output_files.append(dest)
                except Exception as e:
                    request.stderr = f"{request.stderr or ''}\nFailed to copy output files: {e}" if request.stderr else f"Failed to copy output files: {e}"

            # 8. Logs speichern
            self.log_db.log_request(request, sandbox.path, host_results_path)

            # 9. Triples generieren und in ossifikat schreiben
            if tool:
                triples = request.generate_triples(
                    tool=tool,
                    exit_code=request.exit_code or -1,
                    output_files=request.output_files,
                    duration_ms=request.duration_ms or 0
                )
                for triple in triples:
                    try:
                        self.ossifikat_store.add_staging(
                            subject=triple["subject"],
                            predicate=triple["predicate"],
                            object=triple["object"],
                            source=triple["source"],
                            confidence=triple["confidence"]
                        )
                    except Exception as e:
                        import logging
                        logging.error(f"Failed to add triple to ossifikat: {e}")

            # 10. Queue aktualisieren
            if request.status == "completed":
                self.queue.complete(request.req_id, request.exit_code)
            elif request.status == "timeout":
                self.queue.timeout(request.req_id)
            else:
                self.queue.fail(request.req_id, request.stderr or "Unknown error", request.retries)

            request.completed_at = datetime.now()

        except Exception as e:
            # Falls etwas schiefgeht, das nicht abgedeckt ist
            request.status = "failed"
            request.stderr = f"{request.stderr or ''}\nUnexpected error: {e}" if request.stderr else f"Unexpected error: {e}"
            request.completed_at = datetime.now()
            self.queue.fail(request.req_id, request.stderr or "Unknown error", request.retries)
        finally:
            # Sandbox zerstören
            if sandbox:
                try:
                    self.sandbox_manager.destroy(request.req_id)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to destroy sandbox for {request.req_id}: {e}")

            # Health-Check aktualisieren
            self.health_check.update()

    def _build_command(self, request: Request, tool: Tool) -> str:
        """
        Baut den Ausführungskommando aus Request und Tool-Konfiguration.

        Args:
            request: Request-Objekt
            tool: Tool-Objekt

        Returns:
            Vollständiger Befehl als String
        """
        # Basis-Befehl: Tool-Binary + Argumente
        binary_path = tool.get_full_binary_path()
        command_parts = [str(binary_path.relative_to(tool.path))]

        # Füge Argumente hinzu
        command_parts.extend(request.args)

        # Füge Input-Dateien hinzu (falls nicht in args)
        if request.input_files and not any(
            str(input_file.name) in " ".join(request.args)
            for input_file in request.input_files
        ):
            for input_file in request.input_files:
                command_parts.append(f"/workspace/input/{input_file.name}")

        # Füge Output-Option hinzu (falls -o nicht in args)
        if "-o" not in request.args and "--output" not in request.args:
            command_parts.extend(["-o", "/workspace/output/a.out"])

        return " ".join(command_parts)

    def _finalize_request(
        self,
        request: Request,
        host_results_path: Path,
        tool: Optional[Tool] = None,
        sandbox: Optional[Sandbox] = None
    ) -> None:
        """
        Finalisiert einen Request bei vorzeitigem Abbruch.

        Args:
            request: Request-Objekt
            host_results_path: Pfad zu den Ergebnissen auf dem Host
            tool: Tool-Objekt (optional)
            sandbox: Sandbox-Objekt (optional)
        """
        request.completed_at = datetime.now()

        # Logs speichern
        self.log_db.log_request(request, sandbox.path if sandbox else None, host_results_path)

        # Triples generieren (auch bei Fehlern)
        if tool and request.status != "pending":
            triples = request.generate_triples(
                tool=tool,
                exit_code=request.exit_code or -1,
                output_files=request.output_files,
                duration_ms=request.duration_ms or 0
            )
            for triple in triples:
                try:
                    self.ossifikat_store.add_staging(
                        subject=triple["subject"],
                        predicate=triple["predicate"],
                        object=triple["object"],
                        source=triple["source"],
                        confidence=triple["confidence"]
                    )
                except Exception as e:
                    import logging
                    logging.error(f"Failed to add triple to ossifikat: {e}")

        # Queue aktualisieren
        if request.status == "failed":
            self.queue.fail(request.req_id, request.stderr or "Unknown error", request.retries)
        elif request.status == "timeout":
            self.queue.timeout(request.req_id)
