"""A politics story in the real pipeline (server only): opinions appear only for 3+ domains."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from techradar.pipeline.process import collect_results, process_new_items
from techradar.settings import Settings
from tests.fakes import FakeCompleter
from tests.pipeline.conftest import (
    READER_OUTPUT,
    RELATED,
    SUPPORTED,
    _make_deps,
    _page,
    _write_result,
)

pytestmark = pytest.mark.db

POLITICS_OUTPUT = {**READER_OUTPUT, "section": "politics"}
VIEW = {
    "facts": [{"statement": "The bill passed.", "subject": "bill", "value": None}],
    "supporters_say": [
        {"text": "It cuts red tape.", "domain": "thehindu.com"},
        {"text": "Planted by a stranger.", "domain": "evil.example"},
    ],
    "critics_say": [{"text": "It hurts states.", "domain": "indianexpress.com"}],
}


async def _run(db_settings: Settings, tmp_path: Path, domains: list[str], replies: list[str]):
    deps = await _make_deps(db_settings, tmp_path, FakeCompleter(replies), RELATED)
    for n, domain in enumerate(domains, 1):
        _write_result(deps.clean_dir, _page(n, domain))
    await collect_results(deps)
    await process_new_items(deps)
    return deps, next((deps.vault_root / "wiki/news").rglob("*.md")).read_text()


async def test_three_domains_get_attributed_opinions(
    pipeline_db: None, db_settings: Settings, tmp_path: Path
) -> None:
    per_item = [json.dumps(POLITICS_OUTPUT), json.dumps(SUPPORTED)]
    _, md = await _run(
        db_settings,
        tmp_path,
        ["thehindu.com", "indianexpress.com", "ndtv.com"],
        per_item * 3 + [json.dumps(VIEW)],
    )
    assert "## What supporters say (opinion)" in md and "- It cuts red tape. (thehindu.com)" in md
    assert "## What critics say (opinion)" in md and "It hurts states" in md
    assert "Planted by a stranger" not in md


async def test_two_domains_get_no_opinion_sections(
    pipeline_db: None, db_settings: Settings, tmp_path: Path
) -> None:
    per_item = [json.dumps(POLITICS_OUTPUT), json.dumps(SUPPORTED)]
    _, md = await _run(db_settings, tmp_path, ["thehindu.com", "indianexpress.com"], per_item * 2)
    assert "(opinion)" not in md
