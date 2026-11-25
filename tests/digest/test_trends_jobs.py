"""Trend counts, the "rising fast" message and the `since` filter (Phase 10 Task 7)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Chunk, Item, Outbox, RawItem, Source, TrendCount
from techradar.digest.trends import (
    Rising,
    count_day,
    extract_terms,
    render_rising,
    run_trends,
    why_question,
    why_since,
)
from techradar.rag.retrieve import RetrieveFilters, _apply_filters


def test_extract_terms_normalises_and_dedupes() -> None:
    reader = {"entities": ["Rust", " rust ", "PostgreSQL", "", 7, "x" * 200]}
    assert extract_terms(reader) == ["rust", "postgresql"]
    assert extract_terms(None) == []
    assert extract_terms({"entities": "nope"}) == []


def test_render_rising_card() -> None:
    r = Rising(term="rust", today=40, baseline=5.0, ratio=8.0)
    assert render_rising(r) == "🔥 Rising fast: Rust, 40 mentions today vs about 5/day usually."


def test_why_question_and_window() -> None:
    assert why_question("rust") == "Why is everyone talking about rust this week?"
    assert why_since(date(2026, 11, 25)) == date(2026, 11, 18)


def test_since_filter_is_in_the_query() -> None:
    from sqlalchemy import select as sa_select

    stmt = _apply_filters(sa_select(Chunk.id), RetrieveFilters(since=date(2026, 11, 18)), None)
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "indexed_at >=" in sql and "2026-11-18" in sql
    plain = _apply_filters(sa_select(Chunk.id), RetrieveFilters(), None)
    assert "indexed_at" not in str(plain)


pytestmark_db = pytest.mark.db


async def _processed_item(session: AsyncSession, n: int, entities: list[str], at: datetime) -> None:
    src = Source(
        name=f"trend-{n}",
        url=f"https://t{n}.example/f.xml",
        host=f"t{n}.example",
        section="tech",
        trust_tier="news",
    )
    session.add(src)
    await session.flush()
    raw = RawItem(
        source_id=src.id, url=f"https://t{n}.example/a", url_hash=f"{n + 9000:064d}", kind="page"
    )
    session.add(raw)
    await session.flush()
    session.add(
        Item(
            raw_item_id=raw.id,
            title="t",
            url=raw.url,
            domain=f"t{n}.example",
            lang="en",
            content_hash=f"{n + 9000:064d}",
            status="done",
            reader_json={"entities": entities},
            processed_at=at,
        )
    )
    await session.flush()


@pytestmark_db
async def test_count_day_counts_once_per_item_and_is_idempotent(session: AsyncSession) -> None:
    await session.execute(TrendCount.__table__.delete())
    day = date(2026, 11, 25)
    at = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)  # 11:30 IST
    await _processed_item(session, 1, ["Rust", "rust", "Go"], at)
    await _processed_item(session, 2, ["rust"], at)
    await count_day(session, day, "Asia/Kolkata")
    await count_day(session, day, "Asia/Kolkata")
    rows = {
        r.term: r.count
        for r in (await session.execute(select(TrendCount).where(TrendCount.day == day))).scalars()
    }
    assert rows["rust"] == 2 and rows["go"] == 1


@pytestmark_db
async def test_run_trends_alerts_on_spike_not_on_steady(session: AsyncSession) -> None:
    await session.execute(TrendCount.__table__.delete())
    await session.execute(Outbox.__table__.delete())
    today = date(2026, 11, 25)
    for i in range(1, 15):
        d = today - timedelta(days=i)
        session.add(TrendCount(day=d, term="rust", count=5))
        session.add(TrendCount(day=d, term="india", count=55))
    session.add(TrendCount(day=today, term="rust", count=40))
    session.add(TrendCount(day=today, term="india", count=60))
    await session.flush()
    sent = await run_trends(session, today, owner_chat_id=4242)
    assert sent == 1
    msgs = (await session.execute(select(Outbox).where(Outbox.purpose == "rising"))).scalars()
    texts = [m.text for m in msgs]
    assert len(texts) == 1 and "Rust, 40 mentions" in texts[0]
