"""Authorization logic for Telegram bot interactions."""


def is_allowed(
    chat_id: int | None,
    owner_id: int,
    group_ids: frozenset[int] = frozenset(),
) -> bool:
    """Return True if chat_id matches owner_id or is an allowed group; False otherwise."""
    if chat_id is None:
        return False
    return chat_id == owner_id or chat_id in group_ids
