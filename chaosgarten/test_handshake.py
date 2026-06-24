import pytest

from vibelike.chaosgarten.handshake import Handshake, HandshakeState


# ---------------------------------------------------------------------------
# Legal paths
# ---------------------------------------------------------------------------

def test_happy_path_full():
    """INIT -> KEY_EXCHANGED -> CONFIRMED"""
    h = Handshake()
    assert h.state == HandshakeState.INIT

    result = h.advance("send_key")
    assert result == HandshakeState.KEY_EXCHANGED
    assert h.state == HandshakeState.KEY_EXCHANGED

    result = h.advance("confirm")
    assert result == HandshakeState.CONFIRMED
    assert h.state == HandshakeState.CONFIRMED


def test_fail_from_init():
    """INIT --'fail'--> FAILED"""
    h = Handshake()
    result = h.advance("fail")
    assert result == HandshakeState.FAILED
    assert h.state == HandshakeState.FAILED


def test_fail_from_key_exchanged():
    """KEY_EXCHANGED --'fail'--> FAILED"""
    h = Handshake()
    h.advance("send_key")
    result = h.advance("fail")
    assert result == HandshakeState.FAILED
    assert h.state == HandshakeState.FAILED


# ---------------------------------------------------------------------------
# Final states block further transitions
# ---------------------------------------------------------------------------

def test_confirmed_is_final():
    h = Handshake()
    h.advance("send_key")
    h.advance("confirm")
    assert h.state == HandshakeState.CONFIRMED

    with pytest.raises(ValueError, match="final state"):
        h.advance("confirm")


def test_confirmed_is_final_any_event():
    h = Handshake()
    h.advance("send_key")
    h.advance("confirm")

    for event in ("send_key", "confirm", "fail", "whatever"):
        with pytest.raises(ValueError):
            h.advance(event)


def test_failed_is_final():
    h = Handshake()
    h.advance("fail")
    assert h.state == HandshakeState.FAILED

    with pytest.raises(ValueError, match="final state"):
        h.advance("fail")


def test_failed_is_final_any_event():
    h = Handshake()
    h.advance("fail")

    for event in ("send_key", "confirm", "fail", "whatever"):
        with pytest.raises(ValueError):
            h.advance(event)


# ---------------------------------------------------------------------------
# Illegal events in non-final states
# ---------------------------------------------------------------------------

def test_invalid_event_in_init():
    h = Handshake()
    with pytest.raises(ValueError, match="Invalid event"):
        h.advance("confirm")


def test_unknown_event_in_init():
    h = Handshake()
    with pytest.raises(ValueError):
        h.advance("bogus")


def test_invalid_event_in_key_exchanged():
    h = Handshake()
    h.advance("send_key")
    with pytest.raises(ValueError, match="Invalid event"):
        h.advance("send_key")  # already past INIT


def test_unknown_event_in_key_exchanged():
    h = Handshake()
    h.advance("send_key")
    with pytest.raises(ValueError):
        h.advance("bogus")


# ---------------------------------------------------------------------------
# State is not mutated on error
# ---------------------------------------------------------------------------

def test_state_unchanged_after_invalid_event():
    h = Handshake()
    with pytest.raises(ValueError):
        h.advance("confirm")
    assert h.state == HandshakeState.INIT  # unchanged


def test_state_unchanged_after_invalid_event_key_exchanged():
    h = Handshake()
    h.advance("send_key")
    with pytest.raises(ValueError):
        h.advance("send_key")
    assert h.state == HandshakeState.KEY_EXCHANGED  # unchanged


# ---------------------------------------------------------------------------
# Fresh instance always starts at INIT
# ---------------------------------------------------------------------------

def test_initial_state():
    for _ in range(3):
        h = Handshake()
        assert h.state == HandshakeState.INIT