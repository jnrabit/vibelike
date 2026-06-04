import re

PATTERN = re.compile(r'@([A-Za-z0-9_]+)')


def extract_mentions(text: str) -> list[str]:
    """
    Parst @-Mentions aus text.
    Gibt Usernamen zurück (ohne '@'), in Reihenfolge des Auftretens, dedupliziert.
    '@' allein (ohne nachfolgenden [A-Za-z0-9_]) wird ignoriert.
    """
    matches = PATTERN.findall(text)
    return list(dict.fromkeys(matches))


class MentionIndex:
    """Bidirektionaler Index: msg_id ↔ erwähnte User."""

    def __init__(self) -> None:
        self._user_to_msgs: dict[str, list[int]] = {}
        self._msg_to_users: dict[int, list[str]] = {}

    def add(self, msg_id: int, text: str) -> None:
        mentions = extract_mentions(text)
        self._msg_to_users[msg_id] = mentions
        for user in mentions:
            if user not in self._user_to_msgs:
                self._user_to_msgs[user] = []
            if msg_id not in self._user_to_msgs[user]:
                self._user_to_msgs[user].append(msg_id)

    def mentions_of(self, user: str) -> list[int]:
        return self._user_to_msgs.get(user, [])

    def mentioned_users(self, msg_id: int) -> list[str]:
        return self._msg_to_users.get(msg_id, [])