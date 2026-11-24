"""Deep dive on the database (server only): topic choice, once a week, the owner message."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import DeepDive, Item, Note, Outbox, RawItem, Source
from techradar.night.deep_dive import cluster_stats, recent_topics, run_deep_dive
from tests.fakes import FakeCompleter
from tests.night.hits import make_deps, make_hit, patch_retrieve
from tests.night.test_deep_dive import dd_json

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 7, 21, 30, tzinfo=UTC)  # Sunday 03:00 IST, ISO week 2026-W45
OWNER = 4242


async def _story(
    session: AsyncSession,
    *,
    key: int,
    cluster: int,
    domain: str,
    title: str,
    age_days: float = 1,
    flags: list[str] | None = None,
) -> None:
    src = Source(
        name=f"dd-test-{key}",
        url=f"https://{domain}/dd-{key}.xml",
        host=domain,
        section="economy",
        trust_tier="news",
    )
    session.add(src)
    await session.flush()
    raw = RawItem(
        source_id=src.id,
        url=f"https://{domain}/dd-story-{key}",
        url_hash=f"{key + 9000:064d}",
        kind="page",
        fetched_at=NOW - timedelta(days=age_days),
    )
    session.add(raw)
    await session.flush()
    session.add(
        Item(
            raw_item_id=raw.id,
            title=title,
            url=raw.url,
            domain=domain,
            lang="en",
            content_hash=f"{key + 9000:064x}",
            cluster_id=cluster,
            status="written",
            flags=flags or [],
        )
    )
    if not (await session.execute(select(Note).where(Note.cluster_id == cluster))).first():
        session.add(
            Note(
                cluster_id=cluster,
                vault_path=f"wiki/news/2026/11/dd-{cluster}.md",
                kind="news",
                title=title,
                content_hash=f"{cluster:064x}",
            )
        )
    await session.flush()


async def _three_domain_cluster(session: AsyncSession, cluster: int, title: str) -> None:
    for i, domain in enumerate(("a.example", "b.example", "c.example")):
        await _story(session, key=cluster * 10 + i, cluster=cluster, domain=domain, title=title)


async def test_cluster_stats_count_domains_and_skip_old_and_flagged(session: AsyncSession) -> None:
    await _three_domain_cluster(session, 9101, "Repo rate held")
    await _story(
        session, key=9190, cluster=9102, domain="a.example", title="Old story", age_days=20
    )
    await _story(
        session,
        key=9191,
        cluster=9103,
        domain="a.example",
        title="Flagged story",
        flags=["gateway_flagged"],
    )
    stats = {s.topic: s for s in await cluster_stats(session, now=NOW)}
    assert stats["Repo rate held"].domains == 3 and stats["Repo rate held"].items == 3
    assert "Old story" not in stats and "Flagged story" not in stats


async def test_deep_dive_written_once_per_week(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _three_domain_cluster(session, 9201, "Repo rate held")
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    deps = make_deps(FakeCompleter([dd_json()]), tz="Asia/Kolkata")

    first = await run_deep_dive(
        session, now=NOW, deps=deps, vault_root=tmp_path, owner_chat_id=OWNER
    )
    assert first.status == "written" and first.topic == "Repo rate held"
    assert (tmp_path / str(first.path)).exists()

    rows = (await session.execute(select(DeepDive).where(DeepDive.week == "2026-W45"))).scalars()
    assert [r.topic for r in rows] == ["Repo rate held"]
    out = (await session.execute(select(Outbox).where(Outbox.purpose == "deep_dive"))).scalar_one()
    assert out.chat_id == OWNER
    assert out.text == "📚 This week's deep dive: RBI Monetary Policy (in your vault)"

    again = await run_deep_dive(
        session, now=NOW, deps=deps, vault_root=tmp_path, owner_chat_id=OWNER
    )
    assert again.status == "already_done"
    assert len(deps.completer.calls) == 1  # no second model call


async def test_recent_topics_are_skipped_the_next_week(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _three_domain_cluster(session, 9301, "Repo rate held")
    session.add(DeepDive(week="2026-W44", topic="Repo rate held", vault_path="deep_dives/x.md"))
    await session.flush()
    assert "Repo rate held" in await recent_topics(session, now=NOW)
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    deps = make_deps(FakeCompleter([]), tz="Asia/Kolkata")
    result = await run_deep_dive(
        session, now=NOW, deps=deps, vault_root=tmp_path, owner_chat_id=OWNER
    )
    assert result.status == "no_topic"


async def test_needs_review_writes_nothing(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _three_domain_cluster(session, 9401, "Repo rate held")
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    deps = make_deps(FakeCompleter([dd_json(section_without_citation=True)] * 2), tz="Asia/Kolkata")
    result = await run_deep_dive(
        session, now=NOW, deps=deps, vault_root=tmp_path, owner_chat_id=OWNER
    )
    assert result.status == "needs_review"
    assert not (tmp_path / "deep_dives").exists()
    assert (
        await session.execute(select(DeepDive).where(DeepDive.week == "2026-W45"))
    ).first() is None
