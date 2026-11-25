"""Library skill, read side: each ready book and how many chapters are read."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryChapter, LibraryDoc
from techradar.jarvis.skill_impl.result import SkillReply

BOOKS_MAX = 5


async def run(session: AsyncSession, now: datetime, *, book: str | None = None) -> SkillReply:
    """`library status`. Marking a chapter read is a write: it comes with a ticket."""
    stmt = (
        select(
            LibraryDoc.title,
            func.count(LibraryChapter.id),
            func.count(LibraryChapter.read_at),
        )
        .select_from(LibraryDoc)
        .outerjoin(LibraryChapter, LibraryChapter.doc_id == LibraryDoc.id)
        .where(LibraryDoc.status == "ready")
        .group_by(LibraryDoc.id, LibraryDoc.title)
        .order_by(LibraryDoc.title)
    )
    if book:
        stmt = stmt.where(LibraryDoc.title.ilike(f"%{book}%"))
    rows = (await session.execute(stmt)).all()
    if not rows:
        if book:
            return SkillReply(say=f"I can't find a book called {book} in your library.")
        return SkillReply(say="Your library has no books yet.")
    parts = [
        f"{title}: {read} of {total} chapters read." for title, total, read in rows[:BOOKS_MAX]
    ]
    more = len(rows) - BOOKS_MAX
    tail = f" And {more} more." if more > 0 else ""
    return SkillReply(say=" ".join(parts) + tail)
