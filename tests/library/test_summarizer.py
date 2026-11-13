from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from techradar.library.models import Chapter
from techradar.library.summarizer import (
    ChapterSummary,
    check_key_idea_citations,
    render_chapter_vault_note,
)


def test_check_key_idea_citations() -> None:
    assert check_key_idea_citations(["Concept one [C1]", "Concept two [C2]"])
    assert not check_key_idea_citations(["Concept without citation"])
    assert check_key_idea_citations([])


def test_render_chapter_vault_note_success(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    chapter = Chapter(
        title="Chapter 1: The Preamble",
        ordinal=1,
        start_page=1,
        end_page=15,
        slug="chapter-01-the-preamble",
    )

    summary = ChapterSummary(
        chapter_id="c1",
        title="The Preamble to the Constitution",
        summary_markdown=(
            "The Preamble secures justice, liberty, equality and fraternity for all citizens."
        ),
        key_ideas=[
            "Sovereign, socialist, secular, democratic republic framework [C1].",
            "Justice defined in social, economic, and political dimensions [C2].",
        ],
        citations=["C1", "C2"],
    )

    out_path = render_chapter_vault_note(
        chapter=chapter,
        summary=summary,
        book_slug="ncert-polity-11",
        vault_dir=vault_dir,
    )

    expected_path = vault_dir / "Library" / "ncert-polity-11" / "chapter-01-the-preamble.md"
    assert out_path == expected_path
    assert out_path.exists()

    content = out_path.read_text(encoding="utf-8")
    assert content.startswith("---\n")

    # Verify frontmatter
    parts = content.split("---", 2)
    assert len(parts) >= 3
    fm = yaml.safe_load(parts[1])
    assert fm["title"] == "The Preamble to the Constitution"
    assert fm["book_slug"] == "ncert-polity-11"
    assert fm["chapter_ordinal"] == 1
    assert "created_at" in fm
    assert fm["status"] == "ready"

    # Verify body
    body = parts[2]
    assert "## Summary" in body
    assert "The Preamble secures justice" in body
    assert "## Key Ideas" in body
    assert "- Sovereign, socialist, secular, democratic republic framework [C1]." in body
    assert "- Justice defined in social, economic, and political dimensions [C2]." in body
    assert "## Citations" in body
    assert "- [C1]" in body
    assert "- [C2]" in body


def test_render_chapter_vault_note_rejects_uncited_key_idea(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    chapter = Chapter(
        title="Chapter 1",
        ordinal=1,
        start_page=1,
        end_page=10,
        slug="ch-1",
    )

    summary = ChapterSummary(
        chapter_id="c1",
        title="Chapter 1",
        summary_markdown="Summary text",
        key_ideas=["Idea without citation marker"],
        citations=[],
    )

    with pytest.raises(ValueError, match="citation markers"):
        render_chapter_vault_note(chapter, summary, "book-1", vault_dir)


def test_render_chapter_vault_note_path_traversal_rejected(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    chapter = Chapter(
        title="Traitor",
        ordinal=1,
        start_page=1,
        end_page=5,
        slug="../../etc/passwd",
    )

    summary = ChapterSummary(
        chapter_id="c1",
        title="Traitor",
        summary_markdown="Dangerous text",
        key_ideas=["Idea [C1]"],
    )

    with pytest.raises(ValueError, match="Path traversal"):
        render_chapter_vault_note(chapter, summary, "safe-book", vault_dir)

    # Path traversal via book_slug
    chapter_safe = Chapter(
        title="Normal",
        ordinal=1,
        start_page=1,
        end_page=5,
        slug="normal-chapter",
    )
    with pytest.raises(ValueError, match="Path traversal"):
        render_chapter_vault_note(chapter_safe, summary, "../../../escape", vault_dir)


def test_render_chapter_vault_note_symlink_rejected(tmp_path: Path) -> None:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    target_dir = tmp_path / "outside"
    target_dir.mkdir()

    library_dir = vault_dir / "Library"
    library_dir.mkdir()
    symlink_dir = library_dir / "evil-link"
    symlink_dir.symlink_to(target_dir, target_is_directory=True)

    chapter = Chapter(
        title="Chapter 1",
        ordinal=1,
        start_page=1,
        end_page=5,
        slug="ch1",
    )
    summary = ChapterSummary(
        chapter_id="c1",
        title="Symlink attack",
        summary_markdown="Attack",
        key_ideas=["Point [C1]"],
    )

    with pytest.raises(ValueError, match="symlink"):
        render_chapter_vault_note(chapter, summary, "evil-link", vault_dir)
