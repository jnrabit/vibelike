import pytest
from vibelike.chaosgarten.mentions import extract_mentions, MentionIndex


# --- Block A: extract_mentions() ---

def test_extract_mentions_einfache_mention():
    assert extract_mentions("Hallo @alice wie geht's?") == ["alice"]


def test_extract_mentions_mehrere_mentions():
    assert extract_mentions("@alice und @bob sind hier") == ["alice", "bob"]


def test_extract_mentions_duplizierte_mentions():
    assert extract_mentions("@alice @bob @alice") == ["alice", "bob"]


def test_extract_mentions_at_allein_ignoriert():
    assert extract_mentions("Schreib mir @ oder so") == []


def test_extract_mentions_at_allein_gemischt():
    assert extract_mentions("@ und @bob") == ["bob"]


def test_extract_mentions_satzzeichen_nach_mention():
    assert extract_mentions("Hey @alice, kommst du?") == ["alice"]


def test_extract_mentions_satzzeichen_ausrufezeichen():
    assert extract_mentions("Danke @bob!") == ["bob"]


def test_extract_mentions_satzzeichen_punkt():
    assert extract_mentions("Frag @charlie.") == ["charlie"]


def test_extract_mentions_leerer_text():
    assert extract_mentions("") == []


def test_extract_mentions_kein_at():
    assert extract_mentions("Hallo Welt, kein Mention hier") == []


def test_extract_mentions_username_mit_ziffern():
    assert extract_mentions("@user123 meldet sich") == ["user123"]


def test_extract_mentions_username_mit_unterstrich():
    assert extract_mentions("@super_user ist da") == ["super_user"]


def test_extract_mentions_reihenfolge_erhalten():
    assert extract_mentions("@charlie @alice @bob @alice @charlie") == ["charlie", "alice", "bob"]


# --- Block B: MentionIndex.add() + mentioned_users() ---

def test_mentioned_users_einfach():
    idx = MentionIndex()
    idx.add(1, "Hey @alice und @bob")
    assert idx.mentioned_users(1) == ["alice", "bob"]


def test_mentioned_users_unbekannte_msg_id():
    idx = MentionIndex()
    assert idx.mentioned_users(999) == []


def test_mentioned_users_leere_message():
    idx = MentionIndex()
    idx.add(42, "Kein Mention hier")
    assert idx.mentioned_users(42) == []


def test_mentioned_users_duplizierte_mentions_in_text():
    idx = MentionIndex()
    idx.add(1, "@alice @alice @alice")
    assert idx.mentioned_users(1) == ["alice"]


# --- Block C: MentionIndex.mentions_of() ---

def test_mentions_of_einfach():
    idx = MentionIndex()
    idx.add(10, "Hallo @alice")
    assert idx.mentions_of("alice") == [10]


def test_mentions_of_unbekannter_user():
    idx = MentionIndex()
    assert idx.mentions_of("niemand") == []


def test_mentions_of_ueber_mehrere_messages():
    idx = MentionIndex()
    idx.add(1, "@alice kommt")
    idx.add(2, "@bob und @alice")
    idx.add(3, "@alice nochmal")
    assert idx.mentions_of("alice") == [1, 2, 3]
    assert idx.mentions_of("bob") == [2]


def test_mentions_of_dedupliziert_bei_doppeltem_add():
    idx = MentionIndex()
    idx.add(5, "@alice test")
    idx.add(5, "@alice test")
    assert idx.mentions_of("alice") == [5]


def test_mentions_of_einfuegereihenfolge():
    idx = MentionIndex()
    idx.add(100, "@zara hier")
    idx.add(50, "@zara auch")
    idx.add(75, "@zara nochmal")
    assert idx.mentions_of("zara") == [100, 50, 75]


# --- Block D: Kombinierte Szenarien ---

def test_vollstaendiges_szenario():
    idx = MentionIndex()
    idx.add(1, "@alice und @bob treffen @charlie")
    idx.add(2, "@bob schreibt @alice")
    idx.add(3, "Kein Mention")
    idx.add(4, "@alice @alice @bob")

    assert idx.mentioned_users(1) == ["alice", "bob", "charlie"]
    assert idx.mentioned_users(2) == ["bob", "alice"]
    assert idx.mentioned_users(3) == []
    assert idx.mentioned_users(4) == ["alice", "bob"]

    assert idx.mentions_of("alice") == [1, 2, 4]
    assert idx.mentions_of("bob") == [1, 2, 4]
    assert idx.mentions_of("charlie") == [1]
    assert idx.mentions_of("niemand") == []


def test_at_allein_in_message_ignoriert():
    idx = MentionIndex()
    idx.add(1, "Schreib @ oder so @alice")
    assert idx.mentioned_users(1) == ["alice"]
    assert idx.mentions_of("alice") == [1]
    assert idx.mentions_of("") == []