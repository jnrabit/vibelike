import pytest
from chaosgarten.mentions import extract_mentions, MentionIndex


# --- extract_mentions ---

def test_extract_mentions_single():
    assert extract_mentions("Hallo @alice wie geht's?") == ["alice"]


def test_extract_mentions_multiple():
    assert extract_mentions("@alice und @bob sind da") == ["alice", "bob"]


def test_extract_mentions_deduplicated():
    assert extract_mentions("@alice @bob @alice") == ["alice", "bob"]


def test_extract_mentions_at_alone_ignored():
    assert extract_mentions("schreib @ mir") == []
    assert extract_mentions("@ allein") == []
    assert extract_mentions("nur ein @ zeichen") == []


def test_extract_mentions_punctuation_after():
    assert extract_mentions("@alice, bitte meld dich") == ["alice"]
    assert extract_mentions("hey @bob!") == ["bob"]
    assert extract_mentions("danke @charlie.") == ["charlie"]


def test_extract_mentions_empty_and_no_mention():
    assert extract_mentions("") == []
    assert extract_mentions("kein mention hier") == []
    assert extract_mentions("nur text ohne at-zeichen") == []


# --- MentionIndex ---

def test_mention_index_mentions_of_multiple_messages():
    idx = MentionIndex()
    idx.add(1, "@alice komm bitte")
    idx.add(2, "hey @bob und @alice")
    idx.add(3, "@alice nochmal")

    assert idx.mentions_of("alice") == [1, 2, 3]
    assert idx.mentions_of("bob") == [2]
    assert idx.mentions_of("charlie") == []


def test_mention_index_mentioned_users():
    idx = MentionIndex()
    idx.add(10, "@alice und @bob hier")
    idx.add(20, "@charlie allein")

    assert idx.mentioned_users(10) == ["alice", "bob"]
    assert idx.mentioned_users(20) == ["charlie"]
    assert idx.mentioned_users(99) == []
    assert idx.mentioned_users(0) == []


def test_mention_index_no_duplicate_msg_ids_in_mentions_of():
    idx = MentionIndex()
    idx.add(5, "@alice test")
    idx.add(5, "@alice nochmal")  # same msg_id again

    assert idx.mentions_of("alice") == [5]


def test_mention_index_mentioned_users_order_preserved():
    idx = MentionIndex()
    idx.add(1, "@charlie @alice @bob")
    assert idx.mentioned_users(1) == ["charlie", "alice", "bob"]


def test_mention_index_at_alone_not_indexed():
    idx = MentionIndex()
    idx.add(1, "schreib @ mir und @ dir")
    assert idx.mentioned_users(1) == []
    assert idx.mentions_of("") == []


def test_mention_index_punctuation_in_message():
    idx = MentionIndex()
    idx.add(7, "@alice, kannst du @bob! fragen?")
    assert idx.mentioned_users(7) == ["alice", "bob"]
    assert idx.mentions_of("alice") == [7]
    assert idx.mentions_of("bob") == [7]