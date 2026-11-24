"""Economy series on the database (server only)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Fact, FactSource, Item, RawItem, Source
from techradar.world.econ import (
    OFFICIAL_DOMAINS,
    collect_official,
    read_series,
    record_manual,
    render_econ,
    store_points,
)

pytestmark = pytest.mark.db


async def _verified_fact(
    session: AsyncSession,
    n: int,
    subject: str,
    value: str,
    domain: str,
    *,
    status: str = "verified",
) -> Fact:
    src = Source(
        name=f"econ-{n}", url=f"https://{domain}/e{n}.xml", host=domain, section="economy",
        trust_tier="official",
    )  # fmt: skip
    session.add(src)
    await session.flush()
    raw = RawItem(
        source_id=src.id, url=f"https://{domain}/e{n}", url_hash=f"{n + 6000:064d}", kind="page"
    )
    session.add(raw)
    await session.flush()
    item = Item(
        raw_item_id=raw.id, title="t", url=raw.url, domain=domain, lang="en",
        content_hash=f"{n + 6000:064x}",
    )  # fmt: skip
    session.add(item)
    await session.flush()
    fact = Fact(
        fact_key=f"econ-fact-{n}", statement=f"{subject} is {value}", subject=subject, value=value,
        section="economy", status=status, source_count=1, as_of=date(2026, 10, 14),
    )  # fmt: skip
    session.add(fact)
    await session.flush()
    session.add(FactSource(fact_id=fact.id, item_id=item.id, domain=domain, supported=True))
    await session.flush()
    return fact


async def test_manual_value_is_stored_once_per_month(session: AsyncSession) -> None:
    await record_manual(session, "usd_inr", date(2026, 11, 1), 84.2)
    await record_manual(session, "usd_inr", date(2026, 11, 1), 84.3)  # a correction
    await record_manual(session, "usd_inr", date(2026, 10, 1), 83.9)
    assert await read_series(session, "usd_inr") == [
        (date(2026, 11, 1), pytest.approx(84.3)),
        (date(2026, 10, 1), pytest.approx(83.9)),
    ]


async def test_official_facts_become_points_and_others_do_not(session: AsyncSession) -> None:
    await _verified_fact(session, 1, "repo rate", "5.5%", "rbi.org.in")
    await _verified_fact(session, 2, "repo rate", "1%", "fake-news.example")
    await _verified_fact(session, 3, "CPI inflation", "4.6%", "mospi.gov.in", status="unverified")
    assert await collect_official(session, OFFICIAL_DOMAINS) >= 1
    assert await read_series(session, "repo_rate") == [(date(2026, 10, 1), pytest.approx(5.5))]
    assert await read_series(session, "cpi_inflation") == []
    assert await collect_official(session, OFFICIAL_DOMAINS) >= 1  # a repeat changes nothing
    assert len(await read_series(session, "repo_rate")) == 1


async def test_manual_beats_official_for_the_same_month(session: AsyncSession) -> None:
    await store_points(session, "usd_inr", [(date(2026, 11, 1), 1.0)], source_kind="official_fact")
    await record_manual(session, "usd_inr", date(2026, 11, 1), 2.0)
    assert await read_series(session, "usd_inr") == [(date(2026, 11, 1), pytest.approx(2.0))]


async def test_render_econ_reads_stored_series(session: AsyncSession) -> None:
    await record_manual(session, "usd_inr", date(2026, 10, 1), 84.2)
    await record_manual(session, "usd_inr", date(2026, 11, 1), 83.9)
    await record_manual(session, "gold_10g", date(2026, 11, 1), 78450)
    text = await render_econ(session)
    assert "USD/INR fell from 84.2 to 83.9 (−0.3)." in text
    assert "Gold (10 g) is ₹78,450." in text
