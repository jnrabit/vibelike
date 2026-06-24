from vibelike.choose import (
    Predicate,
    PredicateBundle,
    Undecidable,
    UndecidableReason,
    Verdict,
    choose,
)


def test_all_deferred_is_distinct_from_no_candidate_accepted():
    bundle = PredicateBundle(
        [
            Predicate(name="defer-a", evaluate=lambda _x: Verdict.DEFER),
            Predicate(name="defer-b", evaluate=lambda _x: Verdict.DEFER),
        ]
    )
    result = choose(bundle, candidates=[1, 2, 3])

    assert isinstance(result.outcome, Undecidable)
    assert result.outcome.reason is UndecidableReason.ALL_PREDICATES_DEFERRED


def test_any_reject_without_accept_yields_no_candidate_accepted():
    def maybe_reject(x):
        return Verdict.REJECT if x == 2 else Verdict.DEFER

    bundle = PredicateBundle(
        [
            Predicate(name="picky", evaluate=maybe_reject),
            Predicate(name="defer-all", evaluate=lambda _x: Verdict.DEFER),
        ]
    )
    result = choose(bundle, candidates=[1, 2, 3])

    assert isinstance(result.outcome, Undecidable)
    assert result.outcome.reason is UndecidableReason.NO_CANDIDATE_ACCEPTED
