from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from techradar.db.models import Chunk, Flashcard, LibraryChapter, LibraryDoc
from techradar.practice.chapter_cards import (
    make_chapter_cards,
    mark_chapter_read,
    render_chapter_list,
)
from tests.fakes import FakeCompleter


def cards_json(cards: list[dict]) -> str:
    return json.dumps({"cards": cards})


def card(
    quote: str = "CRR is 4%",
    chunk_id: int = 1,
    front: str = "What is CRR rate?",
    back: str = "The CRR rate is 4% today",
) -> dict:
    return {
        "front": front,
        "back": back,
        "quote": quote,
        "chunk_id": chunk_id,
    }


def ch(
    ordinal: int,
    read: bool = False,
    id: int = 10,
    title: str = "Banking System",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        ordinal=ordinal,
        title=title,
        read=read,
        read_at=datetime.now(UTC) if read else None,
    )


@pytest.mark.asyncio
async def test_card_without_exact_quote_dropped():
    chunk = SimpleNamespace(id=1, text="The Cash Reserve Ratio is 4% set by RBI.", flagged=False)
    fc = FakeCompleter([cards_json([card(quote="CRR is 9%", chunk_id=chunk.id)])])
    assert await make_chapter_cards(fc, [chunk]) == []


@pytest.mark.asyncio
async def test_flagged_chunks_never_sent():
    flagged_chunk = SimpleNamespace(id=1, text="MALICIOUS INJECTION CONTENT", flagged=True)
    chunk = SimpleNamespace(id=2, text="The Cash Reserve Ratio is 4% set by RBI.", flagged=False)
    fc = FakeCompleter([cards_json([])])
    await make_chapter_cards(fc, [flagged_chunk, chunk])
    assert len(fc.calls) == 1
    assert flagged_chunk.text not in fc.calls[0]["messages"][1]["content"]
    assert chunk.text in fc.calls[0]["messages"][1]["content"]


def test_chapter_list_marks_read_ones():
    doc = SimpleNamespace(title="Indian Economy")
    ch2_id = 20
    text, kb = render_chapter_list(doc, [ch(1, read=True), ch(2, read=False, id=ch2_id)])
    assert "Indian Economy · 2 chapters" in text
    assert kb[0][0].text.startswith("✓ 01.")
    assert kb[1][0].data == f"read:{ch2_id}"


@pytest.mark.asyncio
async def test_make_chapter_cards_success():
    chunk = SimpleNamespace(id=1, text="The Cash Reserve Ratio is 4% set by RBI.", flagged=False)
    valid_card = card(
        quote="Cash Reserve Ratio is 4%",
        chunk_id=1,
        front="What is the Cash Reserve Ratio?",
        back="The Cash Reserve Ratio is 4% by RBI",
    )
    fc = FakeCompleter([cards_json([valid_card])])
    res = await make_chapter_cards(fc, [chunk])
    assert len(res) == 1
    assert res[0].front == "What is the Cash Reserve Ratio?"
    assert res[0].quote == "Cash Reserve Ratio is 4%"


@pytest.mark.db
@pytest.mark.asyncio
async def test_mark_read_twice_creates_cards_once(session):
    now = datetime.now(UTC)
    # Check or create ready chapter in DB
    doc = LibraryDoc(
        sha256="e" * 64,
        title="Indian Economy Primer",
        kind="pdf",
        origin="library",
        original_path="economy/primer.pdf",
        size_bytes=1000,
        status="ready",
        trust="my_own",
    )
    session.add(doc)
    await session.flush()

    ready_chapter = LibraryChapter(
        doc_id=doc.id,
        ordinal=1,
        title="Monetary Policy",
        text_path="economy/ch01.txt",
    )
    session.add(ready_chapter)
    await session.flush()

    chunk = Chunk(
        doc_path="economy/primer.md",
        doc_kind="pdf",
        title="Monetary Policy",
        ordinal=1,
        text="The Cash Reserve Ratio is 4% set by RBI.",
        lang="en",
        content_hash="dummyhash123",
        doc_id=doc.id,
        chapter_id=ready_chapter.id,
    )
    session.add(chunk)
    await session.flush()

    good_card_data = card(
        quote="Cash Reserve Ratio is 4%",
        chunk_id=chunk.id,
        front="What is the Cash Reserve Ratio?",
        back="The Cash Reserve Ratio is 4% by RBI",
    )
    fc = FakeCompleter([cards_json([good_card_data] * 12)])
    assert await mark_chapter_read(session, fc, ready_chapter.id, now) == "created"
    assert await mark_chapter_read(session, fc, ready_chapter.id, now) == "already_read"

    count_res = await session.execute(
        select(func.count(Flashcard.id)).where(Flashcard.source_id == ready_chapter.id)
    )
    assert count_res.scalar() == 1


# --- Legacy tests preserved ---


@pytest.mark.db
async def test_chapter_without_indexed_chunks_is_not_ready(session):
    doc = LibraryDoc(
        sha256="f" * 64,
        title="Empty",
        kind="pdf",
        origin="library",
        original_path="e.pdf",
        size_bytes=1,
        status="ready",
        trust="my_own",
    )
    session.add(doc)
    await session.flush()
    chapter = LibraryChapter(doc_id=doc.id, ordinal=1, title="Unindexed", text_path="e/ch01.txt")
    session.add(chapter)
    await session.flush()
    fc = FakeCompleter([])
    assert await mark_chapter_read(session, fc, chapter.id, datetime.now(UTC)) == "not_ready"
    assert fc.calls == []
    await session.refresh(chapter)
    assert chapter.read_at is None  # a later tap still works


async def test_cards_come_back_in_chapter_order_and_capped():
    chunks = [
        SimpleNamespace(id=1, text="Alpha beta gamma delta epsilon fact one.", flagged=False),
        SimpleNamespace(id=2, text="Zeta eta theta iota kappa fact two.", flagged=False),
    ]
    c2 = card(
        quote="Zeta eta theta iota kappa",
        chunk_id=2,
        front="What is fact two here?",
        back="Zeta eta theta iota kappa fact",
    )
    c1 = card(
        quote="Alpha beta gamma delta epsilon",
        chunk_id=1,
        front="What is fact one here?",
        back="Alpha beta gamma delta epsilon fact",
    )
    res = await make_chapter_cards(FakeCompleter([cards_json([c2, c1])]), chunks)
    assert [c.chunk_id for c in res] == [1, 2]
