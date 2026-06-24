"""Adapter to store tool information as ossifikat triples."""

import warnings
from typing import Optional

try:
    from ossifikat.store import OssifikatStore
except ImportError:
    warnings.warn("ossifikat not available; ToolsAdapter will not persist triples", ImportWarning)
    OssifikatStore = None

try:
    from vibelike.logdb.db import LogDB
except ImportError:
    warnings.warn("LogDB not available; ToolsAdapter will not log events", ImportWarning)
    LogDB = None


class ToolsAdapter:
    """Stores tool metadata and documentation as knowledge triples."""

    def __init__(self, ossifikat_db_path: str = "ossifikat/data/ossifikat.db", logdb_path: str = "logs/execution.db"):
        self.store = OssifikatStore(ossifikat_db_path) if OssifikatStore else None
        self.logdb = LogDB(logdb_path) if LogDB else None

    def store_tool(self, tool: dict, source: str = "tools_harvester", confirm: bool = False) -> Optional[int]:
        """
        Store tool information as a triple.

        Args:
            tool: Tool dict with id, urls, sector, source, name, etc.
            source: Source label (tools_harvester, manual, etc.)
            confirm: Whether to immediately confirm

        Returns:
            Triple ID if stored successfully
        """
        if not tool or not tool.get("id"):
            return None

        tool_id = str(tool.get("id", ""))
        sector = tool.get("sector", "UNKNOWN")

        # Create triple: tool_id belongs_to_sector sector
        triple_id = self.store.add_staging(
            subject=tool_id,
            predicate="belongs_to_sector",
            object=sector,
            source=source
        )

        # Log event
        if triple_id and self.logdb:
            self.logdb.add_adapter_event(
                adapter="tools",
                event_type="store_tool",
                source=source,
                triple_id=triple_id,
                subject=tool_id,
                predicate="belongs_to_sector",
                object=sector,
                metadata={
                    "tool_id": tool_id,
                    "sector": sector,
                    "urls_count": len(tool.get("urls", []))
                }
            )

        if triple_id and confirm:
            self.store.confirm(triple_id)

        return triple_id

    def store_tool_relationship(
        self,
        tool_a: str,
        relationship: str,
        tool_b: str,
        confirm: bool = False
    ) -> Optional[int]:
        """
        Store relationship between tools (e.g., GCC extends LLVM).

        Args:
            tool_a: First tool ID
            relationship: Type of relationship (extends, depends_on, similar_to, etc.)
            tool_b: Second tool ID
            confirm: Whether to immediately confirm

        Returns:
            Triple ID if stored
        """
        return self.store.add_staging(
            subject=tool_a,
            predicate=relationship,
            object=tool_b,
            source="tools_harvester"
        )

    def store_sector_summary(self, sector: str, tool_count: int, coverage: str = "") -> Optional[int]:
        """Store summary information about a tool sector."""
        return self.store.add_staging(
            subject=sector,
            predicate="sector_summary",
            object=f"{tool_count}_tools",
            source="tools_harvester"
        )

    def get_tools_in_sector(self, sector: str, only_confirmed: bool = False) -> list:
        """Retrieve all tools in a specific sector."""
        return self.store.query(object=sector, only_confirmed=only_confirmed)

    def get_tool_relationships(self, tool_id: str) -> list:
        """Retrieve all relationships involving a tool."""
        outgoing = self.store.query(subject=tool_id)
        incoming = self.store.query(obj=tool_id)
        return outgoing + incoming
