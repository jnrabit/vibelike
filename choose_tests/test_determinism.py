from choose import Predicate, PredicateBundle, Verdict, choose


def _is_even(x):
    return Verdict.ACCEPT if x % 2 == 0 else Verdict.REJECT


def _build_bundle():
    return PredicateBundle(
        [
            Predicate(name="even", evaluate=_is_even),
        ]
    )


def test_same_input_same_choice_and_hash():
    bundle = _build_bundle()
    candidates = [1, 2, 3, 4]

    first = choose(bundle, candidates)
    second = choose(bundle, candidates)

    assert first == second
    assert first.reproducibility_hash == second.reproducibility_hash


def test_reordered_candidates_change_hash_and_possibly_choice():
    bundle = _build_bundle()

    a = choose(bundle, [1, 2, 3, 4])
    b = choose(bundle, [4, 3, 2, 1])

    assert a.reproducibility_hash != b.reproducibility_hash
    # Order also determines which candidate is picked first.
    assert a.outcome != b.outcome


def test_new_bundle_object_with_same_predicates_has_same_fingerprint():
    bundle_one = _build_bundle()
    bundle_two = _build_bundle()

    assert bundle_one is not bundle_two
    assert bundle_one.fingerprint() == bundle_two.fingerprint()

    candidates = [1, 2, 3, 4]
    assert (
        choose(bundle_one, candidates).reproducibility_hash
        == choose(bundle_two, candidates).reproducibility_hash
    )
