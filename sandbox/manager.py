"""Sandbox-Manager für das Vibelike-System."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from vibelike.sandbox.models import Sandbox
from vibelike.tools.registry import ToolRegistry
from vibelike.tools.cache import ToolCache


class SandboxManager:
    """Verwaltet das Erstellen und Zerstören von Sandboxen."""

    def __init__(
        self,
        sandbox_base: Path = Path("/sandbox"),
        tools_dir: Path = Path("/host/tools"),
        user_uid: int = 10000,
        user_gid: int = 10000,
        cache: Optional[ToolCache] = None
    ):
        """
        Initialisiert den Sandbox-Manager.

        Args:
            sandbox_base: Basisverzeichnis für Sandboxen
            tools_dir: Verzeichnis mit den Tools
            user_uid: User-ID für Sandbox-Prozesse
            user_gid: Group-ID für Sandbox-Prozesse
            cache: Optional: ToolCache-Instanz
        """
        self.sandbox_base = Path(sandbox_base)
        self.tools_dir = tools_dir
        self.user_uid = user_uid
        self.user_gid = user_gid
        self.tool_registry = ToolRegistry(tools_dir=tools_dir, cache=cache)
        self.cache = cache or ToolCache()
        self.active_sandboxes: dict[str, Sandbox] = {}  # req_id → Sandbox

        # Erstelle Basisverzeichnis
        self.sandbox_base.mkdir(parents=True, exist_ok=True)

    def create(self, req_id: str, tool_name: str) -> Sandbox:
        """
        Erstellt eine neue Sandbox für einen Request.

        Args:
            req_id: Unique Request-ID
            tool_name: Name des Tools

        Returns:
            Sandbox-Objekt

        Raises:
            ValueError: Falls Sandbox nicht erstellt werden kann
        """
        # Prüfe, ob req_id bereits existiert
        if req_id in self.active_sandboxes:
            raise ValueError(f"Sandbox for request {req_id} already exists")

        # Tool auflösen
        try:
            tool = self.tool_registry.resolve(tool_name)
        except ValueError as e:
            raise ValueError(f"Cannot resolve tool: {e}")

        # Sandbox-Verzeichnis erstellen
        sandbox_path = self.sandbox_base / req_id
        if sandbox_path.exists():
            shutil.rmtree(sandbox_path)

        sandbox = Sandbox(
            req_id=req_id,
            path=sandbox_path,
            user_uid=self.user_uid,
            user_gid=self.user_gid
        )

        # Sandbox vorbereiten
        with sandbox:
            # Tools + Abhängigkeiten mounten
            self._mount_tool_and_dependencies(sandbox, tool)

        self.active_sandboxes[req_id] = sandbox
        return sandbox

    def _mount_tool_and_dependencies(self, sandbox: Sandbox, tool: Tool) -> None:
        """
        Mountet ein Tool und alle seine Abhängigkeiten in die Sandbox.

        Args:
            sandbox: Sandbox-Objekt
            tool: Tool-Objekt
        """
        # Tool selbst mounten
        source = tool.cached_path if tool.cached_path else tool.path
        sandbox.mount_tool(source, tool.name)

        # Abhängigkeiten mounten
        try:
            deps = self.tool_registry.get_dependencies(tool.name)
        except ValueError as e:
            # Zirkuläre Abhängigkeit – loggen und ignorieren
            import logging
            logging.error(f"Circular dependency for {tool.name}: {e}")
            deps = []

        for dep in deps:
            dep_source = dep.cached_path if dep.cached_path else dep.path
            sandbox.mount_tool(dep_source, dep.name)

    def destroy(self, req_id: str) -> None:
        """
        Zerstört eine Sandbox.

        Args:
            req_id: Request-ID der Sandbox
        """
        if req_id not in self.active_sandboxes:
            return

        sandbox = self.active_sandboxes.pop(req_id)
        sandbox.destroy()

    def destroy_all(self) -> None:
        """Zerstört alle aktiven Sandboxen."""
        for req_id in list(self.active_sandboxes.keys()):
            self.destroy(req_id)

    def get(self, req_id: str) -> Optional[Sandbox]:
        """Gibt eine Sandbox zurück oder None, falls nicht gefunden."""
        return self.active_sandboxes.get(req_id)

    def cleanup(self) -> None:
        """Bereinigt alte Sandbox-Verzeichnisse (für den Fall eines Crashes)."""
        for sandbox_dir in self.sandbox_base.iterdir():
            if sandbox_dir.name.startswith("."):
                continue

            # Prüfe, ob die Sandbox noch aktiv ist
            req_id = sandbox_dir.name
            if req_id not in self.active_sandboxes:
                try:
                    # Versuche, Mounts zu entfernen
                    self._force_cleanup(sandbox_dir)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to cleanup sandbox {req_id}: {e}")

    def _force_cleanup(self, sandbox_path: Path) -> None:
        """
        Erzwingt das Aufräumen einer Sandbox (auch bei hängenden Mounts).

        Args:
            sandbox_path: Pfad zur Sandbox
        """
        # Versuche, Mounts zu entfernen
        try:
            subprocess.run(["umount", "-R", str(sandbox_path)], capture_output=True)
        except:
            pass

        # Versuche, Prozesse zu töten
        try:
            subprocess.run(["pkill", "-9", "-f", str(sandbox_path)], capture_output=True)
        except:
            pass

        # Lösche das Verzeichnis
        try:
            shutil.rmtree(sandbox_path, ignore_errors=True)
        except:
            pass
