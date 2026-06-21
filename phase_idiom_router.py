#!/usr/bin/env python3
"""
Runtime Idiom Router: Load frozen code_idioms.json, route by phase+task+requirement.

Usage:
  router = PhaseIdiomRouter("code_idioms.json")
  idiom = router.route(
      phase="briefing",
      task_type="ANALYSIS",
      requirement="Ich brauche ne gründliche Analyse mit Synthese",
      context={"docs_available": True}
  )
  print(f"Selected idiom: {idiom.id}, score: {score:.2f}")
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial.distance import cosine
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


@dataclass
class CodeIdiom:
    """Runtime representation of a compiled idiom."""

    id: str
    phase: str
    task_type: Optional[str]
    description: str
    tags: List[str]
    complexity_hint: str
    tradeoff: str
    requires: List[str]
    patterns: Dict[str, str]
    metadata: Dict[str, Any]
    embedding: np.ndarray  # (384,) numpy array

    @classmethod
    def from_dict(cls, data: dict) -> "CodeIdiom":
        """Create CodeIdiom from JSON dict (converts embedding to numpy)."""
        return cls(
            id=data["id"],
            phase=data["phase"],
            task_type=data.get("task_type"),
            description=data["description"],
            tags=data["tags"],
            complexity_hint=data["complexity_hint"],
            tradeoff=data["tradeoff"],
            requires=data["requires"],
            patterns=data["patterns"],
            metadata=data["metadata"],
            embedding=np.array(data["embedding"], dtype=np.float32),
        )


class PhaseIdiomRouter:
    """
    Load frozen code_idioms.json and route queries to best idiom.

    Routing logic:
    1. Filter idioms by phase + task_type
    2. Encode user requirement
    3. Cosine-similarity against candidates
    4. Return top-1 if score > threshold, else fallback
    """

    def __init__(
        self,
        idiom_space_path: str = "code_idioms.json",
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        confidence_threshold: float = 0.5,
    ):
        """
        Initialize router.

        Args:
            idiom_space_path: Path to compiled code_idioms.json
            model_name: SentenceTransformer model (must match compile-time model)
            confidence_threshold: Min cosine-sim score (0.5 = moderate, 0.7 = high)
        """
        self.idiom_space_path = Path(idiom_space_path)
        self.confidence_threshold = confidence_threshold

        # Load frozen space
        logger.info(f"Loading idiom space from {self.idiom_space_path}...")
        self.space = self._load_space()
        logger.info(f"  ✓ Loaded {len(self.space['idioms'])} idioms")

        # Load model
        logger.info(f"Loading model: {model_name}...")
        self.model = SentenceTransformer(model_name)
        logger.info(f"  ✓ Model ready ({self.model.get_sentence_embedding_dimension()}-dim)")

        # Index by phase + task_type for fast filtering
        self._build_index()

    def _load_space(self) -> Dict[str, Any]:
        """Load frozen JSON space."""
        if not self.idiom_space_path.exists():
            raise FileNotFoundError(f"Idiom space not found: {self.idiom_space_path}")

        with open(self.idiom_space_path) as f:
            space = json.load(f)

        # Convert raw idiom dicts to CodeIdiom objects
        idiom_objs = []
        for idiom_dict in space["idioms"]:
            idiom_objs.append(CodeIdiom.from_dict(idiom_dict))

        space["idioms"] = idiom_objs
        return space

    def _build_index(self) -> None:
        """Build (phase, task_type) → [idiom_indices] index for fast lookup."""
        self.index = {}

        for i, idiom in enumerate(self.space["idioms"]):
            key = (idiom.phase, idiom.task_type)
            if key not in self.index:
                self.index[key] = []
            self.index[key].append(i)

        logger.debug(f"Built index with {len(self.index)} phase+task_type combinations")

    def route(
        self,
        phase: str,
        task_type: Optional[str],
        requirement: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[CodeIdiom, float]:
        """
        Route requirement to best idiom for (phase, task_type).

        Args:
            phase: Phase name (e.g., "briefing", "planning_strategie")
            task_type: Task type (e.g., "ANALYSIS") or None for task-agnostic
            requirement: Natural language requirement (e.g., "thorough analysis with synthesis")
            context: Optional context dict (for future refinement)

        Returns:
            (CodeIdiom, confidence_score) tuple
        """
        # Step 1: Collect candidates
        candidates_indices = self._get_candidates(phase, task_type)

        if not candidates_indices:
            logger.warning(
                f"No idioms found for phase={phase}, task_type={task_type}. "
                f"Using generic fallback."
            )
            return self._fallback_idiom(phase)

        candidates = [self.space["idioms"][i] for i in candidates_indices]

        # Step 2: Encode requirement
        req_embedding = self.model.encode(requirement, convert_to_numpy=True)

        # Step 3: Compute cosine similarities
        scores = []
        for idiom in candidates:
            similarity = 1.0 - cosine(req_embedding, idiom.embedding)
            scores.append(similarity)

        # Step 4: Find best match
        best_idx = np.argmax(scores)
        best_idiom = candidates[best_idx]
        best_score = float(scores[best_idx])

        # Step 5: Check confidence threshold
        if best_score < self.confidence_threshold:
            logger.warning(
                f"Low confidence ({best_score:.2f} < {self.confidence_threshold}) "
                f"for requirement '{requirement[:40]}...'. Using fallback."
            )
            return self._fallback_idiom(phase)

        logger.debug(
            f"[ROUTE] {phase}/{task_type} → {best_idiom.id} (score={best_score:.2f})"
        )

        return best_idiom, best_score

    def _get_candidates(
        self, phase: str, task_type: Optional[str]
    ) -> List[int]:
        """
        Get candidate idiom indices for (phase, task_type).

        Strategy:
        1. First try (phase, task_type) — exact match
        2. Then try (phase, None) — task-agnostic idioms
        3. Return combined list (exact first, then generic)
        """
        exact_key = (phase, task_type)
        generic_key = (phase, None)

        exact_indices = self.index.get(exact_key, [])
        generic_indices = self.index.get(generic_key, [])

        # Combine: exact first, then generic
        return exact_indices + generic_indices

    def _fallback_idiom(self, phase: str) -> Tuple[CodeIdiom, float]:
        """
        Return fallback idiom for phase (lowest complexity, usually).

        Fallback strategy: pick the idiom with lowest complexity_hint,
        or just the first one in the phase.
        """
        phase_idioms = [
            (i, idiom)
            for i, idiom in enumerate(self.space["idioms"])
            if idiom.phase == phase
        ]

        if not phase_idioms:
            raise ValueError(f"No idioms found for phase {phase}")

        # Sort by complexity: "Very Low" < "Low" < "Medium" < "High" < "Very High"
        complexity_order = {
            "Very Low": 0,
            "Low": 1,
            "Medium": 2,
            "High": 3,
            "Very High": 4,
        }

        phase_idioms.sort(
            key=lambda x: complexity_order.get(x[1].complexity_hint, 999)
        )

        fallback_idiom = phase_idioms[0][1]
        logger.info(f"[FALLBACK] phase={phase} → {fallback_idiom.id}")

        return fallback_idiom, 0.0

    def list_idioms_by_phase(self, phase: str) -> List[CodeIdiom]:
        """List all idioms for a given phase."""
        return [idiom for idiom in self.space["idioms"] if idiom.phase == phase]

    def list_phases(self) -> List[str]:
        """List all phases in space."""
        return sorted(set(idiom.phase for idiom in self.space["idioms"]))

    def stats(self) -> Dict[str, Any]:
        """Return router statistics."""
        phases = {}
        for idiom in self.space["idioms"]:
            if idiom.phase not in phases:
                phases[idiom.phase] = 0
            phases[idiom.phase] += 1

        return {
            "model_name": self.space["model_name"],
            "embedding_dim": self.space["embedding_dim"],
            "total_idioms": len(self.space["idioms"]),
            "total_phases": len(phases),
            "phases": phases,
            "confidence_threshold": self.confidence_threshold,
        }


# ============================================================================
# DEMO / CLI
# ============================================================================


def demo():
    """Interactive demo of the router."""
    print("\n" + "=" * 70)
    print("PHASE IDIOM ROUTER — Interactive Demo")
    print("=" * 70)

    # Initialize router
    router = PhaseIdiomRouter("code_idioms.json")

    # Print stats
    stats = router.stats()
    print(f"\n[STATS]")
    print(f"  Model:       {stats['model_name']}")
    print(f"  Dimensions:  {stats['embedding_dim']}")
    print(f"  Total Idioms: {stats['total_idioms']}")
    print(f"  Phases:      {stats['total_phases']}")
    print()

    # Demo queries
    demo_queries = [
        ("briefing", "ANALYSIS", "Ich brauche ne gründliche Analyse mit Detail und Synthese"),
        ("briefing", "IMPLEMENTATION", "Strukturierte Briefing mit Goal, Files, Deps, Risks"),
        ("briefing", "ANALYSIS", "Schneller TL;DR, nur Top-3 Risiken"),
        ("planning_strategie", "IMPLEMENTATION", "Topological sort für Build-Reihenfolge"),
        ("planning_detailplan", None, "Hybrid Retrieval mit BM25 + Dense + Reranker"),
        ("execution", "IMPLEMENTATION", "Code-Generation mit Tests"),
        ("verify", None, "Fuzzing für Edge Cases"),
        ("commit", None, "Per-step commits mit klaren Messages"),
    ]

    print("[DEMO QUERIES]\n")
    for phase, task_type, requirement in demo_queries:
        idiom, score = router.route(phase, task_type, requirement)

        print(f"  Phase:      {phase}")
        print(f"  Task Type:  {task_type or 'generic'}")
        print(f"  Requirement: {requirement}")
        print(f"  → Selected:  {idiom.id} (score={score:.2f})")
        print(f"  → Pattern:   {list(idiom.patterns.keys())}")
        print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    demo()
