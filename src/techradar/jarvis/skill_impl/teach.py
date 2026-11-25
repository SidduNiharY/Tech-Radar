"""Teach skill, start side: say the one-evening plan and build the brief from my own sources."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Fact, LibraryChapter
from techradar.jarvis.skill_impl.result import SkillReply
from techradar.voice_live.briefs import SessionBrief

FACTS_MAX = 20
PASSAGE_MAX = 1500


def _read_summary(vault_root: Path | None, rel: str | None) -> str | None:
    """A chapter summary note from the vault, only when it lies inside the vault."""
    if vault_root is None or not rel:
        return None
    root = vault_root.resolve()
    path = root / rel
    if path.is_symlink():
        return None
    try:
        path = path.resolve()
        path.relative_to(root)
        return path.read_text(encoding="utf-8")[:PASSAGE_MAX]
    except OSError, ValueError:
        return None


async def run(
    session: AsyncSession,
    now: datetime,
    *,
    topic: str,
    minutes: int = 90,
    vault_root: Path | None = None,
) -> SkillReply:
    like = f"%{topic}%"
    facts = (
        (
            await session.execute(
                select(Fact.statement)
                .where(
                    Fact.status == "verified",
                    Fact.superseded_by.is_(None),
                    or_(Fact.subject.ilike(like), Fact.statement.ilike(like)),
                )
                .order_by(Fact.updated_at.desc())
                .limit(FACTS_MAX)
            )
        )
        .scalars()
        .all()
    )
    summary_rel = (
        await session.execute(
            select(LibraryChapter.summary_path)
            .where(LibraryChapter.title.ilike(like), LibraryChapter.summary_path.is_not(None))
            .order_by(LibraryChapter.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    brief = SessionBrief(
        mode="explain",
        facts=list(facts),
        passage=_read_summary(vault_root, summary_rel),
    )
    say = (
        f"Here is a {minutes}-minute plan for {topic}. First I map the topic, then I explain it, "
        "then you explain it back to me, then we practise, and last I summarise it into notes "
        "and cards. Start whenever you are ready."
    )
    return SkillReply(say=say, practice="explain", brief=brief)
