"""Coach skill: start a live practice mode with its brief. It only reads."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from techradar.jarvis.skill_impl.result import SkillReply
from techradar.voice_live.briefs import Mode, build_brief


async def run(
    session: AsyncSession, now: datetime, *, mode: Mode, vault_root: Path | None = None
) -> SkillReply:
    brief = await build_brief(mode, session, vault_root, now.date())
    label = mode.replace("_", " ")
    return SkillReply(say=f"Starting {label} practice.", practice=mode, brief=brief)
