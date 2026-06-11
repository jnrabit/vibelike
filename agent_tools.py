#!/usr/bin/env python3
"""
P0.1: Agent Tools — echte Verbindung zu Vaults, Sandbox, ossifikat.

Tools sind **direkt** an existierende Systeme verdrahtet (kein Framework-Mid-Layer).
Fehlerbehandlung: Try-catch, keine Crashes, sauberes `[ERR]` return für Fehler.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).parent


class VaultTool:
    """Wrapper um terminal.py Retrieval (Code + Wissen Vaults).

    Retriever wird von außen gesetzt (inject_retriever) — der Agent nutzt den bereits
    warmen Retriever aus terminal.py statt einen neuen zu laden (kein 40s-Doppel-Load).
    """

    def __init__(self):
        self.retriever = None  # wird per inject_retriever gesetzt

    def inject_retriever(self, retriever) -> None:
        """Setzt den bereits geladenen CodeRetriever (aus terminal.py main())."""
        self.retriever = retriever

    def _init_retriever(self):
        """Fallback: eigenen Retriever laden wenn keiner injiziert wurde."""
        if self.retriever is not None:
            return
        try:
            sys.path.insert(0, str(ROOT))
            from terminal import CodeRetriever
            self.retriever = CodeRetriever(remote_url=None)
            print("[OK] VaultTool: CodeRetriever (eigen) initialisiert")
        except Exception as e:
            print(f"[WARN] VaultTool: CodeRetriever nicht verfügbar ({type(e).__name__}), nutze Mock")
            self.retriever = "mock"

    def search(self, query: str, k: int = 5) -> str:
        """Suche in Code + Wissen Vaults (Dual-Vault)."""
        if self.retriever is None:
            self._init_retriever()  # Fallback: selbst laden
        if self.retriever is None:
            return "[ERR] VaultTool nicht initialisiert"

        # Mock-Modus für P0.1 (wenn echter CodeRetriever nicht verfügbar)
        if self.retriever == "mock":
            return f"[OK/MOCK] suche nach '{query}' — live-Retrieval später mit sauberer terminal.py"

        try:
            docs, _, _ = self.retriever.search(query, k=k)
            if not docs:
                return f"[OK] keine Treffer für '{query}'"
            result = f"[OK] {len(docs)} Treffer:\n"
            for i, doc in enumerate(docs[:3], 1):
                title = doc.get("title", "?")[:40]
                dist = doc.get("distance", 0)
                result += f"  {i}. {title} (d={dist:.2f})\n"
            return result
        except Exception as e:
            return f"[ERR] search() fehlgeschlagen: {type(e).__name__}: {e}"


class OssifikatTool:
    """Wrapper um ossifikat.store (confirmte Fakten)."""

    def __init__(self):
        self.store = None
        self._init_store()

    def _init_store(self):
        """Lazy-Init OssifikatStore."""
        if self.store is not None:
            return
        try:
            ossifikat_db = ROOT / "data" / "ossifikat.db"
            sys.path.insert(0, str(ROOT / "ossifikat"))
            from ossifikat.store import OssifikatStore
            self.store = OssifikatStore(str(ossifikat_db))
            print("[OK] OssifikatTool: Store initialisiert")
        except ImportError as e:
            print(f"[WARN] OssifikatTool: OssifikatStore nicht verfügbar: {e}")
        except Exception as e:
            print(f"[WARN] OssifikatTool: Init fehlgeschlagen: {e}")

    def query_confirmed(self, subject: Optional[str] = None, k: int = 5) -> str:
        """Abfrage confirmte Fakten (Tripel) aus ossifikat."""
        if self.store is None:
            return "[ERR] OssifikatTool nicht initialisiert"
        try:
            # Lese confirmte Tripel (nur die, die ratifiziert sind)
            triples = self.store.query(subject=subject, only_confirmed=True)
            if not triples:
                return f"[OK] keine bestätigten Fakten gefunden"
            result = f"[OK] {len(triples)} bestätigte Fakten:\n"
            for i, t in enumerate(triples[:k], 1):
                result += f"  {i}. {t.subject} —[{t.predicate}]→ {t.object}\n"
            return result
        except Exception as e:
            return f"[ERR] query_confirmed() fehlgeschlagen: {e}"

    def list_staging(self) -> str:
        """Liste ratifizierungs-ausstehende Tripel."""
        if self.store is None:
            return "[ERR] OssifikatTool nicht initialisiert"
        try:
            staging = self.store.list_staging()
            return f"[OK] {len(staging)} Tripel im Staging (ratifizieren ausstehend)"
        except Exception as e:
            return f"[ERR] list_staging() fehlgeschlagen: {e}"


class FileTool:
    """Wrapper um Dateisystem (read_file)."""

    def read(self, path: str, max_lines: int = 20) -> str:
        """Lese eine Datei (Sicherheit: nur unter ROOT)."""
        try:
            p = Path(path)
            # Sicherheit: nur innerhalb des Projekts
            if not p.resolve().is_relative_to(ROOT):
                return f"[ERR] Zugriff verweigert: {path} liegt außerhalb des Projektverzeichnisses"
            if not p.exists():
                return f"[ERR] Datei nicht gefunden: {path}"
            if p.is_dir():
                return f"[ERR] ist ein Verzeichnis, keine Datei: {path}"
            content = p.read_text(encoding="utf-8")
            lines = content.split("\n")
            if len(lines) > max_lines:
                content = "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} Zeilen gekürzt)"
            return f"[OK] {path} ({len(lines)} Zeilen):\n{content[:500]}"
        except Exception as e:
            return f"[ERR] read() fehlgeschlagen: {e}"


class SandboxTool:
    """Wrapper um sandbox (run_sandboxed) — später."""

    def run(self, command: str, timeout: int = 5) -> str:
        """Führe einen Command in isolierter Umgebung aus."""
        # TODO: mit sandbox/manager.py verbinden
        return f"[STUB] run_sandboxed('{command}', timeout={timeout}) — später"


class VerifyTool:
    """Wrapper um Verifikation (Syntax, Tests, Logik)."""

    def check_syntax(self, file_path: str) -> str:
        """Prüfe Python-Syntax einer Datei."""
        try:
            p = Path(file_path)
            if not p.exists():
                return f"[ERR] Datei nicht gefunden: {file_path}"
            if p.suffix != ".py":
                return f"[ERR] nicht Python: {file_path}"
            import ast
            code = p.read_text(encoding="utf-8")
            ast.parse(code)
            return f"[OK] {file_path} Syntax ok"
        except SyntaxError as e:
            return f"[ERR] Syntax-Fehler in {file_path}: {e.msg} (Zeile {e.lineno})"
        except Exception as e:
            return f"[ERR] check_syntax() fehlgeschlagen: {e}"


# ═══ Tool-Registry (zentraler Zugriff) ═══

class ToolsFactory:
    """Factory für alle Tools."""

    _vault_tool = None
    _ossifikat_tool = None
    _file_tool = None
    _sandbox_tool = None
    _verify_tool = None

    @classmethod
    def vault(cls) -> VaultTool:
        if cls._vault_tool is None:
            cls._vault_tool = VaultTool()
        return cls._vault_tool

    @classmethod
    def inject_retriever(cls, retriever) -> None:
        """Setzt den warmen Retriever aus terminal.py — kein Doppel-Load."""
        cls.vault().inject_retriever(retriever)

    @classmethod
    def ossifikat(cls) -> OssifikatTool:
        if cls._ossifikat_tool is None:
            cls._ossifikat_tool = OssifikatTool()
        return cls._ossifikat_tool

    @classmethod
    def file(cls) -> FileTool:
        if cls._file_tool is None:
            cls._file_tool = FileTool()
        return cls._file_tool

    @classmethod
    def sandbox(cls) -> SandboxTool:
        if cls._sandbox_tool is None:
            cls._sandbox_tool = SandboxTool()
        return cls._sandbox_tool

    @classmethod
    def verify(cls) -> VerifyTool:
        if cls._verify_tool is None:
            cls._verify_tool = VerifyTool()
        return cls._verify_tool


# ═══ Test / Demo ═══

if __name__ == "__main__":
    print("═══ Tool Initialization Test ═══\n")

    # Vault-Tool
    print("[TEST] VaultTool.search('Chaos Retrieval')")
    vault = ToolsFactory.vault()
    result = vault.search("Chaos Retrieval", k=3)
    print(f"  {result}\n")

    # Ossifikat-Tool
    print("[TEST] OssifikatTool.query_confirmed()")
    oss = ToolsFactory.ossifikat()
    result = oss.query_confirmed(k=3)
    print(f"  {result}")
    print(f"[TEST] OssifikatTool.list_staging()")
    result = oss.list_staging()
    print(f"  {result}\n")

    # File-Tool
    print("[TEST] FileTool.read('terminal.py')")
    file = ToolsFactory.file()
    result = file.read("terminal.py", max_lines=5)
    print(f"  {result[:200]}...\n")

    # Verify-Tool
    print("[TEST] VerifyTool.check_syntax('agent_loop.py')")
    verify = ToolsFactory.verify()
    result = verify.check_syntax("agent_loop.py")
    print(f"  {result}\n")

    print("[TEST] VerifyTool.check_syntax('nonexistent.py')")
    result = verify.check_syntax("nonexistent.py")
    print(f"  {result}\n")
