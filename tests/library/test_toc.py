from __future__ import annotations

import pytest

from techradar.library.models import BookMeta, Chapter, LibraryPart
from techradar.library.toc import chunk_by_page_ranges, extract_outline_chapters


def test_chunk_by_page_ranges_100_pages() -> None:
    parts = chunk_by_page_ranges(100, part_size=25)
    assert parts == [(1, 25), (26, 50), (51, 75), (76, 100)]
    assert len(parts) == 4


def test_chunk_by_page_ranges_60_pages() -> None:
    parts = chunk_by_page_ranges(60, part_size=25)
    assert parts == [(1, 25), (26, 50), (51, 60)]
    assert len(parts) == 3


def test_chunk_by_page_ranges_default_part_size() -> None:
    parts = chunk_by_page_ranges(60)
    assert parts == [(1, 25), (26, 50), (51, 60)]


def test_chunk_by_page_ranges_edge_cases() -> None:
    assert chunk_by_page_ranges(0, 25) == []
    assert chunk_by_page_ranges(-5, 25) == []
    assert chunk_by_page_ranges(10, 25) == [(1, 10)]
    assert chunk_by_page_ranges(25, 25) == [(1, 25)]
    assert chunk_by_page_ranges(26, 25) == [(1, 25), (26, 26)]

    with pytest.raises(ValueError, match="part_size must be positive"):
        chunk_by_page_ranges(10, 0)
    with pytest.raises(ValueError, match="part_size must be positive"):
        chunk_by_page_ranges(10, -1)


def test_extract_outline_chapters_bounds_and_slugs() -> None:
    bookmarks = [
        {"title": "Money", "page": 1},
        {"title": "Banks", "page": 30},
    ]
    chapters = extract_outline_chapters(bookmarks, page_count=60)
    assert len(chapters) == 2

    ch1, ch2 = chapters
    assert ch1.title == "Money"
    assert ch1.ordinal == 1
    assert ch1.start_page == 1
    assert ch1.end_page == 29
    assert ch1.slug == "money"

    assert ch2.title == "Banks"
    assert ch2.ordinal == 2
    assert ch2.start_page == 30
    assert ch2.end_page == 60
    assert ch2.slug == "banks"


def test_extract_outline_chapters_multi_chapters() -> None:
    bookmarks = [
        {"title": "Introduction", "page": 1},
        {"title": "Chapter 1: The Foundations", "page": 15},
        {"title": "Chapter 2: Advanced Topics", "page": 45},
    ]
    chapters = extract_outline_chapters(bookmarks, page_count=100)
    assert len(chapters) == 3

    assert chapters[0].slug == "introduction"
    assert (chapters[0].start_page, chapters[0].end_page) == (1, 14)
    assert chapters[0].ordinal == 1

    assert chapters[1].slug == "chapter-1-the-foundations"
    assert (chapters[1].start_page, chapters[1].end_page) == (15, 44)
    assert chapters[1].ordinal == 2

    assert chapters[2].slug == "chapter-2-advanced-topics"
    assert (chapters[2].start_page, chapters[2].end_page) == (45, 100)
    assert chapters[2].ordinal == 3


def test_extract_outline_chapters_empty() -> None:
    assert extract_outline_chapters([], page_count=100) == []


def test_extract_outline_chapters_hierarchical_levels() -> None:
    bookmarks = [
        {"title": "Chapter 1", "page": 1, "level": 1},
        {"title": "Section 1.1", "page": 5, "level": 2},
        {"title": "Section 1.2", "page": 12, "level": 2},
        {"title": "Chapter 2", "page": 25, "level": 1},
        {"title": "Section 2.1", "page": 30, "level": 2},
    ]
    chapters = extract_outline_chapters(bookmarks, page_count=60)
    assert len(chapters) == 2
    assert chapters[0].title == "Chapter 1"
    assert (chapters[0].start_page, chapters[0].end_page) == (1, 24)
    assert chapters[1].title == "Chapter 2"
    assert (chapters[1].start_page, chapters[1].end_page) == (25, 60)


def test_extract_outline_chapters_alternate_keys() -> None:
    bookmarks = [
        {"name": "Part A", "start_page": 1},
        {"label": "Part B", "page_number": 20},
        {"text": "Part C", "page_index": 39},  # 0-based 39 -> 1-based 40
    ]
    chapters = extract_outline_chapters(bookmarks, page_count=60)
    assert len(chapters) == 3
    assert [c.title for c in chapters] == ["Part A", "Part B", "Part C"]
    assert [c.start_page for c in chapters] == [1, 20, 40]
    assert [c.end_page for c in chapters] == [19, 39, 60]


def test_extract_outline_chapters_explicit_end_page() -> None:
    bookmarks = [
        {"title": "Prologue", "start_page": 1, "end_page": 10},
        {"title": "Main Content", "start_page": 15, "end_page": 50},
    ]
    chapters = extract_outline_chapters(bookmarks, page_count=60)
    assert (chapters[0].start_page, chapters[0].end_page) == (1, 10)
    assert (chapters[1].start_page, chapters[1].end_page) == (15, 50)


def test_extract_outline_chapters_duplicate_titles_have_unique_slugs() -> None:
    bookmarks = [
        {"title": "Appendix", "page": 10},
        {"title": "Appendix", "page": 20},
    ]
    chapters = extract_outline_chapters(bookmarks, page_count=30)
    assert chapters[0].slug == "appendix"
    assert chapters[1].slug == "appendix-2"


def test_models_defaults_and_validation() -> None:
    ch = Chapter(
        title="Chapter 1",
        ordinal=1,
        start_page=1,
        end_page=25,
        slug="chapter-1",
    )
    assert ch.title == "Chapter 1"
    assert ch.ordinal == 1
    assert ch.start_page == 1
    assert ch.end_page == 25
    assert ch.slug == "chapter-1"

    meta = BookMeta(title="Principles of Economics")
    assert meta.title == "Principles of Economics"
    assert meta.author is None
    assert meta.doc_kind == "library"
    assert meta.exam_tags == []
    assert meta.page_count == 0
    assert meta.chapters == []

    meta_full = BookMeta(
        title="Macroeconomics",
        author="Mankiw",
        doc_kind="library",
        exam_tags=["gate", "bank"],
        page_count=350,
        chapters=[ch],
    )
    assert meta_full.author == "Mankiw"
    assert meta_full.exam_tags == ["gate", "bank"]
    assert meta_full.page_count == 350
    assert len(meta_full.chapters) == 1

    part = LibraryPart(
        book_slug="principles-of-economics",
        part_index=1,
        start_page=1,
        end_page=25,
    )
    assert part.book_slug == "principles-of-economics"
    assert part.part_index == 1
    assert part.start_page == 1
    assert part.end_page == 25
    assert part.status == "pending"
