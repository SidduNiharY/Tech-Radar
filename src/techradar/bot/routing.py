"""Message routing for owner-only Telegram bot (Phase 2b Task 6).

SEC: SEC-26.
"""

from __future__ import annotations

from collections.abc import Set
from typing import Literal, NamedTuple

from techradar.bot.auth import is_allowed

Action = Literal["start", "status", "ask", "ignore"]


class Routed(NamedTuple):
    """Result of update routing containing the target action and optional argument."""

    action: Action
    arg: str = ""


def route_update(
    chat_id: int | None,
    text: str | None,
    owner_id: int,
    group_ids: Set[int] = frozenset(),
) -> Routed:
    """Route an incoming Telegram message.

    Returns:
        Routed("status") for /status commands from authorized chats
        Routed("start") for /start commands from authorized chats
        Routed("ask", question) for /ask commands from authorized chats
        Routed("ignore") for unauthorized chats or unknown/empty messages
    """
    if not is_allowed(chat_id, owner_id, group_ids):
        return Routed("ignore")

    if not text or not text.strip():
        return Routed("ignore")

    cleaned = text.strip()
    words = cleaned.split()
    cmd = words[0].split("@")[0].lower()

    if cmd == "/start":
        return Routed("start")
    if cmd == "/status":
        return Routed("status")
    if cmd == "/ask":
        arg = cleaned[len(words[0]) :].strip()
        return Routed("ask", arg)

    return Routed("ignore")
