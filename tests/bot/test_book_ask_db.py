"""db tests: a reply to a Ready message finds its book; the chapters list (Phase 2c Task 8).

Everything is rolled back after each test.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.bot.book_ask import chapters_listing, ready_doc_for_reply
from techradar.db.engine import make_engine
from techradar.db.models import LibraryChapter, LibraryDoc, Outbox
from techradar.settings import Settings

pytestmark = pytest.mark.db

OWNER = 1234


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    settings = Settings(
        telegram_owner_chat_id=OWNER,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )
    engine = make_engine("app", settings)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _doc(session: AsyncSession, status: str = "ready") -> LibraryDoc:
    sha = os.urandom(32).hex()
    doc = LibraryDoc(
        sha256=sha,
        title="Indian Economy",
        kind="pdf",
        origin="library",
        original_path=f"originals/{sha}.pdf",
        size_bytes=10,
        status=status,
        trust="my_own",
    )
    session.add(doc)
    await session.flush()
    return doc


async def _ready_msg(
    session: AsyncSession, doc: LibraryDoc, *, message_id: int | None, chat: int = OWNER
) -> Outbox:
    row = Outbox(
        chat_id=chat,
        kind="text",
        purpose="library_ready",
        text="Ready",
        ref_id=doc.id,
        sent_message_id=message_id,
        sent_at=datetime.now(UTC) if message_id is not None else None,
    )
    session.add(row)
    await session.flush()
    return row


async def test_reply_finds_the_ready_book(session: AsyncSession) -> None:
    doc = await _doc(session)
    await _ready_msg(session, doc, message_id=981_234_567)
    assert await ready_doc_for_reply(session, OWNER, 981_234_567) == doc.id


async def test_other_chat_unsent_other_purpose_or_unready_book_never_match(
    session: AsyncSession,
) -> None:
    doc = await _doc(session)
    await _ready_msg(session, doc, message_id=981_234_568, chat=OWNER + 1)
    assert await ready_doc_for_reply(session, OWNER, 981_234_568) is None
    await _ready_msg(session, doc, message_id=None)
    other = await _ready_msg(session, doc, message_id=981_234_569)
    other.purpose = "answer"
    unready = await _doc(session, status="quarantined")
    await _ready_msg(session, unready, message_id=981_234_570)
    await session.flush()
    assert await ready_doc_for_reply(session, OWNER, 981_234_569) is None
    assert await ready_doc_for_reply(session, OWNER, 981_234_570) is None


async def test_chapters_listing_orders_by_ordinal(session: AsyncSession) -> None:
    doc = await _doc(session)
    for ordinal, title, ps, pe in ((2, "Banking", 21, 40), (1, "Money", 1, 20)):
        session.add(
            LibraryChapter(
                doc_id=doc.id,
                ordinal=ordinal,
                title=title,
                page_start=ps,
                page_end=pe,
                text_path=f"{doc.id}/{ordinal}.txt",
            )
        )
    await session.flush()
    text = await chapters_listing(session, doc.id)
    assert text is not None
    lines = text.splitlines()
    assert lines[:3] == [
        "Indian Economy · 2 chapters",
        "1. Money (pp. 1-20)",
        "2. Banking (pp. 21-40)",
    ]


async def test_chapters_listing_of_an_unready_book_is_none(session: AsyncSession) -> None:
    doc = await _doc(session, status="quarantined")
    assert await chapters_listing(session, doc.id) is None
