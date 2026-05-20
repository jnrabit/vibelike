"""Demo: the atom is stateless, the caller iterates.

Run with `python -m tests.examples.demo_iteration` from the repo root.
"""
from __future__ import annotations

from choose import (
    Decided,
    Predicate,
    PredicateBundle,
    Undecidable,
    UndecidableReason,
    Verdict,
    choose,
)


def react_to_all_deferred() -> None:
    """If everything deferred, the caller adds a stronger predicate."""
    weak = Predicate(name="ist-null", evaluate=lambda x: Verdict.ACCEPT if x == 0 else Verdict.DEFER)
    bundle = PredicateBundle([weak])
    candidates = [1, 2, 3]

    first = choose(bundle, candidates)
    assert isinstance(first.outcome, Undecidable)
    assert first.outcome.reason is UndecidableReason.ALL_PREDICATES_DEFERRED
    print(f"[1] first call undecidable: {first.outcome.reason.value}")

    stronger = Predicate(
        name="ist-gerade",
        evaluate=lambda x: Verdict.ACCEPT if x % 2 == 0 else Verdict.REJECT,
    )
    bundle_v2 = PredicateBundle([weak, stronger])
    second = choose(bundle_v2, candidates)
    assert isinstance(second.outcome, Decided)
    print(f"[1] after adding predicate: decided on {second.outcome.candidate!r} via {second.deciding_predicate!r}")


def react_to_no_candidate_accepted() -> None:
    """If everything was rejected, the caller produces new candidates."""
    only_zero = Predicate(
        name="nur-null",
        evaluate=lambda x: Verdict.ACCEPT if x == 0 else Verdict.REJECT,
    )
    bundle = PredicateBundle([only_zero])

    first = choose(bundle, candidates=[1, 2, 3])
    assert isinstance(first.outcome, Undecidable)
    assert first.outcome.reason is UndecidableReason.NO_CANDIDATE_ACCEPTED
    print(f"[2] first call undecidable: {first.outcome.reason.value}")

    second = choose(bundle, candidates=[7, 0, 9])
    assert isinstance(second.outcome, Decided)
    print(f"[2] with new candidates: decided on {second.outcome.candidate!r} via {second.deciding_predicate!r}")


def main() -> None:
    react_to_all_deferred()
    react_to_no_candidate_accepted()
    print("demo done — atom stayed stateless, caller drove the loop")


if __name__ == "__main__":
    main()
