#!/usr/bin/env python3
"""
Idiom↔Ossifikat-Feedback-Schleife: geschlossener Lernkreis für das Idiom-Routing.

SCHREIBEN: Wenn ein Workflow erfolgreich durchläuft, werden die je Phase gewählten
Idiome als verbürgte Fakten in den OssifikatStore geschrieben
(idiom_id  idiom_approved_for  "phase::task_type").

LESEN: Vor dem Routing lädt der Workflow daraus kleine Score-Boni je Idiom (mehr
bewährte Approvals → leichter Vorzug). Der Router bleibt semantisch (frozen
Embedding), der Bonus bricht nur Gleichstände zugunsten empirisch bewährter Idiome.

Das schließt den Kreis Idiom-Space → Ossifikat → Router (verbinden statt schichten).
Ohne Lese-Pfad wäre das geloggte current_workflow["idioms"] nur totes Datensubstrat.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class IdiomFeedback:
    """Schreibt Idiom-Approvals nach Ossifikat und liest sie als Routing-Boni zurück."""

    PREDICATE = "idiom_approved_for"
    SOURCE = "workflow_feedback"
    STEP = 0.01          # Bonus je Approval
    MAX_BOOST = 0.05     # Deckel — semantischer Match dominiert weiter

    def __init__(self, store=None):
        """store: OssifikatStore-Instanz oder None (dann sind alle Ops No-Ops)."""
        self.store = store

    # ───────────────────────────── SCHREIBEN ─────────────────────────────

    def record_approved(self, idiom_id: str, phase: str, task_type: str) -> bool:
        """Persistiere ein bewährtes Idiom als verbürgtes Triple.

        Jeder Aufruf erzeugt (via created_at im content_hash) ein eigenes Triple →
        die Anzahl bestätigter Triple je Idiom = Approval-Häufigkeit.

        Returns True bei Erfolg, False wenn kein Store / Fehler (nie werfend —
        Feedback darf den Workflow nie abbrechen).
        """
        if self.store is None or not idiom_id:
            return False
        obj = f"{phase}::{task_type}"
        try:
            tid = self.store.add_staging(
                subject=idiom_id, predicate=self.PREDICATE, object=obj,
                source=self.SOURCE, confidence=1.0,
            )
            self.store.confirm(tid, confirmed_by="workflow", confirmation_type="auto",
                               note=f"approved run: {obj}")
            logger.debug("[IdiomFeedback] recorded %s approved_for %s", idiom_id, obj)
            return True
        except Exception as e:
            logger.warning("[IdiomFeedback] record_approved failed: %s", e)
            return False

    def record_workflow(self, idioms_by_phase: Dict[str, dict]) -> int:
        """Schreibe alle Idiom-Wahlen eines erfolgreichen Workflows.

        idioms_by_phase: das current_workflow["idioms"]-Dict
            {phase: {"id", "score", "task_type"}}.
        Returns Anzahl geschriebener Triples.
        """
        n = 0
        for phase, info in (idioms_by_phase or {}).items():
            if self.record_approved(info.get("id", ""), phase, info.get("task_type", "")):
                n += 1
        if n:
            print(f"[🔁 IdiomFeedback] {n} bewährte Idiom-Wahl(en) nach Ossifikat verbürgt")
        return n

    # ─────────────────────────────── LESEN ───────────────────────────────

    def load_boosts(self) -> Dict[str, float]:
        """Lade Score-Boni je Idiom aus der Approval-Historie.

        Returns {idiom_id: boost in [0, MAX_BOOST]}. Leeres Dict wenn kein Store.
        """
        if self.store is None:
            return {}
        try:
            triples = self.store.query(predicate=self.PREDICATE, only_confirmed=True)
        except Exception as e:
            logger.warning("[IdiomFeedback] load_boosts failed: %s", e)
            return {}

        counts = Counter(t.subject for t in triples)
        return {
            idiom_id: min(self.MAX_BOOST, n * self.STEP)
            for idiom_id, n in counts.items()
        }
