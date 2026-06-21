#!/usr/bin/env python3
"""
Compile idiom_config.yaml → code_idioms.json (frozen embedding space).

Einmalig ausführen:
  python3 idiom_compiler.py --config idiom_config.yaml --model paraphrase-multilingual-MiniLM-L12-v2

Output:
  code_idioms.json — frozen dict mit embeddings, O(1) lookup by phase+task_type+semantic_sim

The compiled JSON is deterministic & versioned in git.
"""

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import yaml
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


@dataclass
class CodeIdiom:
    """Represents a single idiom in the space."""

    id: str
    phase: str
    task_type: Optional[str]  # "ANALYSIS", "IMPLEMENTATION", etc. or None
    description: str
    tags: List[str]
    complexity_hint: str
    tradeoff: str
    requires: List[str]
    patterns: Dict[str, str]
    metadata: Dict[str, Any]
    embedding: List[float]  # Will be computed by compiler


def load_idiom_config(config_path: str) -> List[Dict[str, Any]]:
    """Load idiom_config.yaml."""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    idioms = config.get("idioms", [])
    logger.info(f"Loaded {len(idioms)} idioms from {config_path}")
    return idioms


def encode_idiom_text(model: SentenceTransformer, idiom: Dict[str, Any]) -> np.ndarray:
    """
    Encode description + tags into a single embedding.
    Strategy: concatenate description + " ".join(tags), encode once.
    """
    description = idiom.get("description", "")
    tags = idiom.get("tags", [])

    text = f"{description} {' '.join(tags)}"
    embedding = model.encode(text, convert_to_numpy=True)

    return embedding


def validate_idiom_config(idioms: List[Dict[str, Any]]) -> None:
    """
    Validate idiom structure + detect issues.
    """
    ids_seen = set()

    for i, idiom in enumerate(idioms):
        # Check required fields
        required = ["id", "phase", "description", "tags", "complexity_hint", "tradeoff", "requires", "patterns", "metadata"]
        for field in required:
            if field not in idiom:
                raise ValueError(f"Idiom {i}: missing required field '{field}'")

        # Check ID uniqueness
        idiom_id = idiom["id"]
        if idiom_id in ids_seen:
            raise ValueError(f"Duplicate idiom ID: {idiom_id}")
        ids_seen.add(idiom_id)

        # Check phase is valid
        valid_phases = ["briefing", "planning_strategie", "planning_detailplan", "execution", "verify", "commit", "analysis_report"]
        if idiom["phase"] not in valid_phases:
            raise ValueError(f"Idiom {idiom_id}: invalid phase '{idiom['phase']}'")

        # Check task_type (can be None)
        task_type = idiom.get("task_type")
        valid_task_types = ["ANALYSIS", "IMPLEMENTATION", "BUG_FIX", "REFACTOR", "EXPLAIN", None]
        if task_type not in valid_task_types:
            raise ValueError(f"Idiom {idiom_id}: invalid task_type '{task_type}'")

        # Check patterns is dict
        if not isinstance(idiom.get("patterns", {}), dict):
            raise ValueError(f"Idiom {idiom_id}: patterns must be a dict")

        logger.debug(f"  ✓ Idiom {idiom_id} (phase={idiom['phase']}, task_type={task_type})")

    logger.info(f"✓ Validation passed: {len(idioms)} idioms, {len(ids_seen)} unique IDs")


def compile_idiom_space(
    config_path: str,
    model_name: str,
    output_path: str = "code_idioms.json",
) -> None:
    """
    Main compilation: YAML → embeddings → JSON.

    Args:
        config_path: Path to idiom_config.yaml
        model_name: SentenceTransformer model name
        output_path: Output JSON file
    """
    logger.info("=" * 70)
    logger.info("[COMPILE] Code-Idiom-Space")
    logger.info("=" * 70)

    # Step 1: Load config
    logger.info("\n[STEP 1] Loading config...")
    idiom_dicts = load_idiom_config(config_path)

    # Step 2: Validate
    logger.info("\n[STEP 2] Validating...")
    validate_idiom_config(idiom_dicts)

    # Step 3: Load model
    logger.info(f"\n[STEP 3] Loading model: {model_name}")
    try:
        model = SentenceTransformer(model_name)
        logger.info(f"  ✓ Model loaded: {model.get_sentence_embedding_dimension()}-dim embeddings")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise

    # Step 4: Encode embeddings
    logger.info("\n[STEP 4] Encoding embeddings...")
    idioms_with_embeddings = []

    for i, idiom_dict in enumerate(idiom_dicts):
        try:
            embedding = encode_idiom_text(model, idiom_dict)

            # Build CodeIdiom object
            code_idiom = CodeIdiom(
                id=idiom_dict["id"],
                phase=idiom_dict["phase"],
                task_type=idiom_dict.get("task_type"),
                description=idiom_dict["description"],
                tags=idiom_dict["tags"],
                complexity_hint=idiom_dict["complexity_hint"],
                tradeoff=idiom_dict["tradeoff"],
                requires=idiom_dict["requires"],
                patterns=idiom_dict["patterns"],
                metadata=idiom_dict["metadata"],
                embedding=embedding.tolist(),  # numpy → list for JSON
            )

            idioms_with_embeddings.append(code_idiom)

            if (i + 1) % 10 == 0:
                logger.debug(f"  Encoded {i + 1}/{len(idiom_dicts)} idioms...")

        except Exception as e:
            logger.error(f"Failed to encode idiom {i}: {e}")
            raise

    logger.info(f"  ✓ Encoded {len(idioms_with_embeddings)} idioms")

    # Step 5: Build frozen space dict
    logger.info("\n[STEP 5] Building frozen space...")

    space = {
        "version": "1.0",
        "model_name": model_name,
        "embedding_dim": model.get_sentence_embedding_dimension(),
        "count": len(idioms_with_embeddings),
        "idioms": [asdict(idiom) for idiom in idioms_with_embeddings],
    }

    # Step 6: Validate space structure
    logger.info("\n[STEP 6] Validating space structure...")
    phase_counts = {}
    task_type_counts = {}

    for idiom in idioms_with_embeddings:
        phase = idiom.phase
        task_type = idiom.task_type or "generic"

        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        task_type_counts[task_type] = task_type_counts.get(task_type, 0) + 1

        # Sanity check: embedding length
        if len(idiom.embedding) != space["embedding_dim"]:
            raise ValueError(
                f"Idiom {idiom.id}: embedding dim mismatch "
                f"(expected {space['embedding_dim']}, got {len(idiom.embedding)})"
            )

    logger.info("  ✓ Phase distribution:")
    for phase in sorted(phase_counts.keys()):
        logger.info(f"    {phase:30s} {phase_counts[phase]:3d} idioms")

    logger.info("  ✓ Task-type distribution:")
    for task_type in sorted(task_type_counts.keys()):
        logger.info(f"    {task_type:30s} {task_type_counts[task_type]:3d} idioms")

    # Step 7: Write JSON
    logger.info(f"\n[STEP 7] Writing JSON: {output_path}")
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(space, f, indent=2)

    # File size
    file_size_kb = output_file.stat().st_size / 1024
    logger.info(f"  ✓ Written: {file_size_kb:.1f} KB")

    # Step 8: Summary
    logger.info("\n" + "=" * 70)
    logger.info("[COMPILE] ✓ SUCCESS")
    logger.info("=" * 70)
    logger.info(f"  Input:        {config_path}")
    logger.info(f"  Model:        {model_name}")
    logger.info(f"  Output:       {output_file}")
    logger.info(f"  Idioms:       {len(idioms_with_embeddings)}")
    logger.info(f"  Dimensions:   {space['embedding_dim']}")
    logger.info(f"  File Size:    {file_size_kb:.1f} KB")
    logger.info("")
    logger.info("Now use phase_idiom_router.py to load code_idioms.json at runtime.")
    logger.info("=" * 70)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Compile idiom_config.yaml → code_idioms.json")
    parser.add_argument(
        "--config",
        default="idiom_config.yaml",
        help="Path to idiom_config.yaml (default: idiom_config.yaml)",
    )
    parser.add_argument(
        "--model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="SentenceTransformer model name (default: paraphrase-multilingual-MiniLM-L12-v2)",
    )
    parser.add_argument(
        "--out",
        default="code_idioms.json",
        help="Output JSON file (default: code_idioms.json)",
    )

    args = parser.parse_args()

    compile_idiom_space(
        config_path=args.config,
        model_name=args.model,
        output_path=args.out,
    )


if __name__ == "__main__":
    main()
