"""Tool-Registry für das Vibelike-Sandbox-System."""

import json
import yaml
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Any

try:
    from tools.models import Tool, TripleTemplate
    from tools.cache import ToolCache
except ImportError:
    from vibelike.tools.models import Tool, TripleTemplate
    from vibelike.tools.cache import ToolCache


class ToolRegistry:
    """Verwaltet die Registrierung und das Auflösen von Tools."""

    def __init__(
        self,
        config_path: str = "/etc/vibelike/tool_adapters.yaml",
        tools_dir: Path = Path("/host/tools"),
        cache: Optional[ToolCache] = None
    ):
        """
        Initialisiert die Tool-Registry.

        Args:
            config_path: Pfad zur YAML-Konfiguration
            tools_dir: Verzeichnis mit den Tools
            cache: Optional: ToolCache-Instanz
        """
        self.config_path = Path(config_path)
        self.tools_dir = tools_dir
        self.cache = cache or ToolCache()
        self._tools: dict[str, Tool] = {}
        self._load_config()
        self._scan_tools_dir()

    def _load_config(self) -> None:
        """Lädt die Tool-Konfiguration aus der YAML-Datei."""
        if not self.config_path.exists():
            return

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        for adapter in config.get("adapters", []):
            for version in adapter.get("versions", []):
                self._tools[version["name"]] = self._load_tool_from_config(
                    version, adapter.get("type", "unknown")
                )

    def _load_tool_from_config(self, version_config: dict, adapter_type: str) -> Tool:
        """Lädt ein Tool aus der YAML-Konfiguration."""
        name = version_config["name"]
        path = Path(version_config.get("path", f"/host/tools/{name}"))
        binary = version_config.get("binary", name)

        triple_templates = [
            TripleTemplate(
                subject=tpl["subject"],
                predicate=tpl["predicate"],
                object=tpl["object"],
                confidence=tpl.get("confidence", 1.0),
                condition=tpl.get("condition", "always")
            )
            for tpl in version_config.get("triple_templates", [])
        ]

        return Tool(
            name=name,
            path=path,
            type=adapter_type,
            binary=binary,
            working_dir=version_config.get("working_dir", "/workspace"),
            env=version_config.get("env", {}),
            dependencies=version_config.get("dependencies", []),
            triple_templates=triple_templates,
            version=version_config.get("version"),
            description=version_config.get("description", "")
        )

    def _scan_tools_dir(self) -> None:
        """Scannt das Tools-Verzeichnis nach nicht konfigurierten Tools."""
        if not self.tools_dir.exists():
            return

        for tool_dir in self.tools_dir.iterdir():
            if tool_dir.name.startswith(".") or tool_dir.name in self._tools:
                continue

            # Lade tool.yaml falls vorhanden
            tool_yaml = tool_dir / "tool.yaml"
            if tool_yaml.exists():
                self._tools[tool_dir.name] = self._load_tool_from_yaml(tool_yaml)
            else:
                # Generisches Tool erstellen
                self._tools[tool_dir.name] = Tool(
                    name=tool_dir.name,
                    path=tool_dir,
                    type="unknown",
                    binary=tool_dir.name
                )

    def _load_tool_from_yaml(self, yaml_path: Path) -> Tool:
        """Lädt ein Tool aus einer tool.yaml-Datei."""
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)

        triple_templates = [
            TripleTemplate(
                subject=tpl["subject"],
                predicate=tpl["predicate"],
                object=tpl["object"],
                confidence=tpl.get("confidence", 1.0),
                condition=tpl.get("condition", "always")
            )
            for tpl in config.get("triple_templates", [])
        ]

        return Tool(
            name=config.get("name", yaml_path.parent.name),
            path=yaml_path.parent,
            type=config.get("type", "unknown"),
            binary=config.get("binary", ""),
            working_dir=config.get("working_dir", "/workspace"),
            env=config.get("env", {}),
            dependencies=config.get("dependencies", []),
            triple_templates=triple_templates,
            version=config.get("version"),
            description=config.get("description", "")
        )

    def resolve(self, tool_name: str) -> Tool:
        """
        Löst einen Tool-Namen in ein Tool-Objekt auf.

        Args:
            tool_name: Name des Tools (z. B. "gcc-13")

        Returns:
            Tool-Objekt

        Raises:
            ValueError: Falls Tool nicht gefunden wurde
        """
        if tool_name not in self._tools:
            raise ValueError(f"Tool not found: {tool_name}")

        # Prüfe Cache
        tool = self._tools[tool_name]
        if self.cache and tool.path.exists():
            cached = self.cache.get(tool.path)
            if cached:
                tool.cached_path = cached.path
                tool.cache_hash = cached.hash

        return tool

    def get_dependencies(self, tool_name: str, visited: set = None) -> list[Tool]:
        """
        Gibt alle Abhängigkeiten eines Tools (rekursiv) zurück.

        Args:
            tool_name: Name des Tools
            visited: Bereits besuchte Tools (für Zyklenerkennung)

        Returns:
            Liste der Tool-Objekte (ohne Duplikate)

        Raises:
            ValueError: Bei zirkulären Abhängigkeiten
        """
        if visited is None:
            visited = set()

        if tool_name in visited:
            raise ValueError(f"Circular dependency detected: {tool_name}")

        tool = self.resolve(tool_name)
        visited.add(tool_name)
        deps = []

        for dep_name in tool.dependencies:
            dep = self.resolve(dep_name)
            deps.append(dep)
            deps.extend(self.get_dependencies(dep_name, visited))

        return list({t.name: t for t in deps}.values())  # Deduplizieren

    def list_tools(self) -> list[str]:
        """Gibt eine Liste aller registrierten Tool-Namen zurück."""
        return list(self._tools.keys())

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Gibt ein Tool-Objekt zurück oder None, falls nicht gefunden."""
        return self._tools.get(tool_name)
