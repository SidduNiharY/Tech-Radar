from __future__ import annotations

from pathlib import Path

from techradar.night.foundations import (
    fill_foundation,
    replace_generated_block,
)
from tests.fakes import FakeCompleter


class FakeHit:
    def __init__(self, title: str, text: str, verified: bool = True) -> None:
        self.title = title
        self.text = text
        self.verified = verified


class FakeRagDeps:
    def __init__(self, hits: list[FakeHit], completer: FakeCompleter) -> None:
        self.hits = hits
        self.completer = completer

    async def retrieve(self, query: str) -> list[FakeHit]:
        return self.hits


def test_replace_generated_block_keeps_my_text() -> None:
    md = "# GDP\nmy notes\n<!-- generated:start -->\nold\n<!-- generated:end -->\nmore notes\n"
    out = replace_generated_block(md, "new")
    assert "my notes" in out
    assert "more notes" in out
    assert "old" not in out
    assert "new" in out


async def test_not_enough_sources(tmp_path: Path) -> None:
    page = tmp_path / "foundations" / "economy" / "gdp.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("# GDP\nInitial notes.\n", encoding="utf-8")

    deps = FakeRagDeps(
        hits=[FakeHit("H1", "Text 1"), FakeHit("H2", "Text 2")],
        completer=FakeCompleter([]),
    )
    res = await fill_foundation("foundations/economy/gdp.md", deps, tmp_path)
    assert res == "not_enough_sources"


async def test_bad_citation_needs_review(tmp_path: Path) -> None:
    page = tmp_path / "foundations" / "economy" / "gdp.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("# GDP\nInitial notes.\n", encoding="utf-8")

    deps = FakeRagDeps(
        hits=[
            FakeHit("H1", "Text 1"),
            FakeHit("H2", "Text 2"),
            FakeHit("H3", "Text 3"),
        ],
        completer=FakeCompleter(
            ['{"explained": "GDP is output [C9].", "key_points": [], "citations": ["C9"]}']
        ),
    )
    res = await fill_foundation("foundations/economy/gdp.md", deps, tmp_path)
    assert res == "needs_review"
