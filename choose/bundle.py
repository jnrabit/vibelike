from __future__ import annotations

import hashlib
from typing import Iterable, Iterator

from .predicate import DEFAULT_COST_HINT, Predicate


class PredicateBundle:
    """Ordered, immutable collection of predicates. Default cost_hint keeps
    the given order; any non-default value triggers stable sort by cost_hint."""

    __slots__ = ("_predicates",)

    def __init__(self, predicates: Iterable[Predicate]) -> None:
        items = tuple(predicates)
        if any(p.cost_hint != DEFAULT_COST_HINT for p in items):
            items = tuple(sorted(items, key=lambda p: p.cost_hint))
        object.__setattr__(self, "_predicates", items)

    def __iter__(self) -> Iterator[Predicate]:
        return iter(self._predicates)

    def __len__(self) -> int:
        return len(self._predicates)

    def __getitem__(self, index: int) -> Predicate:
        return self._predicates[index]

    def fingerprint(self) -> str:
        joined = "|".join(p.name for p in self._predicates)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()
