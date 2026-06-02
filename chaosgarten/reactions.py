"""Backend-agnostische Modellschicht für Chat-Reaktionen und Zitat-Antworten in einem E2E-Messenger."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Message:
    """Repräsentiert eine einzelne Nachricht in einem MessageThread."""

    id: int
    author: str
    text: str
    quote_of: int | None = None


class MessageThread:
    """Verwaltet eine geordnete Sammlung von Nachrichten samt Reaktionen und Zitat-Verknüpfungen."""

    def __init__(self) -> None:
        self._messages: dict[int, Message] = {}
        self._reactions: dict[int, set[tuple[str, str]]] = {}
        self._next_id: int = 1

    def _require_msg(self, msg_id: int) -> Message:
        if msg_id not in self._messages:
            raise ValueError(f"No message with id {msg_id}")
        return self._messages[msg_id]

    def add_message(self, text: str, author: str, quote_of: int | None = None) -> Message:
        """Fügt eine neue Nachricht hinzu und gibt sie zurück.

        Raises:
            ValueError: Wenn quote_of gesetzt ist, aber keine Nachricht mit dieser id existiert.
        """
        if quote_of is not None and quote_of not in self._messages:
            raise ValueError(f"Cannot quote unknown message id {quote_of}")
        msg = Message(id=self._next_id, author=author, text=text, quote_of=quote_of)
        self._messages[self._next_id] = msg
        self._next_id += 1
        return msg

    def react(self, msg_id: int, user: str, emoji: str) -> None:
        """Fügt eine Emoji-Reaktion hinzu; dieselbe (user, emoji)-Kombination ist idempotent.

        Raises:
            ValueError: Wenn msg_id unbekannt ist.
        """
        self._require_msg(msg_id)
        self._reactions.setdefault(msg_id, set()).add((user, emoji))

    def unreact(self, msg_id: int, user: str, emoji: str) -> bool:
        """Entfernt eine Reaktion.

        Returns:
            True wenn die Reaktion entfernt wurde, False wenn sie nicht gesetzt war.

        Raises:
            ValueError: Wenn msg_id unbekannt ist.
        """
        self._require_msg(msg_id)
        bucket = self._reactions.get(msg_id, set())
        pair = (user, emoji)
        if pair in bucket:
            bucket.discard(pair)
            return True
        return False

    def counts(self, msg_id: int) -> dict[str, int]:
        """Gibt die Anzahl je Emoji für eine Nachricht zurück.

        Raises:
            ValueError: Wenn msg_id unbekannt ist.
        """
        self._require_msg(msg_id)
        result: dict[str, int] = {}
        bucket = self._reactions.get(msg_id, set())
        for _user, emoji in bucket:
            result[emoji] = result.get(emoji, 0) + 1
        return result

    def reactors(self, msg_id: int, emoji: str) -> list[str]:
        """Gibt die Liste der User zurück, die mit dem angegebenen Emoji reagiert haben.

        Raises:
            ValueError: Wenn msg_id unbekannt ist.
        """
        self._require_msg(msg_id)
        bucket = self._reactions.get(msg_id, set())
        return [user for user, e in bucket if e == emoji]

    def resolve_quote(self, msg_id: int) -> Message | None:
        """Gibt die zitierte Nachricht zurück, oder None wenn keine Zitat-Verknüpfung besteht.

        Raises:
            ValueError: Wenn msg_id unbekannt ist.
        """
        msg = self._require_msg(msg_id)
        if msg.quote_of is None:
            return None
        # Direkter dict-Zugriff statt .get() in einer potenziellen Schleife –
        # quote_of wurde beim add_message validiert, daher ist der Schlüssel garantiert vorhanden.
        return self._messages[msg.quote_of]

    def resolve_quotes_bulk(self, msg_ids: list[int]) -> dict[int, Message | None]:
        """Löst Zitat-Verknüpfungen für mehrere Nachrichten in einem Schritt auf (kein N+1).

        Args:
            msg_ids: Liste der Nachrichten-IDs, deren Zitate aufgelöst werden sollen.

        Returns:
            Dict von msg_id → zitierte Message (oder None).

        Raises:
            ValueError: Wenn eine der msg_ids unbekannt ist.
        """
        # Alle angeforderten Nachrichten in einem Schritt laden – kein wiederholtes .get()
        messages = {mid: self._require_msg(mid) for mid in msg_ids}

        # Alle benötigten quote_of-IDs sammeln
        quote_ids = {msg.quote_of for msg in messages.values() if msg.quote_of is not None}

        # Zitierte Nachrichten in einem einzigen Batch-Lookup holen
        quoted_messages: dict[int, Message] = {
            qid: self._messages[qid] for qid in quote_ids if qid in self._messages
        }

        return {
            mid: quoted_messages.get(msg.quote_of) if msg.quote_of is not None else None
            for mid, msg in messages.items()
        }