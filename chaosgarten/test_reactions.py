"""Pytest-Tests für chaosgarten.reactions — MessageThread und Message."""

import pytest
from chaosgarten.reactions import Message, MessageThread


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_thread(*texts_authors: tuple[str, str]) -> MessageThread:
    t = MessageThread()
    for text, author in texts_authors:
        t.add_message(text, author)
    return t


# ---------------------------------------------------------------------------
# add_message — fortlaufende IDs
# ---------------------------------------------------------------------------

def test_ids_start_at_one() -> None:
    t = MessageThread()
    msg = t.add_message("Hello", "Alice")
    assert msg.id == 1


def test_ids_are_sequential() -> None:
    t = MessageThread()
    ids = [t.add_message(f"msg{i}", "Alice").id for i in range(5)]
    assert ids == [1, 2, 3, 4, 5]


def test_add_message_returns_message_dataclass() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Bob")
    assert isinstance(msg, Message)
    assert msg.author == "Bob"
    assert msg.text == "Hi"
    assert msg.quote_of is None


# ---------------------------------------------------------------------------
# Zitat-Antworten
# ---------------------------------------------------------------------------

def test_quote_of_stored_on_message() -> None:
    t = MessageThread()
    t.add_message("Original", "Alice")
    reply = t.add_message("Reply", "Bob", quote_of=1)
    assert reply.quote_of == 1


def test_resolve_quote_returns_quoted_message() -> None:
    t = MessageThread()
    original = t.add_message("Original", "Alice")
    reply = t.add_message("Reply", "Bob", quote_of=1)
    resolved = t.resolve_quote(reply.id)
    assert resolved == original


def test_resolve_quote_returns_none_when_no_quote() -> None:
    t = MessageThread()
    msg = t.add_message("Plain", "Alice")
    assert t.resolve_quote(msg.id) is None


def test_quote_of_nonexistent_id_raises() -> None:
    t = MessageThread()
    with pytest.raises(ValueError):
        t.add_message("Reply", "Bob", quote_of=99)


def test_quote_of_zero_raises() -> None:
    t = MessageThread()
    with pytest.raises(ValueError):
        t.add_message("Reply", "Bob", quote_of=0)


def test_quote_chain() -> None:
    """A → B → C: resolve_quote follows one level at a time."""
    t = MessageThread()
    a = t.add_message("A", "Alice")
    b = t.add_message("B", "Bob", quote_of=a.id)
    c = t.add_message("C", "Carol", quote_of=b.id)
    assert t.resolve_quote(c.id) == b
    assert t.resolve_quote(b.id) == a


# ---------------------------------------------------------------------------
# react — idempotenz
# ---------------------------------------------------------------------------

def test_react_adds_reaction() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    assert t.counts(msg.id) == {"👍": 1}


def test_react_is_idempotent() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    t.react(msg.id, "Bob", "👍")
    t.react(msg.id, "Bob", "👍")
    assert t.counts(msg.id) == {"👍": 1}


def test_react_different_users_same_emoji() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "❤️")
    t.react(msg.id, "Carol", "❤️")
    assert t.counts(msg.id) == {"❤️": 2}


def test_react_same_user_different_emojis() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    t.react(msg.id, "Bob", "❤️")
    assert t.counts(msg.id) == {"👍": 1, "❤️": 1}


def test_react_unknown_msg_raises() -> None:
    t = MessageThread()
    with pytest.raises(ValueError):
        t.react(42, "Bob", "👍")


# ---------------------------------------------------------------------------
# unreact
# ---------------------------------------------------------------------------

def test_unreact_returns_true_when_removed() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    assert t.unreact(msg.id, "Bob", "👍") is True


def test_unreact_returns_false_when_not_set() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    assert t.unreact(msg.id, "Bob", "👍") is False


def test_unreact_removes_reaction() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    t.unreact(msg.id, "Bob", "👍")
    assert t.counts(msg.id) == {}


def test_unreact_only_removes_matching_pair() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    t.react(msg.id, "Carol", "👍")
    t.unreact(msg.id, "Bob", "👍")
    assert t.counts(msg.id) == {"👍": 1}
    assert t.reactors(msg.id, "👍") == ["Carol"]


def test_unreact_unknown_msg_raises() -> None:
    t = MessageThread()
    with pytest.raises(ValueError):
        t.unreact(99, "Bob", "👍")


def test_unreact_twice_second_returns_false() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    assert t.unreact(msg.id, "Bob", "👍") is True
    assert t.unreact(msg.id, "Bob", "👍") is False


# ---------------------------------------------------------------------------
# counts
# ---------------------------------------------------------------------------

def test_counts_empty_when_no_reactions() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    assert t.counts(msg.id) == {}


def test_counts_multiple_emojis() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    t.react(msg.id, "Carol", "👍")
    t.react(msg.id, "Dave", "❤️")
    c = t.counts(msg.id)
    assert c["👍"] == 2
    assert c["❤️"] == 1


def test_counts_unknown_msg_raises() -> None:
    t = MessageThread()
    with pytest.raises(ValueError):
        t.counts(7)


# ---------------------------------------------------------------------------
# reactors
# ---------------------------------------------------------------------------

def test_reactors_returns_correct_users() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    t.react(msg.id, "Carol", "👍")
    t.react(msg.id, "Dave", "❤️")
    result = sorted(t.reactors(msg.id, "👍"))
    assert result == ["Bob", "Carol"]


def test_reactors_empty_for_unused_emoji() -> None:
    t = MessageThread()
    msg = t.add_message("Hi", "Alice")
    t.react(msg.id, "Bob", "👍")
    assert t.reactors(msg.id, "❤️") == []


def test_reactors_unknown_msg_raises() -> None:
    t = MessageThread()
    with pytest.raises(ValueError):
        t.reactors(5, "👍")


# ---------------------------------------------------------------------------
# resolve_quote — ValueError für unbekannte msg_id
# ---------------------------------------------------------------------------

def test_resolve_quote_unknown_msg_raises() -> None:
    t = MessageThread()
    with pytest.raises(ValueError):
        t.resolve_quote(100)


# ---------------------------------------------------------------------------
# Isolation zwischen Threads
# ---------------------------------------------------------------------------

def test_two_threads_are_independent() -> None:
    t1 = MessageThread()
    t2 = MessageThread()
    m1 = t1.add_message("Hello", "Alice")
    m2 = t2.add_message("World", "Bob")
    assert m1.id == m2.id == 1
    t1.react(m1.id, "Carol", "👍")
    assert t2.counts(m2.id) == {}