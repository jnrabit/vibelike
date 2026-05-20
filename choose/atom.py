from __future__ import annotations

import hashlib
from typing import Any, Sequence

from .bundle import PredicateBundle
from .choice import (
    Choice,
    Decided,
    Undecidable,
    UndecidableReason,
)
from .predicate import Verdict


def _candidate_repr(candidate: Any) -> str:
    if type(candidate).__repr__ is object.__repr__:
        raise ValueError(
            f"Candidate of type {type(candidate).__name__!r} uses the default "
            "object __repr__ (memory address). Provide a stable __repr__ so "
            "the reproducibility hash stays meaningful."
        )
    return repr(candidate)


def _compute_hash(bundle: PredicateBundle, candidates: Sequence[Any]) -> str:
    parts = [bundle.fingerprint(), *(_candidate_repr(c) for c in candidates)]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _undecidable(reason: UndecidableReason, repro_hash: str, unused: tuple[str, ...] = ()) -> Choice:
    return Choice(Undecidable(reason), None, unused, repro_hash)


def choose(bundle: PredicateBundle, candidates: Sequence[Any]) -> Choice:
    """Deterministically pick the first candidate a predicate accepts.

    Cheap predicates run first. If nothing accepts, Undecidable distinguishes
    "everything deferred" from "something was rejected".
    """
    repro_hash = _compute_hash(bundle, candidates)

    if len(bundle) == 0:
        return _undecidable(UndecidableReason.EMPTY_BUNDLE, repro_hash)
    if len(candidates) == 0:
        return _undecidable(
            UndecidableReason.EMPTY_CANDIDATES,
            repro_hash,
            unused=tuple(p.name for p in bundle),
        )

    predicates = tuple(bundle)
    saw_reject = False
    for i, predicate in enumerate(predicates):
        for candidate in candidates:
            verdict = predicate.evaluate(candidate)
            if verdict is Verdict.ACCEPT:
                unused = tuple(p.name for p in predicates[i + 1 :])
                return Choice(Decided(candidate), predicate.name, unused, repro_hash)
            if verdict is Verdict.REJECT:
                saw_reject = True

    reason = (
        UndecidableReason.NO_CANDIDATE_ACCEPTED
        if saw_reject
        else UndecidableReason.ALL_PREDICATES_DEFERRED
    )
    return _undecidable(reason, repro_hash)
