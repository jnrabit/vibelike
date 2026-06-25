"""Tests für die Idiom↔Ossifikat-Feedback-Schleife (③).

Beweist den GESCHLOSSENEN Kreis: record → load_boosts → Router-Bonus wirkt.
"""

import pytest

from idiom_feedback import IdiomFeedback


# ── Fake-Store (in-memory), erfüllt die genutzte OssifikatStore-Teil-API ──

class FakeTriple:
    def __init__(self, subject, predicate, object):
        self.subject = subject
        self.predicate = predicate
        self.object = object


class FakeStore:
    """Minimaler In-Memory-Store: add_staging + confirm + query."""

    def __init__(self):
        self._rows = []           # (id, subject, predicate, object, confirmed)
        self._next = 1

    def add_staging(self, subject, predicate, object, source, confidence=1.0):
        tid = self._next
        self._next += 1
        # created_at-Äquivalent: jede Staging-Zeile ist eigenständig (kein Dedup)
        self._rows.append({"id": tid, "subject": subject, "predicate": predicate,
                           "object": object, "confirmed": False})
        return tid

    def confirm(self, triple_id_or_hash, confirmed_by, confirmation_type="manual", note=None):
        for r in self._rows:
            if r["id"] == triple_id_or_hash:
                r["confirmed"] = True
                return
        raise ValueError("not found")

    def query(self, subject=None, predicate=None, only_confirmed=True, **kw):
        out = []
        for r in self._rows:
            if only_confirmed and not r["confirmed"]:
                continue
            if predicate is not None and r["predicate"] != predicate:
                continue
            if subject is not None and r["subject"] != subject:
                continue
            out.append(FakeTriple(r["subject"], r["predicate"], r["object"]))
        return out


# ───────────────────────────── Schreiben ─────────────────────────────

def test_record_approved_writes_confirmed_triple():
    store = FakeStore()
    fb = IdiomFeedback(store)
    assert fb.record_approved("brief::analysis::two_part", "briefing", "ANALYSIS")
    rows = store.query(predicate="idiom_approved_for")
    assert len(rows) == 1
    assert rows[0].subject == "brief::analysis::two_part"
    assert rows[0].object == "briefing::ANALYSIS"


def test_record_workflow_writes_all_phases():
    store = FakeStore()
    fb = IdiomFeedback(store)
    idioms = {
        "briefing": {"id": "brief::impl::structured", "task_type": "IMPLEMENTATION"},
        "execution": {"id": "exec::impl::code_gen", "task_type": "IMPLEMENTATION"},
    }
    assert fb.record_workflow(idioms) == 2
    assert len(store.query(predicate="idiom_approved_for")) == 2


def test_no_store_is_noop():
    fb = IdiomFeedback(None)
    assert fb.record_approved("x", "p", "t") is False
    assert fb.load_boosts() == {}


def test_empty_idiom_id_skipped():
    store = FakeStore()
    fb = IdiomFeedback(store)
    assert fb.record_approved("", "briefing", "ANALYSIS") is False


# ─────────────────────────────── Lesen ───────────────────────────────

def test_load_boosts_counts_and_caps():
    store = FakeStore()
    fb = IdiomFeedback(store)
    # 3x approved → boost = 3*0.01 = 0.03
    for _ in range(3):
        fb.record_approved("strat::impl::incremental", "planning_strategie", "IMPLEMENTATION")
    # 10x approved → boost gedeckelt auf MAX_BOOST (0.05)
    for _ in range(10):
        fb.record_approved("exec::impl::code_gen", "execution", "IMPLEMENTATION")

    boosts = fb.load_boosts()
    assert boosts["strat::impl::incremental"] == pytest.approx(0.03)
    assert boosts["exec::impl::code_gen"] == pytest.approx(0.05)  # gedeckelt


# ──────────────────────── GESCHLOSSENE SCHLEIFE ───────────────────────

def test_closed_loop_boost_flips_a_tie():
    """Der Kern: Bonus aus Approval-Historie bricht einen Score-Gleichstand."""
    store = FakeStore()
    fb = IdiomFeedback(store)
    # idiom_b wurde 5x bewährt → boost 0.05
    for _ in range(5):
        fb.record_approved("idiom_b", "execution", "IMPLEMENTATION")
    boosts = fb.load_boosts()

    # Simuliere Router-Scoring: a leicht vorn (0.70 vs 0.69), aber b hat Historie.
    raw = {"idiom_a": 0.70, "idiom_b": 0.69}
    adjusted = {k: v + boosts.get(k, 0.0) for k, v in raw.items()}
    winner = max(adjusted, key=adjusted.get)
    assert winner == "idiom_b"  # Historie kippt den Gleichstand

    # Gegenprobe: ohne Historie gewinnt a
    winner_raw = max(raw, key=raw.get)
    assert winner_raw == "idiom_a"
