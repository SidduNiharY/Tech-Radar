"""Message routing for owner-only Telegram bot (Phase 2b Task 6).

SEC: SEC-26.
"""

from __future__ import annotations

from collections.abc import Set
from typing import Literal, NamedTuple

from techradar.bot.auth import is_allowed

Action = Literal[
    "start",
    "status",
    "ask",
    "quiz",
    "cards",
    "grammar",
    "inbox",
    "plan",
    "take",
    "quarantine",
    "ignore",
]


class Routed(NamedTuple):
    """Result of update routing containing the target action and optional argument."""

    action: Action
    arg: str = ""


def route_update(
    chat_id: int | None,
    text: str | None,
    owner_id: int,
    group_ids: Set[int] = frozenset(),
    reply_to_message_id: int | None = None,
    active_briefing_message_ids: Set[int] = frozenset(),
    *,
    is_briefing_reply: bool = False,
    briefing_message_ids: Set[int] | None = None,
) -> Routed:
    """Route an incoming Telegram message.

    Returns:
        Routed("status") for /status commands from authorized chats
        Routed("start") for /start commands from authorized chats
        Routed("ask", question) for /ask commands from authorized chats
        Routed("quiz") for /quiz commands from authorized chats
        Routed("cards") for /cards commands from authorized chats
        Routed("grammar") for /grammar commands from authorized chats
        Routed("inbox") for /inbox commands from authorized chats
        Routed("plan") for /plan commands from authorized chats
        Routed("quarantine") for /quarantine from the owner's own chat only
        Routed("take", reply_text) for replies to active briefing messages
        Routed("ignore") for unauthorized chats or unknown/empty messages
    """
    if not is_allowed(chat_id, owner_id, group_ids):
        return Routed("ignore")

    if not text or not text.strip():
        return Routed("ignore")

    cleaned = text.strip()

    valid_briefings = set(active_briefing_message_ids)
    if briefing_message_ids:
        valid_briefings.update(briefing_message_ids)

    if is_briefing_reply or (
        reply_to_message_id is not None and reply_to_message_id in valid_briefings
    ):
        return Routed("take", cleaned)

    words = cleaned.split()
    cmd = words[0].split("@")[0].lower()

    if cmd == "/start":
        return Routed("start")
    if cmd == "/status":
        return Routed("status")
    if cmd == "/ask":
        arg = cleaned[len(words[0]) :].strip()
        return Routed("ask", arg)
    if cmd == "/quiz":
        return Routed("quiz")
    if cmd == "/cards":
        return Routed("cards")
    if cmd == "/grammar":
        return Routed("grammar")
    if cmd == "/inbox":
        return Routed("inbox")
    if cmd == "/plan":
        return Routed("plan")
    if cmd == "/quarantine":
        # Releasing held files is the owner's alone, never a study group's (SEC-14).
        return Routed("quarantine") if chat_id == owner_id else Routed("ignore")

    return Routed("ignore")
