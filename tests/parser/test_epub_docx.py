"""Phase 2c Task 3: EPUB and DOCX readers in the parser sandbox."""

import hashlib
import zipfile
from pathlib import Path

import pytest

from techradar.parser.docx import docx_to_doc
from techradar.parser.epub import epub_to_chapters
from techradar.parser.limits import parse_job
from techradar.schemas.pipeline import ParseJob
from tests.intake.library_fixtures import make_docx, make_epub, make_zip_bomb


def test_epub_chapters_follow_spine(tmp_path):
    chapters = epub_to_chapters(make_epub(tmp_path / "ok.epub"), 100_000)
    assert [c.title for c in chapters] == ["Chapter 1", "Chapter 2"]
    assert "First text." in chapters[0].text and "Second text." in chapters[1].text


def test_epub_spine_order_wins_over_file_order(tmp_path):
    book = make_epub(tmp_path / "b.epub", chapters=[("A", "alpha"), ("B", "beta")])
    # Rewrite the OPF so the spine lists c1 before c0.
    src = zipfile.ZipFile(book)
    out = tmp_path / "r.epub"
    with zipfile.ZipFile(out, "w") as z:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.endswith(".opf"):
                data = data.replace(
                    b'<itemref idref="c0"/><itemref idref="c1"/>',
                    b'<itemref idref="c1"/><itemref idref="c0"/>',
                )
            z.writestr(info, data)
    assert [c.title for c in epub_to_chapters(out, 100_000)] == ["B", "A"]


def test_epub_refuses_unsafe_archives(tmp_path):
    with pytest.raises(ValueError, match="archive"):
        epub_to_chapters(make_zip_bomb(tmp_path / "bomb.epub"), 100_000)


def test_epub_manifest_cannot_point_outside_the_book(tmp_path):
    book = make_epub(tmp_path / "e.epub")
    src = zipfile.ZipFile(book)
    out = tmp_path / "x.epub"
    with zipfile.ZipFile(out, "w") as z:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.endswith(".opf"):
                data = data.replace(b'href="c0.xhtml"', b'href="../../../etc/passwd"')
            z.writestr(info, data)
    titles = [c.title for c in epub_to_chapters(out, 100_000)]
    assert titles == ["Chapter 2"]  # the escaping item is skipped, not followed


def test_docx_text_extracted(tmp_path):
    doc = docx_to_doc(make_docx(tmp_path / "a.docx"), "library:a", 100_000)
    assert doc is not None and "Hello library" in doc.text


def _job(tmp_path: Path, data: bytes, kind: str, ext: str) -> ParseJob:
    name = f"{hashlib.sha256(data).hexdigest()}.{ext}"
    (tmp_path / name).write_bytes(data)
    return ParseJob(
        job_id="a" * 32,
        kind=kind,
        raw_name=name,
        url="library:x",
        source_id=0,
        origin="library",
        purpose="library",
    )


def test_parse_job_epub_marks_chapters(tmp_path):
    data = make_epub(tmp_path / "src.epub").read_bytes()
    res = parse_job(_job(tmp_path, data, "epub", "epub"), tmp_path, max_bytes=50_000_000)
    assert res.status == "ok" and res.doc is not None
    assert "<!-- chapter 1: Chapter 1 -->" in res.doc.text
    assert res.doc.text.index("chapter 1:") < res.doc.text.index("chapter 2:")


def test_parse_job_docx(tmp_path):
    data = make_docx(tmp_path / "src.docx").read_bytes()
    res = parse_job(_job(tmp_path, data, "docx", "docx"), tmp_path, max_bytes=50_000_000)
    assert res.status == "ok" and res.doc is not None and "Hello library" in res.doc.text
