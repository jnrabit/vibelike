"""Datenmodelle für Sandbox und Mounts."""

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Mount:
    """Repräsentiert einen Mount in der Sandbox."""

    source: Path
    target: Path
    options: list[str] = field(default_factory=lambda: ["ro", "noexec", "nosuid", "nodev"])
    mounted: bool = False

    def mount(self) -> bool:
        """
        Mountet das Verzeichnis.

        Returns:
            True bei Erfolg, False bei Fehler
        """
        if self.mounted:
            return True

        try:
            cmd = [
                "mount", "--bind", str(self.source), str(self.target),
                "-o", ",".join(self.options)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            self.mounted = True
            return True
        except subprocess.CalledProcessError as e:
            # Bugreport bei Fehler
            self._send_bugreport(e, "mount_failed")
            return False

    def umount(self) -> bool:
        """
        Entmountet das Verzeichnis.

        Returns:
            True bei Erfolg, False bei Fehler
        """
        if not self.mounted:
            return True

        try:
            # Versuche, blockierende Prozesse zu finden
            if self._is_busy():
                self._kill_blocking_processes()

            cmd = ["umount", str(self.target)]
            subprocess.run(cmd, check=True, capture_output=True)
            self.mounted = False
            return True
        except subprocess.CalledProcessError as e:
            self._send_bugreport(e, "umount_failed")
            return False

    def _is_busy(self) -> bool:
        """Prüft, ob der Mount-Punkt beschäftigt ist."""
        try:
            result = subprocess.run(
                ["lsof", "+D", str(self.target)],
                capture_output=True, text=True
            )
            return bool(result.stdout.strip())
        except:
            return False

    def _kill_blocking_processes(self) -> None:
        """Tötet Prozesse, die den Mount-Punkt blockieren."""
        try:
            result = subprocess.run(
                ["lsof", "-t", "+D", str(self.target)],
                capture_output=True, text=True
            )
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                if pid.strip():
                    subprocess.run(["kill", "-9", pid], capture_output=True)
        except:
            pass

    def _send_bugreport(self, error: Exception, error_type: str) -> None:
        """
        Sendet einen Bugreport mit Fehlerdetails.

        Args:
            error: Die aufgetretene Exception
            error_type: Typ des Fehlers (z. B. "mount_failed")
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "source": str(self.source),
            "target": str(self.target),
            "options": self.options,
            "error": str(error),
            "stdout": getattr(error, "stdout", ""),
            "stderr": getattr(error, "stderr", ""),
            "workaround": self._get_workaround(error_type)
        }

        # Speichere in Log-Verzeichnis
        log_dir = Path("/vibelike/logs/bugreports")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{error_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        import json
        with open(log_file, "w") as f:
            json.dump(report, f, indent=2)

    def _get_workaround(self, error_type: str) -> str:
        """Gibt einen kurzen Workaround für den Fehler zurück."""
        workarounds = {
            "mount_failed": "Prüfe, ob das Quellverzeichnis existiert und lesbar ist. Falls ja: 'mount -o remount,ro /' ausführen und neu versuchen.",
            "umount_failed": "Führe 'lsof +D <target>' aus, um blockierende Prozesse zu finden. Töte sie mit 'kill -9 <pid>'.",
            "target_busy": "Warte 5 Sekunden und versuche es erneut. Falls Fehler persistiert: System neu starten."
        }
        return workarounds.get(error_type, "Unbekannter Fehler. Prüfe System-Logs.")


@dataclass
class Sandbox:
    """Repräsentiert eine isolierte Sandbox für einen Request."""

    req_id: str
    path: Path
    workspace_path: Path
    tools_path: Path
    git_path: Path
    user_uid: int = 10000
    user_gid: int = 10000
    mounts: list[Mount] = field(default_factory=list)
    pid: Optional[int] = None
    status: str = "created"
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Initialisiert die Pfade."""
        self.path = Path(self.path)
        self.workspace_path = self.path / "workspace"
        self.tools_path = self.path / "tools"
        self.git_path = self.path / "git"

    def __enter__(self):
        """Kontextmanager: Erstellt die Sandbox."""
        self._setup_tmpfs()
        self.status = "ready"
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Kontextmanager: Zerstört die Sandbox."""
        self.destroy()
        return False  # Exceptions weiterleiten

    def _setup_tmpfs(self) -> None:
        """Mountet tmpfs für den Workspace."""
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [
                    "mount", "-t", "tmpfs", "-o",
                    f"size=100M,noexec,nosuid,nodev,mode=0700,uid={self.user_uid},gid={self.user_gid}",
                    "tmpfs", str(self.workspace_path)
                ],
                check=True, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            # Falls tmpfs nicht verfügbar, versuche mit normalem Verzeichnis
            if "tmpfs" in str(e.stderr):
                self._fallback_to_normal_dir()
            else:
                raise

    def _fallback_to_normal_dir(self) -> None:
        """Fallback zu normalem Verzeichnis, falls tmpfs nicht funktioniert."""
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        os.chmod(self.workspace_path, 0o700)
        os.chown(self.workspace_path, self.user_uid, self.user_gid)

    def mount_tool(self, source: Path, target_name: str, options: list[str] = None) -> Mount:
        """
        Mountet ein Tool in die Sandbox.

        Args:
            source: Quellpfad auf dem Host
            target_name: Name des Zielverzeichnisses (z. B. "gcc-13")
            options: Mount-Optionen (Default: ro,noexec,nosuid,nodev)

        Returns:
            Mount-Objekt
        """
        if options is None:
            options = ["ro", "noexec", "nosuid", "nodev"]

        target = self.tools_path / target_name
        mount = Mount(source=source, target=target, options=options)
        if mount.mount():
            self.mounts.append(mount)
            return mount
        else:
            raise RuntimeError(f"Failed to mount {source} to {target}")

    def umount_all(self) -> None:
        """Entmountet alle Mounts in umgekehrter Reihenfolge."""
        for mount in reversed(self.mounts):
            mount.umount()
        self.mounts.clear()

    def copy_to_workspace(self, src: Path, dst: Path = None) -> Path:
        """
        Kopiert eine Datei in den Workspace.

        Args:
            src: Quellpfad (Host)
            dst: Zielpfad (relativ zum Workspace). Default: src.name

        Returns:
            Vollständiger Pfad im Workspace
        """
        if dst is None:
            dst = self.workspace_path / src.name
        else:
            dst = self.workspace_path / dst

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        os.chown(dst, self.user_uid, self.user_gid)
        return dst

    def copy_from_workspace(self, src: Path, dst: Path) -> Path:
        """
        Kopiert eine Datei aus dem Workspace auf den Host.

        Args:
            src: Quellpfad (relativ zum Workspace)
            dst: Zielpfad (Host)

        Returns:
            Vollständiger Pfad auf dem Host
        """
        src_full = self.workspace_path / src
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_full, dst)
        return dst

    def execute(
        self,
        command: str,
        timeout: int = 20,
        env: dict = None,
        cwd: str = "/workspace"
    ) -> dict:
        """
        Führt ein Kommando in der Sandbox aus.

        Args:
            command: Auszuführender Befehl
            timeout: Timeout in Sekunden (Default: 20)
            env: Umgebungvariablen
            cwd: Arbeitsverzeichnis (Default: /workspace)

        Returns:
            Dict mit:
            - exit_code: int
            - stdout: str
            - stderr: str
            - duration_ms: float
            - timed_out: bool
            - signal: int (falls durch Signal beendet)
        """
        if env is None:
            env = {}

        # Umgebungsvariablen vorbereiten
        sandbox_env = os.environ.copy()
        sandbox_env.update(env)
        sandbox_env["PATH"] = f"/tools:{sandbox_env.get('PATH', '')}"
        sandbox_env["HOME"] = "/tmp"
        sandbox_env["USER"] = "sandbox"
        sandbox_env["LOGNAME"] = "sandbox"

        # unshare-Kommando vorbereiten
        unshare_cmd = [
            "unshare",
            "--user",
            "--mount",
            "--pid",
            "--fork",
            "--map-root-user",
            "--setgroups=",
            "chroot", str(self.path),
            "/bin/bash", "-c",
            f"cd {cwd} && {command}"
        ]

        start_time = datetime.now()
        timed_out = False
        signal = None
        result = None

        try:
            result = subprocess.run(
                unshare_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=sandbox_env
            )
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = -1
            timed_out = True
        except subprocess.CalledProcessError as e:
            exit_code = e.returncode
        except Exception as e:
            exit_code = -1
            signal = getattr(e, "returncode", None)

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "exit_code": exit_code,
            "stdout": result.stdout if result else "",
            "stderr": result.stderr if result else str(e) if e else "",
            "duration_ms": duration_ms,
            "timed_out": timed_out,
            "signal": signal
        }

    def destroy(self) -> None:
        """Zerstört die Sandbox und gibt alle Ressourcen frei."""
        if self.status == "destroyed":
            return

        # Prozesse in der Sandbox töten
        self._kill_sandbox_processes()

        # Mounts entfernen
        self.umount_all()

        # tmpfs umounten
        try:
            subprocess.run(["umount", str(self.workspace_path)], capture_output=True)
        except:
            pass

        # Verzeichnis löschen
        try:
            shutil.rmtree(self.path, ignore_errors=True)
        except:
            pass

        self.status = "destroyed"

    def _kill_sandbox_processes(self) -> None:
        """Tötet alle Prozesse in der Sandbox."""
        try:
            # Finde alle Prozesse in der Sandbox
            result = subprocess.run(
                ["ps", "-eo", "pid,ppid,cmd"],
                capture_output=True, text=True
            )
            for line in result.stdout.split("\n"):
                if str(self.path) in line:
                    parts = line.split()
                    if len(parts) > 0 and parts[0].isdigit():
                        pid = int(parts[0])
                        try:
                            subprocess.run(["kill", "-9", str(pid)], capture_output=True)
                        except:
                            pass
        except:
            pass
