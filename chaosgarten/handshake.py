from enum import Enum


class HandshakeState(Enum):
    INIT = 1
    KEY_EXCHANGED = 2
    CONFIRMED = 3
    FAILED = 4


_FINAL_STATES = {HandshakeState.CONFIRMED, HandshakeState.FAILED}

_TRANSITIONS: dict[HandshakeState, dict[str, HandshakeState]] = {
    HandshakeState.INIT: {
        "send_key": HandshakeState.KEY_EXCHANGED,
        "fail": HandshakeState.FAILED,
    },
    HandshakeState.KEY_EXCHANGED: {
        "confirm": HandshakeState.CONFIRMED,
        "fail": HandshakeState.FAILED,
    },
}


class Handshake:
    """Key-Exchange Handshake State Machine.

    Legal transitions:
        INIT      --'send_key'--> KEY_EXCHANGED
        INIT      --'fail'------> FAILED
        KEY_EXCHANGED --'confirm'--> CONFIRMED
        KEY_EXCHANGED --'fail'-----> FAILED

    CONFIRMED and FAILED are final states; any further advance raises ValueError.
    Any event not listed for the current state raises ValueError.
    """

    def __init__(self) -> None:
        self.state: HandshakeState = HandshakeState.INIT

    def advance(self, event: str) -> HandshakeState:
        """Apply *event* to the current state and return the new state.

        Raises:
            ValueError: If the current state is final, or the event is not
                        valid for the current state.
        """
        if self.state in _FINAL_STATES:
            raise ValueError(
                f"Cannot advance from final state {self.state.name!r} "
                f"(event={event!r})"
            )

        allowed = _TRANSITIONS.get(self.state, {})
        if event not in allowed:
            raise ValueError(
                f"Invalid event {event!r} in state {self.state.name!r}. "
                f"Allowed events: {sorted(allowed)}"
            )

        self.state = allowed[event]
        return self.state