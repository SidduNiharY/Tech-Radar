"""Unit tests for tracking and analyzing user edits to generated notes."""

from __future__ import annotations

from typing import Any

from techradar.db.models import Edit
from techradar.feedback.edits import (
    compare_edit,
    diff_ratio,
    generate_critique_signals,
    load_snapshot,
    record_edit,
    save_snapshot,
)


def test_compare_edit_finds_removed_section_and_shortening():
    """Verify section removal and character length change detection."""
    gen = "# T\n## Background\nlong text here\n## Why\nreason"
    edited = "# T\n## Why\nreason"
    m = compare_edit(gen, edited)
    assert m.sections_removed == ["Background"]
    assert m.length_change < 0


def test_compare_edit_detects_words_replaced():
    """Verify replaced words count computation."""
    gen = "The rapid brown fox leaps over lazy dogs"
    edited = "The quick brown fox jumps over sleepy dogs"
    m = compare_edit(gen, edited)
    assert m.words_replaced >= 2


def test_snapshot_written_only_for_generated(tmp_path):
    """Snapshot is only saved when is_generated is True."""
    doc_path = "vault/notes/2026-11-15-ai-trends.md"
    content = "---\ngenerated: true\n---\n# AI Trends\nContent here"

    # Not generated
    p1 = save_snapshot(doc_path, content, is_generated=False, base_dir=tmp_path)
    assert p1 is None
    assert load_snapshot(doc_path, base_dir=tmp_path) is None

    # Generated
    p2 = save_snapshot(doc_path, content, is_generated=True, base_dir=tmp_path)
    assert p2 is not None
    assert p2.exists()
    assert load_snapshot(doc_path, base_dir=tmp_path) == content


def test_diff_ratio_and_critique_signals():
    """Verify similarity ratio and critique signal generation."""
    gen = "# Title\n## Intro\nSome intro text.\n## Details\nLots of detailed explanation."
    edited = "# Title\n## Intro\nBrief intro."

    ratio = diff_ratio(gen, edited)
    assert 0.0 < ratio < 1.0

    m = compare_edit(gen, edited)
    signals = generate_critique_signals(m, original_length=len(gen))
    assert "remove_section:Details" in signals
    assert "shorten" in signals


class FakeEditSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for idx, row in enumerate(self.added, 1):
            if getattr(row, "id", None) is None:
                row.id = idx


async def test_record_edit():
    """Verify record_edit saves edit record with diff hashes."""
    session = FakeEditSession()
    gen = "## Section 1\nContent A"
    edited = "## Section 1\nContent B edited"
    edit_row = await record_edit(session, doc_path="test.md", before=gen, after=edited)

    assert isinstance(edit_row, Edit)
    assert edit_row.doc_path == "test.md"
    assert len(session.added) == 1
    assert session.added[0].words_replaced >= 1
