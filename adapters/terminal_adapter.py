"""Adapter to store terminal interactions as ossifikat triples."""

from typing import Optional
from ossifikat.store import OssifikatStore


class TerminalAdapter:
    """Stores terminal queries and responses as knowledge triples."""

    def __init__(self, ossifikat_db_path: str = "ossifikat/data/ossifikat.db"):
        self.store = OssifikatStore(ossifikat_db_path)

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
        triple_id = self.store.add_staging(
            subject=f"query_{hash(query) % 10000}",
            predicate="retrieved_answer",
            object=f"response_{hash(response) % 10000}",
            source="terminal"
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
        return self.store.add_staging(
            subject="hardware_state",
            predicate=label,
            object="lorenz_attractor",
            source="terminal_hardware"
        )

    def get_query_history(self, limit: int = 10) -> list:
        """Retrieve recent query-response triples."""
        return self.store.query(predicate="retrieved_answer", limit=limit)
