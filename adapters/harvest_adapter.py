"""Adapter to store harvested documents as ossifikat triples."""

from typing import Optional
from ossifikat.store import OssifikatStore


class HarvestAdapter:
    """Converts harvested documents into knowledge triples."""

    def __init__(self, ossifikat_db_path: str = "ossifikat/data/ossifikat.db"):
        self.store = OssifikatStore(ossifikat_db_path)

    def store_document(self, doc: dict, source: str = "harvest", confirm: bool = False) -> Optional[int]:
        """
        Store a harvested document as a triple.

        Args:
            doc: Document dict with id, title, content, source, sector, etc.
            source: Source label (harvest, rfc, pep, etc.)
            confirm: Whether to immediately confirm the triple

        Returns:
            Triple ID if stored successfully, None otherwise
        """
        if not doc or not doc.get("id"):
            return None

        doc_id = str(doc.get("id", ""))
        title = doc.get("title", "Unknown")
        sector = doc.get("sector", "UNKNOWN")

        # Create triple: document_id is_document_in sector
        triple_id = self.store.add_staging(
            subject=doc_id,
            predicate="is_document_in",
            object=sector,
            source=source
        )

        if triple_id and confirm:
            self.store.confirm(triple_id)

        return triple_id

    def store_sector(self, sector: str, doc_count: int) -> Optional[int]:
        """Store information about a harvested sector."""
        return self.store.add_staging(
            subject=sector.lower(),
            predicate="harvested_documents",
            object=str(doc_count),
            source="harvest_summary"
        )

    def get_document_triples(self, doc_id: str, only_confirmed: bool = False) -> list:
        """Retrieve all triples related to a document."""
        return self.store.query(subject=doc_id, only_confirmed=only_confirmed)
