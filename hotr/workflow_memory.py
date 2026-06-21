"""
WorkflowMemory: In-Flight Context & Decision-Making for Workflows.

Integriert PredicateRegistry + OssifikatStore + choose() für intelligente
Phase-Transitions basierend auf Ossifikat-Triples.

Flow:
  1. add_phase_fact(phase, predicate, value) → speichert als Triple
  2. decide_next_phase(current_phase, phase_output) → choose() evaluiert
  3. outcome ist Choice(Decided(outcome) | Undecidable(reason))
  4. confirm_decision(choice) → speichert Decision + marks triples confirmed
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from choose.atom import choose
from choose.choice import Choice, Decided, Undecidable
from choose.predicate import Verdict
from ossifikat.ossifikat.store import OssifikatStore

from hotr.predicate_registry import PredicateRegistry

logger = logging.getLogger(__name__)


class WorkflowMemory:
    """
    In-Flight context for a workflow execution.

    Tracks facts (as Ossifikat triples) and makes deterministic decisions
    about phase transitions using PredicateRegistry + choose().
    """

    def __init__(
        self,
        task_id: str,
        ossifikat_store: OssifikatStore,
        registry: PredicateRegistry,
    ):
        """
        Initialize WorkflowMemory for a task.

        Args:
            task_id: Unique task identifier (subject for all triples)
            ossifikat_store: OssifikatStore instance for persistence
            registry: PredicateRegistry for phase decisions
        """
        self.task_id = task_id
        self.store = ossifikat_store
        self.registry = registry

        # In-flight cache: phase_name -> {predicate: value}
        self._fact_cache: Dict[str, Dict[str, str]] = {}

        # Decision log for audit trail
        self._decisions: List[Dict[str, Any]] = []

        logger.info(f"[WorkflowMemory] Initialized for task {task_id}")

    # =========================================================================
    # FACT MANAGEMENT
    # =========================================================================

    def add_phase_fact(
        self,
        phase_name: str,
        predicate_name: str,
        fact_value: str,
        source: str = "workflow",
        confidence: float = 1.0,
    ) -> None:
        """
        Record a fact from a phase.

        Adds to OssifikatStore (staging layer) via add_staging().
        Also caches locally for in-flight decisions.

        Args:
            phase_name: "BRIEFING", "PLANNING", "EXECUTION", "VERIFY"
            predicate_name: e.g., "strategy_viable"
            fact_value: e.g., "true", "pass", "fail"
            source: where fact came from (default: "workflow")
            confidence: 0.0-1.0 (default: 1.0)
        """
        # Create triple: subject=task_id, predicate=phase.fact, object=value
        full_predicate = f"{phase_name.lower()}.{predicate_name}"

        # Persist to store (staging layer)
        try:
            self.store.add_staging(
                subject=self.task_id,
                predicate=full_predicate,
                object=fact_value,
                source=source,
                confidence=confidence,
            )
            logger.debug(
                f"[WorkflowMemory] Added fact: {full_predicate}={fact_value}"
            )
        except Exception as e:
            logger.warning(
                f"[WorkflowMemory] Failed to add staging triple: {e}. Continuing with cache only."
            )

        # Cache locally
        if phase_name not in self._fact_cache:
            self._fact_cache[phase_name] = {}
        self._fact_cache[phase_name][predicate_name] = fact_value

    def get_facts(self, phase_name: str) -> Dict[str, str]:
        """
        Get all cached facts for a phase.

        Args:
            phase_name: "BRIEFING", "PLANNING", etc.

        Returns:
            Dict of {predicate_name: fact_value}
        """
        return self._fact_cache.get(phase_name, {})

    def load_triples_for_task(self) -> List[Dict[str, Any]]:
        """
        Load all triples for this task from OssifikatStore.

        Returns:
            List of triple dicts (or empty list on error)
        """
        try:
            # Query store for all triples with this task_id as subject
            triples = self.store.query(subject=self.task_id)
            logger.debug(
                f"[WorkflowMemory] Loaded {len(triples)} triples for {self.task_id}"
            )
            return triples
        except Exception as e:
            logger.warning(f"[WorkflowMemory] Failed to load triples: {e}")
            return []

    # =========================================================================
    # DECISION MAKING (with choose())
    # =========================================================================

    def decide_next_phase(
        self,
        current_phase: str,
        phase_output: Any,
    ) -> Choice:
        """
        Decide if we can proceed to the next phase.

        Uses PredicateRegistry to build a bundle for the next phase,
        then calls choose() to determine if we're ready.

        Args:
            current_phase: "BRIEFING", "PLANNING", "EXECUTION", "VERIFY"
            phase_output: The output from current phase (dict or str)

        Returns:
            Choice(Decided(outcome) | Undecidable(reason))
            - Decided: ready to proceed
            - Undecidable: missing facts or rejection
        """
        # Map phase to next phase
        phase_sequence = {
            "BRIEFING": "PLANNING",
            "PLANNING": "EXECUTION",
            "EXECUTION": "VERIFY",
            "VERIFY": "COMMIT",
        }

        next_phase = phase_sequence.get(current_phase.upper())
        if not next_phase:
            logger.warning(f"[WorkflowMemory] Unknown phase: {current_phase}")
            return Choice(
                outcome=Undecidable(reason="UNKNOWN_PHASE"),
                deciding_predicate=None,
                unused_predicates=(),
                reproducibility_hash="unknown",
            )

        # Get bundle for next phase
        try:
            bundle = self.registry.get_bundle(next_phase)
        except ValueError as e:
            logger.warning(f"[WorkflowMemory] {e}")
            return Choice(
                outcome=Undecidable(reason="NO_BUNDLE"),
                deciding_predicate=None,
                unused_predicates=(),
                reproducibility_hash="unknown",
            )

        # Load current facts from store + cache
        all_triples = self.load_triples_for_task()
        fact_values = [triple.get("object", "") for triple in all_triples if triple.get("object")]

        # If no facts yet, use phase_output as single candidate
        if not fact_values:
            fact_values = [str(phase_output)] if phase_output else []

        logger.info(
            f"[WorkflowMemory] Deciding {current_phase} → {next_phase} "
            f"with {len(fact_values)} facts"
        )

        # Call choose()
        choice = choose(bundle, fact_values)

        # Log decision
        self._log_decision(
            from_phase=current_phase,
            to_phase=next_phase,
            choice=choice,
        )

        return choice

    def _log_decision(
        self,
        from_phase: str,
        to_phase: str,
        choice: Choice,
    ) -> None:
        """
        Log a decision to the audit trail.

        Args:
            from_phase: Current phase
            to_phase: Candidate next phase
            choice: Choice object from choose()
        """
        decision_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": self.task_id,
            "from_phase": from_phase,
            "to_phase": to_phase,
            "outcome": "DECIDED" if isinstance(choice.outcome, Decided) else "UNDECIDABLE",
            "deciding_predicate": choice.deciding_predicate,
            "unused_predicates": choice.unused_predicates,
            "reproducibility_hash": choice.reproducibility_hash,
        }

        if isinstance(choice.outcome, Undecidable):
            decision_record["reason"] = choice.outcome.reason.value

        self._decisions.append(decision_record)

        logger.info(
            f"[WorkflowMemory] Decision logged: {from_phase}→{to_phase} "
            f"outcome={decision_record['outcome']}"
        )

    # =========================================================================
    # CONFIRMATION & PERSISTENCE
    # =========================================================================

    def confirm_decision(
        self,
        choice: Choice,
        from_phase: str,
        to_phase: str,
    ) -> bool:
        """
        Confirm a decision and persist it.

        Moves staging triples to confirmed state in OssifikatStore.

        Args:
            choice: The Choice object from decide_next_phase()
            from_phase: Phase we came from
            to_phase: Phase we're going to

        Returns:
            True if confirmed, False if undecidable
        """
        if isinstance(choice.outcome, Undecidable):
            logger.warning(
                f"[WorkflowMemory] Cannot confirm undecidable: {choice.outcome.reason.value}"
            )
            return False

        # Get decided candidate
        decided = choice.outcome
        logger.info(
            f"[WorkflowMemory] Confirming decision: {from_phase}→{to_phase} "
            f"decided={decided.candidate}"
        )

        # Mark all staging triples as confirmed
        try:
            triples = self.load_triples_for_task()
            for triple in triples:
                # Check if staging (query returns triples, staging status may be in dict)
                is_staging = triple.get("staging", True)
                if is_staging:  # Only confirm staging triples
                    content_hash = triple.get("content_hash")
                    if content_hash:
                        self.store.confirm(
                            content_hash,
                            confirmed_by=f"workflow:{self.task_id}",
                            confirmation_type=f"phase_transition:{from_phase}→{to_phase}",
                            note=f"Decided by predicate: {choice.deciding_predicate}",
                        )
        except Exception as e:
            logger.warning(f"[WorkflowMemory] Failed to confirm triples: {e}")
            return False

        return True

    # =========================================================================
    # INSPECTION
    # =========================================================================

    def get_decision_log(self) -> List[Dict[str, Any]]:
        """Get all recorded decisions."""
        return self._decisions.copy()

    def summary(self) -> Dict[str, Any]:
        """
        Get a summary of workflow memory state.

        Returns:
            Dict with task_id, fact_count, decision_count, cache snapshot
        """
        total_facts = sum(len(v) for v in self._fact_cache.values())
        return {
            "task_id": self.task_id,
            "total_facts_cached": total_facts,
            "total_decisions": len(self._decisions),
            "cache_phases": list(self._fact_cache.keys()),
            "last_decision": self._decisions[-1] if self._decisions else None,
        }

    def to_json(self) -> str:
        """Serialize memory state to JSON."""
        return json.dumps(
            {
                "task_id": self.task_id,
                "fact_cache": self._fact_cache,
                "decisions": self._decisions,
            },
            indent=2,
        )
