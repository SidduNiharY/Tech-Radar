from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import Flashcard
from techradar.practice.flashcards import (
    CardRow,
    due_cards,
    new_card_state,
    render_card_back,
    review_card,
    run_cards,
)
from techradar.practice.fsrs import State
from techradar.settings import Settings

NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)


def test_good_schedules_later_than_again() -> None:
    s, _ = new_card_state(NOW)
    _, due_again = review_card(s, 1, NOW)
    _, due_good = review_card(s, 3, NOW)
    assert due_good > due_again


def test_new_card_state_initial_values() -> None:
    state, due = new_card_state(NOW)
    assert due == NOW
    assert state.get("reps") == 0
    assert state.get("lapses") == 0
    assert state.get("state") == State.NEW


def test_review_card_ratings_intervals() -> None:
    s, _ = new_card_state(NOW)
    _, due_again = review_card(s, 1, NOW)
    _, due_hard = review_card(s, 2, NOW)
    _, due_good = review_card(s, 3, NOW)
    _, due_easy = review_card(s, 4, NOW)

    assert due_again < due_hard < due_good <= due_easy


def test_render_card_back_with_doc_source() -> None:
    card = CardRow(
        id=101,
        front="What is virtual memory?",
        back="An abstraction mapping virtual addresses to physical pages.",
        source_kind="chapter",
        due=NOW,
        is_new=False,
        doc_path="textbooks/operating_systems.pdf",
        page=42,
    )
    text, buttons = render_card_back(card)
    assert "An abstraction mapping virtual addresses to physical pages." in text
    assert "Source: operating_systems, p. 42" in text
    # Row 0: ratings
    assert [b.text for b in buttons[0]] == ["Again", "Hard", "Good", "Easy"]
    assert [b.data for b in buttons[0]] == [
        f"rate:{card.id}:1",
        f"rate:{card.id}:2",
        f"rate:{card.id}:3",
        f"rate:{card.id}:4",
    ]
    # Row 1: show source
    assert buttons[1][0].text == "Show source"
    assert buttons[1][0].data == f"src:{card.id}"


def test_render_card_back_with_video_timestamp() -> None:
    card = CardRow(
        id=102,
        front="Eigenvalues definition?",
        back="Av = lambda v for non-zero eigenvector v.",
        source_kind="lecture",
        due=NOW,
        is_new=True,
        doc_path="lectures/mit_1806_lecture_21.mp4",
        ts_start=135,  # 2 min 15 sec
    )
    text, buttons = render_card_back(card)
    assert "Source: mit_1806_lecture_21, 02:15" in text
    assert buttons[1][0].text == "Show source"
    assert buttons[1][0].data == f"src:{card.id}"


def test_render_card_back_without_source() -> None:
    card = CardRow(
        id=103,
        front="Custom front",
        back="Custom back",
        source_kind="manual",
        due=NOW,
        is_new=True,
    )
    text, buttons = render_card_back(card)
    assert "Source:" not in text
    assert len(buttons) == 1
    assert [b.text for b in buttons[0]] == ["Again", "Hard", "Good", "Easy"]


# --- Unit Tests with FakeAsyncSession ---


class FakeFlashcardSession:
    """In-memory session fake for flashcard operations."""

    def __init__(self, cards: list[Flashcard] | None = None) -> None:
        self.cards: list[Flashcard] = list(cards or [])
        self.added: list[Any] = []
        self.flushed = False

    async def get(self, entity: type, ident: Any) -> Any:
        for c in self.cards:
            if c.id == ident:
                return c
        return None

    async def execute(self, stmt: Any) -> Any:
        class FakeResult:
            def __init__(self, items: list[Any]) -> None:
                self._items = items

            def scalars(self) -> FakeResult:
                return self

            def all(self) -> list[Any]:
                return list(self._items)

        stmt_str = str(stmt).lower()
        active = [c for c in self.cards if not c.retired]

        if "first_shown_at is not null" in stmt_str:
            reviews = [c for c in active if c.first_shown_at is not None]
            reviews.sort(key=lambda c: c.due)
            return FakeResult(reviews[:40])
        elif "first_shown_at is null" in stmt_str:
            new_cards = [c for c in active if c.first_shown_at is None]
            new_cards.sort(key=lambda c: (c.due, c.id))
            return FakeResult(new_cards[:10])

        return FakeResult(active)

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        if isinstance(obj, Flashcard):
            self.cards.append(obj)

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_due_cards_unit_filtering() -> None:
    # 20 review cards and 15 new cards
    cards: list[Flashcard] = []
    for i in range(20):
        cards.append(
            Flashcard(
                id=i + 1,
                front=f"Review front {i}",
                back=f"Review back {i}",
                source_kind="chapter",
                due=NOW - timedelta(days=1),
                first_shown_at=NOW - timedelta(days=2),
                retired=False,
            )
        )
    for i in range(15):
        cards.append(
            Flashcard(
                id=100 + i,
                front=f"New front {i}",
                back=f"New back {i}",
                source_kind="mcq",
                due=NOW - timedelta(hours=2),
                first_shown_at=None,
                retired=False,
            )
        )
    # 5 retired cards
    for i in range(5):
        cards.append(
            Flashcard(
                id=200 + i,
                front=f"Retired front {i}",
                back=f"Retired back {i}",
                source_kind="fact",
                due=NOW - timedelta(days=1),
                first_shown_at=NOW - timedelta(days=2),
                retired=True,
            )
        )

    session = FakeFlashcardSession(cards=cards)
    due = await due_cards(session, NOW, new_limit=10, review_limit=40)

    reviews = [c for c in due if not c.is_new]
    new_ones = [c for c in due if c.is_new]
    assert len(reviews) == 20
    assert len(new_ones) == 10
    assert all(c.id < 200 for c in due)


@pytest.mark.asyncio
async def test_run_cards_unit() -> None:
    card = Flashcard(
        id=55,
        front="What is Amdahl's Law?",
        back="Speedup is limited by the serial part of the program.",
        source_kind="chapter",
        due=NOW - timedelta(days=1),
        first_shown_at=None,
        retired=False,
    )
    session = FakeFlashcardSession(cards=[card])
    res = await run_cards(session, now=NOW, owner_chat_id=999, new_limit=10, review_limit=40)
    assert res.cards_sent == 1
    assert res.card_ids == [55]
    assert card.first_shown_at == NOW
    assert len(session.added) >= 1


# --- Database Integration Tests (@pytest.mark.db) ---


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def session(db_settings: Settings) -> AsyncGenerator[AsyncSession]:
    engine = make_engine("app", db_settings)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.fixture
def cards_150_due_30_new(session: AsyncSession) -> list[Flashcard]:
    cards = []
    # 150 review cards
    for i in range(150):
        cards.append(
            Flashcard(
                front=f"Review card {i}",
                back=f"Back {i}",
                source_kind="chapter",
                due=NOW - timedelta(days=1),
                first_shown_at=NOW - timedelta(days=3),
                retired=False,
            )
        )
    # 30 new cards
    for i in range(30):
        cards.append(
            Flashcard(
                front=f"New card {i}",
                back=f"Back {i}",
                source_kind="mcq",
                due=NOW - timedelta(hours=1),
                first_shown_at=None,
                retired=False,
            )
        )
    return cards


@pytest.fixture
def retired_card() -> Flashcard:
    return Flashcard(
        front="Old superseded fact",
        back="Superseded explanation",
        source_kind="fact",
        due=NOW - timedelta(days=1),
        first_shown_at=NOW - timedelta(days=2),
        retired=True,
    )


@pytest.mark.db
async def test_daily_limits_cap_new_and_reviews(
    session: AsyncSession,
    cards_150_due_30_new: list[Flashcard],
) -> None:
    for c in cards_150_due_30_new:
        session.add(c)
    await session.flush()

    cards = await due_cards(session, NOW, new_limit=10, review_limit=40)
    assert len([c for c in cards if c.is_new]) == 10
    assert len([c for c in cards if not c.is_new]) == 40


@pytest.mark.db
async def test_retired_cards_never_due(
    session: AsyncSession,
    retired_card: Flashcard,
) -> None:
    session.add(retired_card)
    await session.flush()

    cards = await due_cards(session, NOW, new_limit=10, review_limit=40)
    assert retired_card.id not in {c.id for c in cards}
