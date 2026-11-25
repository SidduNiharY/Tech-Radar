"""Ask skill: find the book the owner means; the answer itself comes from the RAG pipeline.

Skills hold no models. The router passes in `answer`, a small async function that runs the
grounded answer within the fast budget (8 s) and returns text, or `None` when the answer was not
ready in time or needs review. `None` makes this a slow reply: the night model answers later.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import LibraryDoc
from techradar.jarvis.skill_impl.result import SkillReply

Answerer = Callable[[str, int | None], Awaitable[str | None]]


async def find_book(session: AsyncSession, title: str) -> LibraryDoc | None:
    """The ready book whose title best matches: an exact (case-blind) title first, then the
    shortest title that contains the words."""
    rows = (
        (
            await session.execute(
                select(LibraryDoc)
                .where(LibraryDoc.status == "ready", LibraryDoc.title.ilike(f"%{title}%"))
                .order_by(LibraryDoc.id)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    exact = [r for r in rows if r.title.lower() == title.lower()]
    return exact[0] if exact else min(rows, key=lambda r: len(r.title))


async def run(
    session: AsyncSession,
    now: datetime,
    *,
    question: str,
    book: str | None = None,
    answer: Answerer | None = None,
) -> SkillReply:
    doc_id: int | None = None
    if book:
        doc = await find_book(session, book)
        if doc is None:
            return SkillReply(say=f"I can't find a book called {book} in your library.")
        doc_id = doc.id
    text = await answer(question, doc_id) if answer is not None else None
    if text is None:
        return SkillReply(say="Let me think about that.", slow=True, doc_id=doc_id)
    return SkillReply(say=text, doc_id=doc_id)
