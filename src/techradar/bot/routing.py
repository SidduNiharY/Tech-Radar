"""Message routing for owner-only Telegram bot (Phase 2b Task 6).

SEC: SEC-26.
"""

from __future__ import annotations

from collections.abc import Set
from typing import Literal, NamedTuple

from techradar.bot.auth import is_allowed
from techradar.bot.intake import is_paste, link_in

Action = Literal[
    "start",
    "status",
    "ask",
    "ask_book",
    "quiz",
    "cards",
    "grammar",
    "inbox",
    "plan",
    "take",
    "quarantine",
    "packs",
    # --- Phase 7 ---
    "predict",
    "prediction_reply",
    "econ",
    "ignore",
    # --- Phase 5 ---
    "study",
    "stop",
    "skill",
    "drill",  # Phase 8
    # --- Phase 6: English practice ---
    "polish",
    "story",
    "story_reply",
    "essay_reply",
    "reflection_reply",
    # --- Phase 3 Task 3: links and pasted text from the owner ---
    "link",
    "paste",
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
    *,
    ready_message_ids: Set[int] = frozenset(),
    reply_to_purpose: str | None = None,
    reply_to_ref: int | None = None,
    prediction_message_ids: Set[int] = frozenset(),
    story_open: bool = False,
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
        Routed("ask_book", text) for a plain-text reply (no command) from the owner's own chat
            to one of `ready_message_ids` (the caller looked the Ready messages up)
        Routed("take", text) for a plain reply from the owner's own chat to a sent briefing
            message: the caller looked up the target outbox row and passes its `purpose` and
            `ref_id` (the briefing id) as `reply_to_purpose` and `reply_to_ref`
        Routed("econ", arg) for /econ from the owner's own chat only (Phase 7)
        Routed("predict", arg) for /predict from the owner's own chat only (Phase 7)
        Routed("prediction_reply", text) for a plain-text reply from the owner's own chat to
            one of `prediction_message_ids` (the caller looked the reminders up)
        Routed("link", url) for owner text (own chat only) that is exactly one URL-like token,
            including schemes that are never fetched (javascript:, file:, ...), so they get a
            clear refusal; the worker checks it against the allowlist (Phase 3 Task 3)
        Routed("paste", text) for owner text (own chat only) of 200 characters or more with
            no URL in it (Phase 3 Task 3)
        Routed("polish" | "story", arg) for /polish and /story from the owner's own chat only
        Routed("essay_reply" | "reflection_reply", text) for a plain reply from the owner's
            own chat to the essay or reflection prompt; Routed("story_reply", text) for a plain
            message while a /story draft is open (Phase 6)

    Order: commands first, then replies to a message we sent and an open /story draft, and
    only then a bare link or a pasted text, so a long reply is never taken for a paste.
        Routed("ignore") for unauthorized chats or unknown/empty messages
    """
    if not is_allowed(chat_id, owner_id, group_ids):
        return Routed("ignore")

    if not text or not text.strip():
        return Routed("ignore")

    cleaned = text.strip()

    # --- Phase 7: predictions log (the owner's own chat only, never a study group) ---
    if (
        chat_id == owner_id
        and reply_to_message_id is not None
        and reply_to_message_id in prediction_message_ids
        and not cleaned.startswith("/")
    ):
        return Routed("prediction_reply", cleaned)

    words = cleaned.split()
    cmd = words[0].split("@")[0].lower()

    if cmd == "/start":
        return Routed("start")
    if cmd == "/status":
        return Routed("status")
    if cmd == "/ask":
        arg = cleaned[len(words[0]) :].strip()
        return Routed("ask", arg)
    if cmd in ("/quiz", "/cards", "/grammar", "/inbox"):
        # Their messages go to the owner's chat, and the review inbox shows the owner's own
        # items: never from a study group.
        return Routed(cmd[1:]) if chat_id == owner_id else Routed("ignore")  # type: ignore[arg-type]
    if cmd == "/plan":
        return Routed("plan")
    # --- Phase 8 ---
    if cmd == "/drill":
        # Timed drills are the owner's own practice, not a study group's.
        return Routed("drill") if chat_id == owner_id else Routed("ignore")
    # --- end Phase 8 ---
    if cmd == "/econ":  # --- Phase 7: the owner keeps the numbers ---
        if chat_id != owner_id:
            return Routed("ignore")
        return Routed("econ", cleaned[len(words[0]) :].strip())
    if cmd == "/predict":  # --- Phase 7 ---
        if chat_id != owner_id:
            return Routed("ignore")
        return Routed("predict", cleaned[len(words[0]) :].strip())
    # --- Phase 6: English practice is the owner's own, never a study group's (SEC-26) ---
    if cmd in ("/polish", "/story"):
        if chat_id != owner_id:
            return Routed("ignore")
        return Routed(cmd[1:], cleaned[len(words[0]) :].strip())  # type: ignore[arg-type]
    # --- end Phase 6 ---
    if cmd == "/quarantine":
        # Releasing held files is the owner's alone, never a study group's (SEC-14).
        return Routed("quarantine") if chat_id == owner_id else Routed("ignore")
    if cmd == "/packs":  # starter packs status: the owner's own chat only
        return Routed("packs") if chat_id == owner_id else Routed("ignore")

    # --- Phase 5 ---
    # The study tracker and the skill map are the owner's alone, never a study group's (SEC-26).
    if cmd in ("/study", "/stop", "/skill"):
        if chat_id != owner_id:
            return Routed("ignore")
        return Routed(cmd[1:], cleaned[len(words[0]) :].strip())  # type: ignore[arg-type]

    if (
        not cmd.startswith("/")
        and chat_id == owner_id
        and reply_to_purpose == "briefing"
        and reply_to_ref is not None
    ):
        # "My take": one line in reply to a briefing message. Owner's own chat only.
        return Routed("take", cleaned)

    # --- Phase 6: replies to the essay prompt and the reflection prompt; a plain message while
    # a /story draft is open. Owner's own chat only. ---
    if not cmd.startswith("/") and chat_id == owner_id:
        if reply_to_purpose == "essay" and reply_to_ref is not None:
            return Routed("essay_reply", cleaned)
        if reply_to_purpose == "reflection":
            return Routed("reflection_reply", cleaned)
    # --- end Phase 6 ---

    if (
        not cmd.startswith("/")
        and chat_id == owner_id
        and reply_to_message_id is not None
        and reply_to_message_id in ready_message_ids
    ):
        # Replying to a Ready message asks that book. Owner's own chat only: the Ready message
        # is sent nowhere else.
        return Routed("ask_book", cleaned)

    if not cmd.startswith("/") and chat_id == owner_id and story_open:  # --- Phase 6 ---
        return Routed("story_reply", cleaned)

    # --- Phase 3 Task 3: links and pasted text, the owner's own chat only (SEC-26). Last of
    # all: a command, a reply to a message we sent (briefing, essay, reflection, Ready,
    # prediction) or an open /story draft always wins, so a long reply is never taken for a
    # paste. ---
    if chat_id == owner_id and not cmd.startswith("/"):
        url = link_in(cleaned)
        if url is not None:
            return Routed("link", url)
        if is_paste(cleaned):
            return Routed("paste", cleaned)

    return Routed("ignore")
