"""Red-team prompt injection test suite (Task 13 / SEC-21)."""

import unicodedata
from pathlib import Path

import pytest
import yaml

from techradar.parser.html import html_to_doc
from techradar.pipeline.reader import build_reader_graph, read_item
from techradar.pipeline.verify import is_verified
from techradar.pipeline.writer import render_story
from tests.fakes import FakeCompleter
from tests.security.redteam_helpers import attacker_outputs, note_from

CASES_FILE = Path("security/redteam/expected.yaml")
CASES: dict[str, list[str]] = yaml.safe_load(CASES_FILE.read_text()) if CASES_FILE.exists() else {}


def _load_fixture_doc(name: str):
    path = Path(f"security/redteam/pages/{name}")
    assert path.exists(), f"Fixture {name} not found"
    doc = html_to_doc(path.read_bytes(), "https://fake-news.example/a", 100_000)
    assert doc is not None, f"Failed to extract clean doc from {name}"
    return doc


@pytest.mark.parametrize("name,expect", list(CASES.items()))
async def test_redteam_fixture_is_contained(name: str, expect: list[str]) -> None:
    doc = _load_fixture_doc(name)

    if "sanitized" in expect:
        assert not any(unicodedata.category(c) == "Cf" and c not in "‌‍" for c in doc.text)

    result = await read_item(build_reader_graph(FakeCompleter(attacker_outputs(name))), doc)
    if "needs_review" in expect:
        assert result.status == "needs_review"
    if "unverified" in expect:
        assert result.status == "ok" and not is_verified(
            {"fake-news.example"}, frozenset({"rbi.org.in"})
        )


def test_no_written_note_can_carry_an_attack() -> None:
    md = render_story(
        note_from(attacker_outputs("02_markdown_image_exfil.html")[0], allow_invalid=True)
    )
    assert "![" not in md and "](" not in md.split("## Sources")[0]
