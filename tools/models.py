"""Datenmodelle für Tools und Triple-Templates."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from pathlib import Path


@dataclass
class TripleTemplate:
    """Template für ossifikat-Triples."""

    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    condition: str = "always"  # "always" | "exit_code == 0" | "exit_code != 0"

    def evaluate(self, exit_code: int, **kwargs: Any) -> bool:
        """
        Bewertet, ob das Template unter den gegebenen Bedingungen angewendet werden soll.

        Args:
            exit_code: Exit-Code der Tool-Ausführung
            **kwargs: Zusätzliche Variablen für die Bedingung

        Returns:
            True, wenn das Template angewendet werden soll
        """
        if self.condition == "always":
            return True
        elif self.condition == "exit_code == 0":
            return exit_code == 0
        elif self.condition == "exit_code != 0":
            return exit_code != 0
        else:
            # Für komplexere Bedingungen (z. B. "duration_ms > 1000")
            try:
                return eval(self.condition, {}, {"exit_code": exit_code, **kwargs})
            except:
                return False

    def render(self, **kwargs: Any) -> tuple[str, str, str, float]:
        """
        Rendert das Template mit den gegebenen Variablen.

        Args:
            **kwargs: Variablen für Platzhalter (z. B. tool_name="gcc-13")

        Returns:
            (subject, predicate, object, confidence)
        """
        def replace_placeholders(text: str) -> str:
            for key, value in kwargs.items():
                text = text.replace(f"{{{key}}}", str(value))
            return text

        return (
            replace_placeholders(self.subject),
            replace_placeholders(self.predicate),
            replace_placeholders(self.object),
            self.confidence
        )


@dataclass
class Tool:
    """Repräsentiert ein Tool mit Metadaten."""

    name: str                          # z. B. "gcc-13"
    path: Path                        # Host-Pfad: /host/tools/gcc-13
    type: str = "unknown"             # "compiler" | "interpreter" | "test_runner" | "vcs" | "unknown"
    binary: str = ""                  # z. B. "gcc" (Default: name)
    working_dir: str = "/workspace"    # Standard-Arbeitsverzeichnis
    env: dict = field(default_factory=dict)  # z. B. {"PATH": "/tools/gcc-13/bin"}
    dependencies: list[str] = field(default_factory=list)  # z. B. ["binutils", "glibc"]
    triple_templates: list[TripleTemplate] = field(default_factory=list)
    version: Optional[str] = None     # z. B. "13.2.0"
    description: str = ""
    cache_hash: Optional[str] = None    # SHA256-Hash des Tool-Verzeichnisses
    cached_path: Optional[Path] = None # Cache-Pfad: /vibelike/tools/.cache/<hash>/<name>
    last_updated: datetime = field(default_factory=datetime.now)

    def get_full_binary_path(self) -> Path:
        """Gibt den vollen Pfad zur Binary zurück."""
        if self.binary:
            return self.path / "bin" / self.binary
        return self.path / self.name
