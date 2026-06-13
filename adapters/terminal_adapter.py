"""Adapter to store terminal interactions as ossifikat triples."""

import sys
from pathlib import Path
from typing import Optional

# Add ossifikat to path for local development
_root = Path(__file__).parent.parent
if str(_root / "ossifikat") not in sys.path:
    sys.path.insert(0, str(_root / "ossifikat"))

try:
    from ossifikat.store import OssifikatStore
except ImportError:
    OssifikatStore = None

try:
    from logdb.db import LogDB
except ImportError:
    try:
        from vibelike.logdb.db import LogDB
    except ImportError:
        LogDB = None


class TerminalAdapter:
    """Stores terminal queries and responses as knowledge triples."""

    def __init__(self, ossifikat_db_path: str = "ossifikat/data/ossifikat.db", logdb_path: str = "logs/execution.db"):
        self.store = OssifikatStore(ossifikat_db_path) if OssifikatStore else None
        self.logdb = LogDB(logdb_path) if LogDB else None

    def store_query_response(
        self,
        query: str,
        response: str,
        context_ids: list[str] = None,
        confirm: bool = False
    ) -> Optional[int]:
        """
        Store a query-response interaction as a triple.

        Args:
            query: User query
            response: Model response
            context_ids: IDs of documents used as context
            confirm: Whether to immediately confirm

        Returns:
            Triple ID if stored successfully
        """
        # Create triple: query_hash retrieved_answer response_hash
        subject = f"query_{hash(query) % 10000}"
        object_val = f"response_{hash(response) % 10000}"

        triple_id = self.store.add_staging(
            subject=subject,
            predicate="retrieved_answer",
            object=object_val,
            source="terminal"
        )

        # Log event to database
        if triple_id and self.logdb:
            self.logdb.add_adapter_event(
                adapter="terminal",
                event_type="store_query_response",
                source="terminal",
                triple_id=triple_id,
                subject=subject,
                predicate="retrieved_answer",
                object=object_val,
                metadata={
                    "query": query[:200],  # Store first 200 chars
                    "response": response[:200],
                    "context_count": len(context_ids) if context_ids else 0
                }
            )

        if triple_id and confirm:
            self.store.confirm(triple_id)

        return triple_id

    def store_hardware_state(
        self,
        lorenz_params: dict,
        thermodynamics: dict,
        label: str = "query_execution"
    ) -> Optional[int]:
        """Store hardware state information as a triple."""
        triple_id = self.store.add_staging(
            subject="hardware_state",
            predicate=label,
            object="lorenz_attractor",
            source="terminal_hardware"
        )

        # Log event
        if triple_id and self.logdb:
            self.logdb.add_adapter_event(
                adapter="terminal",
                event_type="store_hardware_state",
                source="terminal_hardware",
                triple_id=triple_id,
                subject="hardware_state",
                predicate=label,
                object="lorenz_attractor",
                metadata={
                    "lorenz": lorenz_params,
                    "thermodynamics": thermodynamics
                }
            )

        return triple_id

    def get_query_history(self, limit: int = 10) -> list:
        """Retrieve recent query-response triples."""
        return self.store.query(predicate="retrieved_answer", limit=limit)
