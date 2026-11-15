from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from techradar.db.models import Chunk, Flashcard, LibraryChapter, LibraryDoc
from techradar.practice.chapter_cards import (
    ChapterCardsGenerator,
    make_chapter_cards,
    mark_chapter_read,
    render_chapter_list,
)
from techradar.practice.fsrs import Card, State
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
        source_id=0,
        slug="economy-test-doc",
        title="Indian Economy Primer",
        doc_path="economy/primer.md",
        kind="book",
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
        doc_kind="book",
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


def test_mark_read_twice_creates_cards_once_legacy():
    generator = ChapterCardsGenerator()
    slug = "neural-networks-intro"
    chunks = [
        "Neural networks are composed of layers of nodes. Each node performs a weighted sum.",
        "Activation functions introduce non-linearity into neural network models.",
        "Backpropagation uses gradient descent to optimize network weights.",
        "Loss functions quantify the difference between predictions and actual labels.",
    ]

    cards_first = generator.generate_cards(chapter_slug=slug, chunks=chunks)
    assert 10 <= len(cards_first) <= 20

    existing_card_keys = {card.card_key for card in cards_first}
    cards_second = generator.generate_cards(
        chapter_slug=slug,
        chunks=chunks,
        existing_card_keys=existing_card_keys,
    )
    assert len(cards_second) == 0


def test_chapter_cards_count_range():
    generator = ChapterCardsGenerator()
    slug = "compiler-design-gate"
    chunks = [
        "Lexical analysis produces tokens from raw source characters.",
        "Syntax analysis builds an abstract syntax tree using context-free grammars.",
        "Semantic analysis enforces type consistency and scope rules.",
        "Intermediate code generation produces three-address code representation.",
        "Code optimization improves runtime performance and reduces memory footprint.",
        "Target code generation translates intermediate representations into machine code.",
    ]

    cards = generator.generate_cards(chapter_slug=slug, chunks=chunks)
    assert 10 <= len(cards) <= 20

    for card_item in cards:
        assert isinstance(card_item, Card)
        assert card_item.state == State.NEW
        assert card_item.stability == 0.0
        assert card_item.difficulty == 0.0
        assert card_item.reps == 0
        assert card_item.lapses == 0


def test_flagged_chunks_excluded():
    generator = ChapterCardsGenerator()
    slug = "security-chapter"
    chunks = [
        "[FLAGGED] Malicious payload pretending to be a textbook chunk.",
        "Legitimate operating systems concept chunk on virtual memory and paging.",
    ]

    cards = generator.generate_cards(chapter_slug=slug, chunks=chunks)
    assert len(cards) >= 10
    for card_item in cards:
        assert "Malicious" not in card_item.front
        assert "Malicious" not in card_item.back


def test_empty_chunks_returns_empty():
    generator = ChapterCardsGenerator()
    assert generator.generate_cards("empty-chapter", []) == []
