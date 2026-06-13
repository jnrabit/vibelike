"""Adapter to store harvested documents as ossifikat triples."""

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


class HarvestAdapter:
    """Converts harvested documents into knowledge triples."""

    def __init__(self, ossifikat_db_path: str = "ossifikat/data/ossifikat.db", logdb_path: str = "logs/execution.db"):
        self.store = OssifikatStore(ossifikat_db_path) if OssifikatStore else None
        self.logdb = LogDB(logdb_path) if LogDB else None

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

        # If ossifikat is not available, skip storage
        if not self.store:
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

        # Log event to database
        if triple_id and self.logdb:
            self.logdb.add_adapter_event(
                adapter="harvest",
                event_type="store_document",
                source=source,
                triple_id=triple_id,
                subject=doc_id,
                predicate="is_document_in",
                object=sector,
                metadata={"title": title, "doc_id": doc_id, "sector": sector}
            )

        if triple_id and confirm:
            self.store.confirm(triple_id)

        return triple_id

    def store_sector(self, sector: str, doc_count: int) -> Optional[int]:
        """Store information about a harvested sector."""
        if not self.store:
            return None

        triple_id = self.store.add_staging(
            subject=sector.lower(),
            predicate="harvested_documents",
            object=str(doc_count),
            source="harvest_summary"
        )

        # Log event
        if triple_id and self.logdb:
            self.logdb.add_adapter_event(
                adapter="harvest",
                event_type="store_sector",
                source="harvest_summary",
                triple_id=triple_id,
                subject=sector.lower(),
                predicate="harvested_documents",
                object=str(doc_count),
                metadata={"sector": sector, "doc_count": doc_count}
            )

        return triple_id

    def get_document_triples(self, doc_id: str, only_confirmed: bool = False) -> list:
        """Retrieve all triples related to a document."""
        if not self.store:
            return []
        return self.store.query(subject=doc_id, only_confirmed=only_confirmed)
