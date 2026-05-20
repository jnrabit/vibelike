from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


DEFAULT_COST_HINT = 100


class Verdict(Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DEFER = "DEFER"


@dataclass(frozen=True)
class Predicate:
    name: str
    evaluate: Callable[[Any], Verdict]
    cost_hint: int = field(default=DEFAULT_COST_HINT)
