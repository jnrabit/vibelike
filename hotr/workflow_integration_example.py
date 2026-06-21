"""
Integration Example: Full Workflow Loop with PredicateRegistry + WorkflowMemory.

Shows how to wire up PredicateRegistry + WorkflowMemory + choose() into a
real workflow execution. Demonstrates:
  1. Move through phases (Briefing → Planning → Execution → Verify → Commit)
  2. Record facts after each phase
  3. Use decide_next_phase() to check if ready for next phase
  4. Handle Decided vs. Undecidable outcomes
  5. Confirm decisions and persist to ossifikat

This is meant to be integrated into workflow_agent.run_workflow() at key points.

USAGE:
  registry = PredicateRegistry()
  store = OssifikatStore("data/ossifikat.db")
  memory = WorkflowMemory(task_id, store, registry)

  # BRIEFING
  briefing_output = agent.phase_briefing(task)
  memory.add_phase_fact("BRIEFING", "analysis_complete", "true")
  memory.add_phase_fact("BRIEFING", "context_loaded", "true")

  # Decide: can we go to PLANNING?
  choice = memory.decide_next_phase("BRIEFING", briefing_output)
  if isinstance(choice.outcome, Decided):
      memory.confirm_decision(choice, "BRIEFING", "PLANNING")
      print("✓ Ready for PLANNING")
  else:
      print(f"✗ Cannot proceed: {choice.outcome.reason.value}")
      return briefing_output

  # Continue for PLANNING, EXECUTION, VERIFY, COMMIT...
"""

import logging
from typing import Any, Dict

from choose.choice import Decided, Undecidable

from hotr.predicate_registry import PredicateRegistry
from hotr.workflow_memory import WorkflowMemory

logger = logging.getLogger(__name__)


class IntegrationExample:
    """
    Demonstrates full workflow loop with intelligent phase transitions.

    This is NOT production code — it's for understanding the architecture.
    In real usage, this logic would be integrated directly into workflow_agent.py
    phase methods.
    """

    def __init__(self, task_id: str, ossifikat_store, workflow_agent):
        """
        Initialize example.

        Args:
            task_id: Unique task ID
            ossifikat_store: OssifikatStore instance
            workflow_agent: WorkflowAgent instance (for phase methods)
        """
        self.task_id = task_id
        self.store = ossifikat_store
        self.agent = workflow_agent

        self.registry = PredicateRegistry()
        self.memory = WorkflowMemory(task_id, ossifikat_store, self.registry)

        logger.info(f"[Example] Initialized for task {task_id}")

    def run_full_workflow(self, task: str) -> Dict[str, Any]:
        """
        Run full workflow: Briefing → Planning → Execution → Verify → Commit.

        At each phase, we:
          1. Call agent.phase_X() to execute
          2. Record facts to memory
          3. Use decide_next_phase() with choose()
          4. Handle Decided vs. Undecidable
          5. Confirm decision and continue

        Args:
            task: The task description

        Returns:
            Final workflow result
        """
        print("\n" + "=" * 70)
        print("[WORKFLOW] Starting full loop with PredicateRegistry")
        print("=" * 70)

        # ===== PHASE 1: BRIEFING =====
        print("\n[PHASE 1] BRIEFING")
        print("-" * 70)
        try:
            briefing_output = self.agent.phase_briefing(task)
            print(f"  Briefing completed. Recording facts...")

            # Record facts from briefing
            self.memory.add_phase_fact(
                "BRIEFING",
                "analysis_complete",
                "true",
                source="phase_briefing",
            )
            self.memory.add_phase_fact(
                "BRIEFING",
                "context_loaded",
                "true",
                source="phase_briefing",
            )
            self.memory.add_phase_fact(
                "BRIEFING",
                "identified_bottleneck",
                "async_bottleneck_in_loop",
                source="phase_briefing",
            )

            # Decide: ready for PLANNING?
            choice_to_planning = self.memory.decide_next_phase("BRIEFING", briefing_output)
            self._handle_decision(choice_to_planning, "BRIEFING", "PLANNING")

            if isinstance(choice_to_planning.outcome, Undecidable):
                print(f"  ✗ Cannot proceed to PLANNING: {choice_to_planning.outcome.reason.value}")
                return {
                    "phase": "BRIEFING",
                    "status": "blocked",
                    "reason": choice_to_planning.outcome.reason.value,
                }

            # Confirm and continue
            self.memory.confirm_decision(choice_to_planning, "BRIEFING", "PLANNING")
            print("  ✓ Confirmed: proceeding to PLANNING")

        except Exception as e:
            logger.error(f"[BRIEFING] Failed: {e}")
            return {"phase": "BRIEFING", "status": "error", "error": str(e)}

        # ===== PHASE 2: PLANNING =====
        print("\n[PHASE 2] PLANNING")
        print("-" * 70)
        try:
            planning_output = self.agent.phase_planning(briefing_output)
            print(f"  Planning completed. Recording facts...")

            # Record facts from planning
            self.memory.add_phase_fact(
                "PLANNING",
                "strategy_viable",
                "true",
                source="phase_planning",
            )
            self.memory.add_phase_fact(
                "PLANNING",
                "all_deps_identified",
                "true",
                source="phase_planning",
            )
            self.memory.add_phase_fact(
                "PLANNING",
                "architecture_check",
                "pass",
                source="phase_planning",
            )

            # Decide: ready for EXECUTION?
            choice_to_execution = self.memory.decide_next_phase("PLANNING", planning_output)
            self._handle_decision(choice_to_execution, "PLANNING", "EXECUTION")

            if isinstance(choice_to_execution.outcome, Undecidable):
                print(f"  ✗ Cannot proceed: {choice_to_execution.outcome.reason.value}")
                return {
                    "phase": "PLANNING",
                    "status": "blocked",
                    "reason": choice_to_execution.outcome.reason.value,
                }

            self.memory.confirm_decision(choice_to_execution, "PLANNING", "EXECUTION")
            print("  ✓ Confirmed: proceeding to EXECUTION")

        except Exception as e:
            logger.error(f"[PLANNING] Failed: {e}")
            return {"phase": "PLANNING", "status": "error", "error": str(e)}

        # ===== PHASE 3: EXECUTION =====
        print("\n[PHASE 3] EXECUTION")
        print("-" * 70)
        try:
            execution_output = self.agent.phase_execution(briefing_output, planning_output)
            print(f"  Execution completed. Recording facts...")

            # Record facts from execution
            self.memory.add_phase_fact(
                "EXECUTION",
                "code_generated",
                "true",
                source="phase_execution",
            )
            self.memory.add_phase_fact(
                "EXECUTION",
                "syntax_check",
                "pass",
                source="phase_execution",
            )
            self.memory.add_phase_fact(
                "EXECUTION",
                "imports_verified",
                "true",
                source="phase_execution",
            )

            # Decide: ready for VERIFY?
            choice_to_verify = self.memory.decide_next_phase("EXECUTION", execution_output)
            self._handle_decision(choice_to_verify, "EXECUTION", "VERIFY")

            if isinstance(choice_to_verify.outcome, Undecidable):
                print(f"  ✗ Cannot proceed: {choice_to_verify.outcome.reason.value}")
                return {
                    "phase": "EXECUTION",
                    "status": "blocked",
                    "reason": choice_to_verify.outcome.reason.value,
                }

            self.memory.confirm_decision(choice_to_verify, "EXECUTION", "VERIFY")
            print("  ✓ Confirmed: proceeding to VERIFY")

        except Exception as e:
            logger.error(f"[EXECUTION] Failed: {e}")
            return {"phase": "EXECUTION", "status": "error", "error": str(e)}

        # ===== PHASE 4: VERIFICATION =====
        print("\n[PHASE 4] VERIFICATION")
        print("-" * 70)
        try:
            verification_output = self.agent.phase_verification(
                execution_output,
                task_type="IMPLEMENTATION",
            )
            print(f"  Verification completed. Recording facts...")

            # Record facts from verification
            self.memory.add_phase_fact(
                "VERIFY",
                "test_result",
                "pass",
                source="phase_verification",
            )
            self.memory.add_phase_fact(
                "VERIFY",
                "coverage_sufficient",
                "true",
                source="phase_verification",
            )
            self.memory.add_phase_fact(
                "VERIFY",
                "retry_count",
                "0",
                source="phase_verification",
            )

            # Decide: ready for COMMIT?
            # Note: VERIFY → COMMIT is typically deterministic if tests pass
            # But we still use choose() for consistency
            choice_to_commit = self.memory.decide_next_phase("VERIFY", verification_output)
            self._handle_decision(choice_to_commit, "VERIFY", "COMMIT")

            if isinstance(choice_to_commit.outcome, Undecidable):
                print(f"  ✗ Cannot proceed: {choice_to_commit.outcome.reason.value}")
                return {
                    "phase": "VERIFY",
                    "status": "blocked",
                    "reason": choice_to_commit.outcome.reason.value,
                }

            self.memory.confirm_decision(choice_to_commit, "VERIFY", "COMMIT")
            print("  ✓ Confirmed: proceeding to COMMIT")

        except Exception as e:
            logger.error(f"[VERIFICATION] Failed: {e}")
            return {"phase": "VERIFY", "status": "error", "error": str(e)}

        # ===== PHASE 5: COMMIT =====
        print("\n[PHASE 5] COMMIT")
        print("-" * 70)
        try:
            commit_output = self.agent.phase_commit(
                briefing_output,
                execution_output,
                verification_output,
            )
            print(f"  Commit completed: {commit_output.get('message', 'OK')}")

            # Record final fact
            self.memory.add_phase_fact(
                "COMMIT",
                "committed",
                "true",
                source="phase_commit",
            )

            print("  ✓ Workflow completed successfully")

        except Exception as e:
            logger.error(f"[COMMIT] Failed: {e}")
            return {"phase": "COMMIT", "status": "error", "error": str(e)}

        # ===== SUMMARY =====
        print("\n" + "=" * 70)
        print("[WORKFLOW] Summary")
        print("=" * 70)

        summary = self.memory.summary()
        print(f"  Task ID: {summary['task_id']}")
        print(f"  Total facts recorded: {summary['total_facts_cached']}")
        print(f"  Total decisions made: {summary['total_decisions']}")
        print(f"  Phases visited: {summary['cache_phases']}")

        print("\n[WORKFLOW] ✓ Success: Briefing → Planning → Execution → Verify → Commit")

        return {
            "phase": "COMMIT",
            "status": "success",
            "summary": summary,
            "decision_log": self.memory.get_decision_log(),
        }

    @staticmethod
    def _handle_decision(choice, from_phase: str, to_phase: str) -> None:
        """
        Log a decision outcome (for debugging).

        Args:
            choice: Choice object from decide_next_phase()
            from_phase: Phase we came from
            to_phase: Phase we're considering
        """
        if isinstance(choice.outcome, Decided):
            status = "✓ DECIDED"
            reason = f"predicate={choice.deciding_predicate}"
        else:
            status = "✗ UNDECIDABLE"
            reason = f"reason={choice.outcome.reason.value}"

        print(
            f"  [{status}] {from_phase}→{to_phase} | {reason} | "
            f"unused={len(choice.unused_predicates)}"
        )


# ============================================================================
# DEMO: Run example (if executed directly)
# ============================================================================

if __name__ == "__main__":
    """
    Minimal demo showing the structure.

    In real usage, you'd:
      1. Load real WorkflowAgent
      2. Load real OssifikatStore
      3. Create IntegrationExample
      4. Call run_full_workflow()
    """
    print("""
    ============================================================================
    INTEGRATION EXAMPLE: Workflow Loop with PredicateRegistry
    ============================================================================

    This example shows HOW to wire up:
      • PredicateRegistry (phase predicates)
      • WorkflowMemory (fact recording + decide_next_phase)
      • choose() (deterministic decisions)
      • OssifikatStore (persistence)

    In a real scenario:

      from workflow_agent import WorkflowAgent
      from ossifikat.ossifikat.store import OssifikatStore
      from hotr.workflow_integration_example import IntegrationExample

      store = OssifikatStore("data/ossifikat.db")
      agent = WorkflowAgent()
      example = IntegrationExample("task_123", store, agent)

      result = example.run_full_workflow("Implement feature X")

      # result contains:
      # - phase: "COMMIT"
      # - status: "success"
      # - summary: {task_id, total_facts_cached, total_decisions, ...}
      # - decision_log: [{from_phase, to_phase, outcome, predicate, ...}, ...]

    ============================================================================
    KEY POINTS:
    ============================================================================

    1. Each phase() method is called from the agent (workflow_agent.py)

    2. After each phase, we record facts:
       memory.add_phase_fact("PLANNING", "strategy_viable", "true")

    3. Before moving to next phase, we ask:
       choice = memory.decide_next_phase("PLANNING", planning_output)

    4. choose() evaluates predicates deterministically:
       - Cheap predicates first (cost_hint ordering)
       - Returns Decided(candidate) or Undecidable(reason)

    5. If Decided, we confirm and continue:
       memory.confirm_decision(choice, from_phase, to_phase)

    6. If Undecidable, we block the phase transition and return early

    ============================================================================
    AUDIT TRAIL:
    ============================================================================

    All decisions are logged with:
      - timestamp
      - task_id
      - from_phase, to_phase
      - deciding_predicate
      - unused_predicates (not needed)
      - reproducibility_hash (for debugging choose())

    Access via:
      memory.get_decision_log()
      memory.to_json()  # Full serialization

    ============================================================================
    """)
