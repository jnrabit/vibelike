import re


def extract_mentions(text: str) -> list[str]:
    """Extract @-mentioned usernames from text.

    Returns usernames (without '@') in order of first occurrence, deduplicated.
    '@' alone (no word characters following) is ignored.
    Punctuation after a username is not included.
    """
    raw = re.findall(r'@(\w+)', text)
    return list(dict.fromkeys(raw))


class MentionIndex:
    """Index mapping messages to their @-mentioned users and vice versa."""

    def __init__(self) -> None:
        self._by_user: dict[str, list[int]] = {}   # user → [msg_id, ...] insertion order
        self._by_msg: dict[int, list[str]] = {}    # msg_id → [user, ...] insertion order
        self._seen: dict[str, set[int]] = {}       # user → {msg_ids already recorded}

    def add(self, msg_id: int, text: str) -> None:
        """Parse mentions in text and index which message mentions which users."""
        users = extract_mentions(text)
        # Store ordered user list for this message (last write wins for same msg_id)
        self._by_msg[msg_id] = users

        for user in users:
            if user not in self._seen:
                self._seen[user] = set()
            if msg_id not in self._seen[user]:
                self._seen[user].add(msg_id)
                if user not in self._by_user:
                    self._by_user[user] = []
                self._by_user[user].append(msg_id)

    def mentions_of(self, user: str) -> list[int]:
        """Return msg_ids that mention this user, in insertion order, deduplicated."""
        return self._by_user.get(user, [])

    def mentioned_users(self, msg_id: int) -> list[str]:
        """Return users mentioned in this message, in order of appearance.

        Returns [] for unknown msg_id.
        """
        return self._by_msg.get(msg_id, [])