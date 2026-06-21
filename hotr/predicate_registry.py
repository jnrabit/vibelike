"""
PredicateRegistry für Workflow-Decision-Making.

Konvertiert Ossifikat-Triples zu evaluierbaren Facts für jede Workflow-Phase.
Nutzt choose() für deterministische Decision-Making.

Predicate-Definitionen sind flache dicts mit:
  - type: "equals" | "regex" | "exists" | "not_exists"
  - value: String oder Regex-Pattern (ignored für "exists"/"not_exists")
  - cost_hint: int (cheap=10, medium=50, expensive=100; choose() evaluiert in dieser Reihenfolge)
  - verdict_on_match: "ACCEPT" | "REJECT" (was returned wenn Match)
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple

from choose.bundle import PredicateBundle
from choose.predicate import Predicate, Verdict
from ossifikat.ossifikat.schema import Triple


class PredicateType(Enum):
    """Predicate evaluation types."""
    EQUALS = "equals"          # fact_value == predicate.value
    REGEX = "regex"            # fact_value matches predicate.value as regex
    EXISTS = "exists"          # fact exists (any value)
    NOT_EXISTS = "not_exists"  # fact does not exist


# ============================================================================
# BRIEFING PREDICATES
# ============================================================================
BRIEFING_PREDICATES: Dict[str, Dict] = {
    "has_identified_bottleneck": {
        "type": "exists",
        "cost_hint": 10,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["briefing.identified_bottleneck"],
    },
    "has_constraints": {
        "type": "exists",
        "cost_hint": 10,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["briefing.identified_constraints"],
    },
    "analysis_incomplete": {
        "type": "not_exists",
        "cost_hint": 10,
        "verdict_on_match": "REJECT",
        "predicate_names": ["briefing.analysis_complete"],
    },
    "context_loaded": {
        "type": "equals",
        "value": "true",
        "cost_hint": 15,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["briefing.context_loaded"],
    },
}


# ============================================================================
# PLANNING PREDICATES
# ============================================================================
PLANNING_PREDICATES: Dict[str, Dict] = {
    "strategy_viable": {
        "type": "equals",
        "value": "true",
        "cost_hint": 20,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["planning.strategy_viable"],
    },
    "dependencies_known": {
        "type": "equals",
        "value": "true",
        "cost_hint": 20,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["planning.all_deps_identified"],
    },
    "has_unresolved_dependency": {
        "type": "exists",
        "cost_hint": 25,
        "verdict_on_match": "REJECT",
        "predicate_names": ["planning.unresolved_dependency"],
    },
    "architecture_aligned": {
        "type": "equals",
        "value": "pass",
        "cost_hint": 30,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["planning.architecture_check"],
    },
    "plan_is_minimal": {
        "type": "equals",
        "value": "true",
        "cost_hint": 15,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["planning.is_minimal"],
    },
}


# ============================================================================
# EXECUTION PREDICATES
# ============================================================================
EXECUTION_PREDICATES: Dict[str, Dict] = {
    "code_generated": {
        "type": "equals",
        "value": "true",
        "cost_hint": 10,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["execution.code_generated"],
    },
    "syntax_ok": {
        "type": "equals",
        "value": "pass",
        "cost_hint": 20,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["execution.syntax_check"],
    },
    "syntax_error": {
        "type": "equals",
        "value": "fail",
        "cost_hint": 20,
        "verdict_on_match": "REJECT",
        "predicate_names": ["execution.syntax_check"],
    },
    "imports_resolved": {
        "type": "equals",
        "value": "true",
        "cost_hint": 25,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["execution.imports_verified"],
    },
    "no_import_error": {
        "type": "not_exists",
        "cost_hint": 25,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["execution.import_error"],
    },
    "code_incomplete": {
        "type": "not_exists",
        "cost_hint": 15,
        "verdict_on_match": "REJECT",
        "predicate_names": ["execution.code_generated"],
    },
}


# ============================================================================
# VERIFICATION PREDICATES
# ============================================================================
VERIFY_PREDICATES: Dict[str, Dict] = {
    "tests_passing": {
        "type": "equals",
        "value": "pass",
        "cost_hint": 20,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["verify.test_result"],
    },
    "failure_recoverable": {
        "type": "regex",
        "value": r"^(recoverable|warning|minor)$",
        "cost_hint": 30,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["verify.failure_severity"],
    },
    "critical_failure": {
        "type": "equals",
        "value": "CRITICAL",
        "cost_hint": 30,
        "verdict_on_match": "REJECT",
        "predicate_names": ["verify.failure_severity"],
    },
    "retry_available": {
        "type": "regex",
        "value": r"^([0-2])$",  # retry_count < 3
        "cost_hint": 25,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["verify.retry_count"],
    },
    "no_retries_left": {
        "type": "regex",
        "value": r"^([3-9]|\d{2,})$",  # retry_count >= 3
        "cost_hint": 25,
        "verdict_on_match": "REJECT",
        "predicate_names": ["verify.retry_count"],
    },
    "coverage_sufficient": {
        "type": "equals",
        "value": "true",
        "cost_hint": 35,
        "verdict_on_match": "ACCEPT",
        "predicate_names": ["verify.coverage_sufficient"],
    },
}


# ============================================================================
# PREDICATE REGISTRY CLASS
# ============================================================================

class FactEvaluator:
    """Evaluates a single fact against a predicate definition."""

    def __init__(self, predicate_name: str, predicate_def: Dict):
        self.name = predicate_name
        self.predicate_type = PredicateType(predicate_def["type"])
        self.value = predicate_def.get("value")
        self.verdict_on_match = Verdict[predicate_def["verdict_on_match"]]
        self.cost_hint = predicate_def.get("cost_hint", 50)

    def evaluate(self, fact_value: Optional[str]) -> Verdict:
        """
        Evaluate fact_value against this predicate.

        Args:
            fact_value: The value from the Ossifikat triple (or None if not exists)

        Returns:
            Verdict.ACCEPT, Verdict.REJECT, or Verdict.DEFER
        """
        if self.predicate_type == PredicateType.EXISTS:
            # Fact exists if fact_value is not None
            match = fact_value is not None
            if match:
                return self.verdict_on_match
            else:
                # Fact doesn't exist; if we wanted NOT_EXISTS, that's a match
                return Verdict.DEFER  # No match, can't decide on this predicate alone

        elif self.predicate_type == PredicateType.NOT_EXISTS:
            # Fact doesn't exist if fact_value is None
            match = fact_value is None
            if match:
                return self.verdict_on_match
            else:
                return Verdict.DEFER

        elif self.predicate_type == PredicateType.EQUALS:
            if fact_value is None:
                return Verdict.DEFER  # No value to compare
            match = fact_value == self.value
            if match:
                return self.verdict_on_match
            else:
                # Didn't match; but may still defer or reject
                if self.verdict_on_match == Verdict.ACCEPT:
                    return Verdict.DEFER  # Was looking for ACCEPT, didn't find it
                else:
                    return Verdict.REJECT  # Was looking for REJECT, found something else

        elif self.predicate_type == PredicateType.REGEX:
            if fact_value is None:
                return Verdict.DEFER
            try:
                match = bool(re.match(self.value, fact_value))
                if match:
                    return self.verdict_on_match
                else:
                    if self.verdict_on_match == Verdict.ACCEPT:
                        return Verdict.DEFER
                    else:
                        return Verdict.REJECT
            except re.error as e:
                # Regex error; defer
                return Verdict.DEFER

        return Verdict.DEFER


class PredicateRegistryPhase:
    """A set of predicates for a single workflow phase."""

    def __init__(self, phase_name: str, predicate_defs: Dict[str, Dict]):
        self.phase_name = phase_name
        self.evaluators = {
            name: FactEvaluator(name, defn)
            for name, defn in predicate_defs.items()
        }

    def build_bundle(self) -> PredicateBundle:
        """Build a PredicateBundle for choose()."""
        # Sort by cost_hint (cheap first)
        sorted_evals = sorted(
            self.evaluators.values(),
            key=lambda e: e.cost_hint
        )

        # Create Predicate objects that choose() understands
        predicates = [
            Predicate(
                name=e.name,
                evaluate=lambda candidate, evaluator=e: self._evaluate_candidate(evaluator, candidate)
            )
            for e in sorted_evals
        ]

        return PredicateBundle(predicates)

    @staticmethod
    def _evaluate_candidate(evaluator: FactEvaluator, candidate) -> Verdict:
        """Wrapper to evaluate a candidate (fact_value) using the evaluator."""
        fact_value = candidate if isinstance(candidate, str) else str(candidate)
        return evaluator.evaluate(fact_value)


class PredicateRegistry:
    """
    Central registry for workflow decision predicates.

    Maps Ossifikat triples to workflow decisions across all phases.
    """

    def __init__(self):
        self.phases = {
            "BRIEFING": PredicateRegistryPhase("BRIEFING", BRIEFING_PREDICATES),
            "PLANNING": PredicateRegistryPhase("PLANNING", PLANNING_PREDICATES),
            "EXECUTION": PredicateRegistryPhase("EXECUTION", EXECUTION_PREDICATES),
            "VERIFY": PredicateRegistryPhase("VERIFY", VERIFY_PREDICATES),
        }

    def get_bundle(self, phase_name: str) -> PredicateBundle:
        """Get PredicateBundle for a workflow phase."""
        phase = self.phases.get(phase_name.upper())
        if not phase:
            raise ValueError(f"Unknown phase: {phase_name}")
        return phase.build_bundle()

    def evaluate_fact(self, phase_name: str, fact_value: str) -> Optional[Verdict]:
        """
        Evaluate a single fact in a phase. (Rarely used; prefer choose() instead.)

        Args:
            phase_name: "BRIEFING", "PLANNING", "EXECUTION", "VERIFY"
            fact_value: The fact value to evaluate

        Returns:
            Verdict or None if phase not found
        """
        phase = self.phases.get(phase_name.upper())
        if not phase:
            return None

        # This would need more context (which predicate?), so mostly for debugging
        # In practice, use choose(bundle, [fact_value]) instead
        return None

    def list_predicates(self, phase_name: str) -> List[str]:
        """List all predicate names for a phase."""
        phase = self.phases.get(phase_name.upper())
        if not phase:
            return []
        return list(phase.evaluators.keys())


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def triple_to_fact(triple: Triple) -> Tuple[str, str]:
    """
    Convert an Ossifikat triple to (predicate_name, fact_value).

    Args:
        triple: Triple(subject=task_id, predicate=phase.fact_name, object=value)

    Returns:
        (predicate_name, fact_value) or (predicate, "UNKNOWN") if malformed
    """
    if not triple.predicate:
        return ("UNKNOWN", triple.object or "")

    # Triple predicate is like "briefing.identified_bottleneck"
    # We extract the fact_name directly
    return (triple.predicate, triple.object or "")


def fact_matches_predicate(fact_value: str, predicate_name: str, phase_name: str, registry: PredicateRegistry) -> Verdict:
    """
    Check if a fact value matches a specific predicate in a phase.

    Args:
        fact_value: The value from triple.object
        predicate_name: e.g., "strategy_viable"
        phase_name: "BRIEFING", "PLANNING", etc.
        registry: PredicateRegistry instance

    Returns:
        Verdict.ACCEPT, REJECT, or DEFER
    """
    phase = registry.phases.get(phase_name.upper())
    if not phase:
        return Verdict.DEFER

    evaluator = phase.evaluators.get(predicate_name)
    if not evaluator:
        return Verdict.DEFER

    return evaluator.evaluate(fact_value)
