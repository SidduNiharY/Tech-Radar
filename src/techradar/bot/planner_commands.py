"""Phase 5 bot handlers: /study, /stop, /skill and the check-in buttons.

Called from `bot/main.py` and `bot/callbacks.py` only after the owner check (SEC-26).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from techradar.planner.checkin import record_checkin
from techradar.planner.sessions import local_date, stop_reply, study_reply
from techradar.vault.frontmatter import set_skill_status

logger = logging.getLogger(__name__)

NOT_AVAILABLE = "Not available yet."
SKILL_USAGE = "Use /skill <name> <status>, with status not_started, learning or built."
CHECKIN_FIELDS = ("sleep", "energy", "mood")


def split_skill_arg(arg: str) -> tuple[str, str] | None:
    """`FastAPI learning` -> ("FastAPI", "learning"); the status is the last word."""
    parts = arg.strip().rsplit(maxsplit=1)
    if len(parts) != 2 or not parts[0].strip():
        return None
    name, status = parts
    return name.strip()[:80], status.lower()


async def handle_planner_command(
    action: str, arg: str, bot_data: Any, now: datetime | None = None
) -> str:
    """Return the reply for `study`, `stop` or `skill`."""
    now = now or datetime.now(UTC)
    if action == "skill":
        parsed = split_skill_arg(arg)
        if parsed is None:
            return SKILL_USAGE
        vault_root = bot_data.get("vault_root")
        if vault_root is None:
            return NOT_AVAILABLE
        return await set_skill_status(Path(vault_root), parsed[0], parsed[1], local_date(now))

    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        return NOT_AVAILABLE
    async with session_factory() as session:
        if action == "study":
            reply = await study_reply(session, arg, now)
        else:
            reply = await stop_reply(session, now)
        await session.commit()
    return reply


async def handle_checkin_tap(
    field: str, value: int, bot_data: Any, now: datetime | None = None
) -> str:
    """Record one check-in tap for today (India day) and return the answer."""
    now = now or datetime.now(UTC)
    session_factory = bot_data.get("session_factory")
    if session_factory is None or field not in CHECKIN_FIELDS:
        return NOT_AVAILABLE
    try:
        async with session_factory() as session:
            await record_checkin(session, local_date(now), field, value)  # type: ignore[arg-type]
            await session.commit()
    except ValueError:
        return "Invalid request."
    return "Noted."
