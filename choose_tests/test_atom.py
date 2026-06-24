from vibelike.choose import (
    Decided,
    Predicate,
    PredicateBundle,
    Undecidable,
    UndecidableReason,
    Verdict,
    choose,
)


def _always(verdict: Verdict):
    return lambda _x: verdict


def test_accepts_first_candidate():
    bundle = PredicateBundle([Predicate(name="accept-all", evaluate=_always(Verdict.ACCEPT))])
    result = choose(bundle, candidates=[10, 20, 30])

    assert isinstance(result.outcome, Decided)
    assert result.outcome.candidate == 10
    assert result.deciding_predicate == "accept-all"
    assert result.unused_predicates == ()


def test_all_reject_yields_no_candidate_accepted():
    bundle = PredicateBundle([Predicate(name="reject-all", evaluate=_always(Verdict.REJECT))])
    result = choose(bundle, candidates=[1, 2, 3])

    assert isinstance(result.outcome, Undecidable)
    assert result.outcome.reason is UndecidableReason.NO_CANDIDATE_ACCEPTED
    assert result.deciding_predicate is None


def test_defer_chain_escalates_to_next_predicate():
    bundle = PredicateBundle(
        [
            Predicate(name="defer", evaluate=_always(Verdict.DEFER)),
            Predicate(name="accept", evaluate=_always(Verdict.ACCEPT)),
        ]
    )
    result = choose(bundle, candidates=["a", "b"])

    assert isinstance(result.outcome, Decided)
    assert result.outcome.candidate == "a"
    assert result.deciding_predicate == "accept"
    assert result.unused_predicates == ()


def test_empty_bundle_is_undecidable():
    bundle = PredicateBundle([])
    result = choose(bundle, candidates=[1, 2])

    assert isinstance(result.outcome, Undecidable)
    assert result.outcome.reason is UndecidableReason.EMPTY_BUNDLE


def test_duplicate_candidates_first_wins_documented():
    # Clarification test: choose() does not deduplicate. With [5, 5, 5] the
    # first 5 is decided; the rest are syntactically present but never reached.
    # This is intentional — dedup belongs in the caller, not the atom.
    bundle = PredicateBundle(
        [Predicate(name="positive", evaluate=lambda x: Verdict.ACCEPT if x > 0 else Verdict.REJECT)]
    )
    result = choose(bundle, candidates=[5, 5, 5])

    assert isinstance(result.outcome, Decided)
    assert result.outcome.candidate == 5
    assert result.deciding_predicate == "positive"


def test_empty_candidates_is_undecidable():
    bundle = PredicateBundle([Predicate(name="accept", evaluate=_always(Verdict.ACCEPT))])
    result = choose(bundle, candidates=[])

    assert isinstance(result.outcome, Undecidable)
    assert result.outcome.reason is UndecidableReason.EMPTY_CANDIDATES
