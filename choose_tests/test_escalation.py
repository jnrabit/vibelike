from dataclasses import dataclass, field

from choose import Decided, Predicate, PredicateBundle, Verdict, choose


@dataclass
class CountingEvaluator:
    verdict: Verdict
    calls: int = field(default=0)

    def __call__(self, _candidate) -> Verdict:
        self.calls += 1
        return self.verdict


def test_later_predicates_are_not_called_once_a_decision_is_made():
    first = CountingEvaluator(Verdict.ACCEPT)
    second = CountingEvaluator(Verdict.ACCEPT)
    third = CountingEvaluator(Verdict.ACCEPT)

    bundle = PredicateBundle(
        [
            Predicate(name="first", evaluate=first),
            Predicate(name="second", evaluate=second),
            Predicate(name="third", evaluate=third),
        ]
    )

    result = choose(bundle, candidates=["only"])

    assert isinstance(result.outcome, Decided)
    assert first.calls == 1
    assert second.calls == 0
    assert third.calls == 0


def test_unused_predicates_contains_exactly_the_ones_not_called():
    first = CountingEvaluator(Verdict.DEFER)
    second = CountingEvaluator(Verdict.ACCEPT)
    third = CountingEvaluator(Verdict.ACCEPT)
    fourth = CountingEvaluator(Verdict.ACCEPT)

    bundle = PredicateBundle(
        [
            Predicate(name="first", evaluate=first),
            Predicate(name="second", evaluate=second),
            Predicate(name="third", evaluate=third),
            Predicate(name="fourth", evaluate=fourth),
        ]
    )

    result = choose(bundle, candidates=["x"])

    assert isinstance(result.outcome, Decided)
    assert result.deciding_predicate == "second"
    assert result.unused_predicates == ("third", "fourth")
    assert first.calls == 1
    assert second.calls == 1
    assert third.calls == 0
    assert fourth.calls == 0
