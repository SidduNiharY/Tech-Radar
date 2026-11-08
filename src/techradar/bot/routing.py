"""Message routing for owner-only Telegram bot."""

from collections.abc import Set

from techradar.bot.auth import is_allowed


def route_update(
    chat_id: int | None,
    text: str | None,
    owner_id: int,
    group_ids: Set[int] = frozenset(),
) -> str:
    """Route an incoming Telegram message.

    Returns:
        "status" for /status commands from authorized chats
        "start" for /start commands from authorized chats
        "ignore" for unauthorized chats or unknown/empty messages
    """
    if not is_allowed(chat_id, owner_id, group_ids):
        return "ignore"

    if not text or not text.strip():
        return "ignore"

    first_word = text.strip().split()[0]
    cmd = first_word.split("@")[0].lower()

    if cmd == "/status":
        return "status"
    if cmd == "/start":
        return "start"

    return "ignore"
