"""Glossary, timelines and chains on the database (server only)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import DeepDive, GlossaryTerm, Item, Note, RawItem, Source
from techradar.db.models import Timeline as TimelineRow
from techradar.night.chains import CHAIN_START, run_chains
from techradar.night.glossary import entity_counts, run_glossary
from techradar.night.timelines import cluster_rows, run_timelines
from tests.fakes import FakeCompleter
from tests.night.hits import make_deps, make_hit, patch_retrieve

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 7, 21, 30, tzinfo=UTC)


async def _story(
    session: AsyncSession, key: int, entities: list[str], *, days_ago: int = 1, flags=None
) -> None:
    src = Source(
        name=f"wp-{key}",
        url=f"https://wp{key}.example/f.xml",
        host=f"wp{key}.example",
        section="economy",
        trust_tier="news",
    )
    session.add(src)
    await session.flush()
    raw = RawItem(
        source_id=src.id,
        url=f"https://wp{key}.example/s",
        url_hash=f"{key + 7000:064d}",
        kind="page",
        fetched_at=NOW - timedelta(days=days_ago),
    )
    session.add(raw)
    await session.flush()
    session.add(
        Item(
            raw_item_id=raw.id,
            title=f"Story {key}",
            url=raw.url,
            domain=f"wp{key}.example",
            lang="en",
            content_hash=f"{key + 7000:064x}",
            cluster_id=key,
            status="written",
            flags=flags or [],
            reader_json={"entities": entities},
        )
    )
    session.add(
        Note(
            cluster_id=key,
            vault_path=f"wiki/news/2026/11/wp-{key}.md",
            kind="news",
            title=f"Story {key}",
            content_hash=f"{key:064x}",
        )
    )
    await session.flush()


async def test_entity_counts_skip_old_items(session: AsyncSession) -> None:
    await _story(session, 8101, ["Repo rate", "RBI"])
    await _story(session, 8102, ["Repo rate"])
    await _story(session, 8103, ["Repo rate"], days_ago=90)
    counts = await entity_counts(session, now=NOW)
    assert counts["Repo rate"] == 2 and counts["RBI"] == 1


async def test_timelines_written_for_busy_entities_and_recorded(
    session: AsyncSession, tmp_path: Path
) -> None:
    for k in (8201, 8202, 8203):
        await _story(session, k, ["Zeta Bank"])
    await _story(session, 8204, ["Rare Co"])
    assert {r.cluster_id for r in await cluster_rows(session, tz="Asia/Kolkata")} >= {8201}
    result = await run_timelines(session, tz="Asia/Kolkata", vault_root=tmp_path)
    assert "Zeta Bank" in result.written and "Rare Co" not in result.written
    page = (tmp_path / "timelines" / "zeta-bank.md").read_text(encoding="utf-8")
    assert page.count("[[wiki/news/2026/11/wp-") == 3
    row = await session.get(TimelineRow, "zeta bank")
    assert row is not None and row.vault_path == "timelines/zeta-bank.md"


async def test_glossary_writes_missing_terms_only(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for k in (8301, 8302, 8303):
        await _story(session, k, ["Zeta Rate"])
    session.add(GlossaryTerm(term="Other Term", vault_path="glossary/other-term.md"))
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    reply = json.dumps(
        {
            "term": "Zeta Rate",
            "definition": "A rate [C1].",
            "example": "It moved.",
            "citations": ["C1"],
        }
    )
    deps = make_deps(FakeCompleter([reply]))
    result = await run_glossary(session, now=NOW, deps=deps, vault_root=tmp_path)
    assert "Zeta Rate" in result.written
    assert (tmp_path / "glossary" / "zeta-rate.md").exists()
    assert await session.get(GlossaryTerm, "Zeta Rate") is not None
    again = await run_glossary(session, now=NOW, deps=deps, vault_root=tmp_path)
    assert "Zeta Rate" not in again.written  # already has an entry


async def test_chain_added_once_to_a_recent_deep_dive(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = tmp_path / "deep_dives" / "2026-W45-x.md"
    page.parent.mkdir()
    page.write_text("# X\n\nmy text\n", encoding="utf-8")
    session.add(DeepDive(week="2026-W45", topic="oil", vault_path="deep_dives/2026-W45-x.md"))
    await session.flush()
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    reply = json.dumps({"steps": ["Oil up", "Inflation up", "Rates held"], "citations": ["C1"]})
    deps = make_deps(FakeCompleter([reply]))
    now = datetime.now(UTC)
    result = await run_chains(session, now=now, deps=deps, vault_root=tmp_path)
    assert result.added == ["deep_dives/2026-W45-x.md"]
    text = page.read_text(encoding="utf-8")
    assert "my text" in text and CHAIN_START in text and "```mermaid" in text
    again = await run_chains(session, now=now, deps=deps, vault_root=tmp_path)
    assert again.added == [] and len(deps.completer.calls) == 1
    assert (await session.execute(select(DeepDive))).first() is not None
