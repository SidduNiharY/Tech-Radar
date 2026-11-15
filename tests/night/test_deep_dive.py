from __future__ import annotations

import json
from pathlib import Path

from techradar.night.deep_dive import (
    ClusterStat,
    DDSection,
    DeepDive,
    pick_topic,
    write_deep_dive,
)
from tests.fakes import FakeCompleter


class FakeHit:
    def __init__(self, title: str, text: str) -> None:
        self.title = title
        self.text = text


class FakeRagDeps:
    def __init__(self, hits: list[FakeHit], completer: FakeCompleter) -> None:
        self.hits = hits
        self.completer = completer

    async def retrieve(self, query: str, k_final: int = 10) -> list[FakeHit]:
        return self.hits


def test_pick_topic_prefers_domains_and_skips_recent() -> None:
    stats = [
        ClusterStat(topic="repo rate", domains=5, items=9),
        ClusterStat(topic="rust", domains=7, items=4),
    ]
    assert pick_topic(stats, recent_topics={"rust"}) == "repo rate"


async def test_every_section_must_cite(tmp_path: Path) -> None:
    hits = [
        FakeHit("H1", "Content 1"),
        FakeHit("H2", "Content 2"),
        FakeHit("H3", "Content 3"),
    ]
    # Deep dive JSON where section 2 has NO citation
    dd_bad = DeepDive(
        title="RBI Monetary Policy",
        sections=[
            DDSection(heading="Introduction", body="Intro text with [C1]."),
            DDSection(heading="Impact", body="Impact text without any citation."),
            DDSection(heading="Conclusion", body="Closing text with [C2]."),
        ],
        citations=["C1", "C2"],
    )
    deps = FakeRagDeps(
        hits=hits,
        completer=FakeCompleter([json.dumps(dd_bad.model_dump())] * 2),
    )
    res = await write_deep_dive("repo rate", deps, tmp_path, "2026-W45")
    assert res == "needs_review"


async def test_valid_deep_dive_written(tmp_path: Path) -> None:
    hits = [
        FakeHit("H1", "Content 1"),
        FakeHit("H2", "Content 2"),
        FakeHit("H3", "Content 3"),
    ]
    dd_good = DeepDive(
        title="RBI Monetary Policy",
        sections=[
            DDSection(heading="Introduction", body="Intro text with [C1]."),
            DDSection(heading="Impact", body="Impact text with [C2]."),
            DDSection(heading="Conclusion", body="Closing text with [C3]."),
        ],
        citations=["C1", "C2", "C3"],
    )
    deps = FakeRagDeps(
        hits=hits,
        completer=FakeCompleter([json.dumps(dd_good.model_dump())]),
    )
    res = await write_deep_dive("repo rate", deps, tmp_path, "2026-W45")
    assert res == "written"
    written_file = tmp_path / "deep_dives" / "2026-W45-rbi-monetary-policy.md"
    assert written_file.exists()
    assert "# RBI Monetary Policy" in written_file.read_text(encoding="utf-8")
