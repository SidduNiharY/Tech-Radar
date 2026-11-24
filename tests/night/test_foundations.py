from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from techradar.night.foundations import fill_foundation, replace_generated_block
from tests.fakes import FakeCompleter
from tests.night.hits import make_deps, make_hit, patch_retrieve

TODAY = date(2026, 11, 22)


def test_replace_generated_block_keeps_my_text() -> None:
    md = "# GDP\nmy notes\n<!-- generated:start -->\nold\n<!-- generated:end -->\nmore notes\n"
    out = replace_generated_block(md, "new")
    assert "my notes" in out
    assert "more notes" in out
    assert "old" not in out
    assert "new" in out


def test_without_markers_the_block_goes_after_the_first_heading() -> None:
    out = replace_generated_block("# GDP\nmy notes\n", "new")
    assert out.splitlines()[:5] == [
        "# GDP",
        "",
        "<!-- generated:start -->",
        "new",
        "<!-- generated:end -->",
    ]
    assert "my notes" in out
    assert replace_generated_block(out, "newer").count("<!-- generated:start -->") == 1


def _page(tmp_path: Path) -> Path:
    page = tmp_path / "foundations" / "economy" / "gdp.md"
    page.parent.mkdir(parents=True)
    page.write_text("# GDP\nMy own notes.\n", encoding="utf-8")
    return page


def _reply(explained: str = "GDP is output [C1].", citations: list[str] | None = None) -> str:
    return json.dumps(
        {
            "explained": explained,
            "key_points": ["Output of a country"],
            "citations": citations or ["C1"],
        }
    )


async def test_not_enough_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _page(tmp_path)
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2)])
    deps = make_deps(FakeCompleter([]))
    res = await fill_foundation("foundations/economy/gdp.md", deps, tmp_path, today=TODAY)
    assert res == "not_enough_sources"


async def test_flagged_and_unverified_news_do_not_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _page(tmp_path)
    hits = [make_hit(1), make_hit(2, flagged=True), make_hit(3, kind="news", verified=False)]
    patch_retrieve(monkeypatch, hits)
    deps = make_deps(FakeCompleter([]))
    res = await fill_foundation("foundations/economy/gdp.md", deps, tmp_path, today=TODAY)
    assert res == "not_enough_sources" and deps.completer.calls == []


async def test_bad_citation_needs_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = _page(tmp_path)
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    bad = _reply("GDP is output [C9].", ["C9"])
    deps = make_deps(FakeCompleter([bad]))
    res = await fill_foundation("foundations/economy/gdp.md", deps, tmp_path, today=TODAY)
    assert res == "needs_review"
    assert page.read_text(encoding="utf-8") == "# GDP\nMy own notes.\n"


async def test_filled_page_keeps_my_text_and_records_the_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _page(tmp_path)
    patch_retrieve(monkeypatch, [make_hit(1), make_hit(2), make_hit(3)])
    deps = make_deps(FakeCompleter([_reply()]))
    res = await fill_foundation("foundations/economy/gdp.md", deps, tmp_path, today=TODAY)
    assert res == "updated"
    text = page.read_text(encoding="utf-8")
    assert "My own notes." in text and "GDP is output [C1]." in text
    assert "filled: '2026-11-22'" in text or "filled: 2026-11-22" in text
    assert "- [C1] Source 1" in text


async def test_a_path_outside_the_vault_is_refused(tmp_path: Path) -> None:
    deps = make_deps(FakeCompleter([]))
    assert await fill_foundation("../x.md", deps, tmp_path, today=TODAY) == "not_enough_sources"
