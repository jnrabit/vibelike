from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Union


class UndecidableReason(Enum):
    ALL_PREDICATES_DEFERRED = "ALL_PREDICATES_DEFERRED"
    NO_CANDIDATE_ACCEPTED = "NO_CANDIDATE_ACCEPTED"
    EMPTY_CANDIDATES = "EMPTY_CANDIDATES"
    EMPTY_BUNDLE = "EMPTY_BUNDLE"


@dataclass(frozen=True)
class Decided:
    candidate: Any


@dataclass(frozen=True)
class Undecidable:
    reason: UndecidableReason


Outcome = Union[Decided, Undecidable]


@dataclass(frozen=True)
class Choice:
    outcome: Outcome
    deciding_predicate: str | None
    unused_predicates: tuple[str, ...]
    reproducibility_hash: str
