"""Adapter to store terminal interactions as ossifikat triples."""

import warnings
from typing import Optional

try:
    from ossifikat.store import OssifikatStore
except ImportError:
    warnings.warn("ossifikat not available; TerminalAdapter will not persist triples", ImportWarning)
    OssifikatStore = None

try:
    from vibelike.logdb.db import LogDB
except ImportError:
    warnings.warn("LogDB not available; TerminalAdapter will not log events", ImportWarning)
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
        from vibelike.crypto import stable_hash_sha256
        
        # Create triple: query_hash retrieved_answer response_hash (using stable SHA256)
        subject = f"query_{stable_hash_sha256(query, hex_length=8)}"
        object_val = f"response_{stable_hash_sha256(response, hex_length=8)}"

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
