"""Unit tests for safe note writer and markdown rendering."""

from datetime import UTC, date, datetime
from pathlib import PurePosixPath

import pytest
import yaml

from techradar.pipeline.writer import (
    StoryFact,
    StoryNote,
    StorySource,
    md_escape,
    note_rel_path,
    render_story,
    slugify,
    write_note,
)
from techradar.schemas.pipeline import ExamTag, FourQuestions, Section

NOTE = StoryNote(
    cluster_id=1,
    title="RBI Policy Update",
    published=date(2026, 11, 8),
    section=Section.ECONOMY,
    exam_tags=[ExamTag.BANK],
    summary="RBI kept interest rates steady.",
    four_questions=FourQuestions(
        what_happened="RBI kept rates steady.",
        why="Inflation under control.",
        what_changes="Borrowing costs remain constant.",
        how_it_affects_me="Loan EMIs will not change.",
    ),
    facts=[
        StoryFact(
            statement="Repo rate unchanged at 5.5%.",
            status="verified",
            source_count=2,
        ),
        StoryFact(
            statement="Growth forecast is 7.2%.",
            status="unverified",
            source_count=1,
        ),
    ],
    sources=[
        StorySource(
            url="https://rbi.org.in/press/1",
            domain="rbi.org.in",
            fetched_at=datetime(2026, 11, 8, 10, 0, tzinfo=UTC),
        ),
    ],
    verified_headline=True,
)


def test_slugify_is_safe():
    assert slugify("../../etc/passwd") == "etc-passwd"
    assert slugify("भारत") == "note"


def test_note_rel_path_handles_collisions():
    p = note_rel_path(date(2026, 11, 8), "RBI holds rate", {"wiki/news/2026/11/rbi-holds-rate.md"})
    assert str(p) == "wiki/news/2026/11/rbi-holds-rate-2.md"


def test_md_escape_neutralises_image_and_link():
    out = md_escape("![x](https://evil.example/?d=1) <script>")
    assert "![" not in out and "](" not in out and "<script>" not in out


def test_render_story_has_provenance_and_status():
    md = render_story(NOTE)
    fm = yaml.safe_load(md.split("---")[1])
    assert fm["sources"] == [s.url for s in NOTE.sources]
    assert fm["generated"] is True
    assert "- ✅ verified · " in md
    assert "## How it affects me" in md


def test_write_note_rejects_traversal(tmp_path):
    for rel in ["../x.md", "/etc/x.md", "wiki/../../x.md"]:
        with pytest.raises(ValueError):
            write_note(tmp_path, PurePosixPath(rel), "x")


def test_write_note_refuses_symlinked_dir(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    vault = tmp_path / "v"
    vault.mkdir()
    (vault / "wiki").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        write_note(vault, PurePosixPath("wiki/a.md"), "x")


def test_write_note_atomic(tmp_path):
    p = write_note(tmp_path, PurePosixPath("wiki/news/2026/11/a.md"), "hello")
    assert p.read_text() == "hello" and not list(p.parent.glob("*.tmp"))
