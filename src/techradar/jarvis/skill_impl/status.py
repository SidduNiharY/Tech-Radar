"""Status skill: the same health text as the bot's /status; it only reads."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.bot.render import render_status
from techradar.jarvis.skill_impl.result import SkillReply
from techradar.ops.status import check_disk_live, check_ollama_live, collect_status


async def run(
    session: AsyncSession,
    now: datetime,
    *,
    check_ollama: Callable[[], Awaitable[list[str] | None]] = check_ollama_live,
    check_disk: Callable[[], float] = check_disk_live,
) -> SkillReply:
    async def check_db() -> bool:
        try:
            return (await session.execute(text("SELECT 1"))).scalar() == 1
        except Exception:
            return False

    status = await collect_status(check_db, check_ollama, check_disk)
    return SkillReply(say=render_status(status).replace("\n", ". "))
