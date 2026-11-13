from __future__ import annotations

from pathlib import Path

from techradar.library.chapters import (
    ChapterSpec,
    assemble_chapter_text,
    detect_chapters,
    write_chapter_text,
)
from techradar.parser.pdf import OutlineEntry


def _t(chs):
    return [(c.title, c.page_start, c.page_end) for c in chs]


def test_detect_chapters_prefers_outline():
    out = [
        OutlineEntry(title="Money", page=1, level=1),
        OutlineEntry(title="Banks", page=30, level=1),
    ]
    heads = [(5, 1, "Ignored")]
    chs = detect_chapters(60, out, heads)
    assert _t(chs) == [("Money", 1, 29), ("Banks", 30, 60)]
    assert [c.ordinal for c in chs] == [1, 2]


def test_detect_chapters_ignores_deeper_outline_levels():
    out = [
        OutlineEntry(title="A", page=1, level=1),
        OutlineEntry(title="A.1", page=5, level=2),
        OutlineEntry(title="B", page=20, level=1),
    ]
    assert _t(detect_chapters(40, out, [])) == [("A", 1, 19), ("B", 20, 40)]


def test_single_level1_outline_entry_is_not_enough():
    out = [OutlineEntry(title="Only", page=1, level=1)]
    assert [c.title for c in detect_chapters(30, out, [])] == ["Pages 1–25", "Pages 26–30"]


def test_outline_pages_clamped_and_deduped():
    out = [
        OutlineEntry(title="X", page=0, level=1),
        OutlineEntry(title="Y", page=10, level=1),
        OutlineEntry(title="Z", page=10, level=1),
        OutlineEntry(title="Beyond", page=99, level=1),
    ]
    assert _t(detect_chapters(30, out, [])) == [("X", 1, 9), ("Y", 10, 30)]


def test_detect_chapters_uses_headings_second():
    heads = [(1, 1, "One"), (4, 2, "sub"), (12, 1, "Two")]
    assert _t(detect_chapters(30, [], heads)) == [("One", 1, 11), ("Two", 12, 30)]


def test_detect_chapters_falls_back_to_page_ranges():
    chs = detect_chapters(60, [], [])
    assert [c.title for c in chs] == ["Pages 1–25", "Pages 26–50", "Pages 51–60"]
    assert _t(chs)[0][1:] == (1, 25)


def test_detect_chapters_empty_document():
    assert detect_chapters(0, [], []) == []


def test_failed_part_noted_in_chapter():
    text = assemble_chapter_text(
        {1: "<!-- page 1 -->\nA"},
        ChapterSpec(ordinal=1, title="T", page_start=1, page_end=50),
        failed_pages=range(26, 51),
    )
    assert "> Pages 26–50 couldn't be read." in text
    assert "<!-- page 1 -->\nA" in text


def test_assemble_keeps_page_markers_in_order_and_notes_gap_in_place():
    parts = {
        1: "<!-- page 1 -->\nA\n\n<!-- page 2 -->\nB",
        26: "<!-- page 26 -->\nC",
    }
    ch = ChapterSpec(ordinal=1, title="T", page_start=2, page_end=26)
    text = assemble_chapter_text(parts, ch, failed_pages=[3, 4, 5, 7])
    assert "<!-- page 1 -->" not in text
    assert text.index("<!-- page 2 -->") < text.index("> Pages 3–5 couldn't be read.")
    assert text.index("> Pages 3–5 couldn't be read.") < text.index("> Page 7 couldn't be read.")
    assert text.index("> Page 7 couldn't be read.") < text.index("<!-- page 26 -->")


def test_write_chapter_text(tmp_path: Path):
    p = write_chapter_text(tmp_path, 7, 3, "hello")
    assert p == tmp_path / "text" / "7" / "03.md"
    assert p.read_text(encoding="utf-8") == "hello"
    assert p.stat().st_mode & 0o777 == 0o640
