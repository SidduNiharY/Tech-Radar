"""Write the 300-page test book for Gate 2c (Phase 2c Task 11).

A plain PDF 1.4 file built with the standard library only: real text on every page
(Helvetica, so pypdfium2 and Docling extract it), a heading on the first page of each
chapter and a bookmark outline, one level-1 entry per chapter. Chapters are 30 pages,
so they do not line up with the parser's 25-page parts. Each page carries "Page N" and
a unique marker `fact-N`, so page references can be checked.

The output is deterministic (no dates or ids) and has no JavaScript, actions or
embedded files, so the Intake Gateway passes it as a clean PDF.

Usage: python scripts/make_big_pdf.py [--out tests/fixtures/library/big_300_pages.pdf]
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests/fixtures/library/big_300_pages.pdf"
N_PAGES = 300
PAGES_PER_CHAPTER = 30
CHAPTER_TITLES = [
    "Packets and Protocols",
    "Routing Tables",
    "Process Scheduling",
    "Memory and Paging",
    "File Systems",
    "Relational Algebra",
    "Transactions and Locks",
    "Graph Algorithms",
    "Dynamic Programming",
    "Compilers and Parsing",
]
BODY_LINES = [
    "This page belongs to the Gate 2c test book. Every page has its own marker",
    "so a search result can be traced back to the page it came from.",
    "The text is plain and repeated on purpose: it is a fixture, not a lesson.",
    "Retrieval must cite this page number when it answers from this page.",
]


def _pdf_string(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return b"(" + escaped.encode("latin-1") + b")"


def chapter_of(page: int) -> int:
    return (page - 1) // PAGES_PER_CHAPTER + 1


def chapter_title(n: int) -> str:
    return f"Chapter {n}: {CHAPTER_TITLES[n - 1]}"


def _page_stream(page: int) -> bytes:
    ch = chapter_of(page)
    ops: list[bytes] = []
    y = 740
    if (page - 1) % PAGES_PER_CHAPTER == 0:
        ops.append(b"BT /F2 20 Tf 72 %d Td " % y + _pdf_string(chapter_title(ch)) + b" Tj ET")
        y -= 40
    header = f"Chapter {ch}, Page {page}"
    ops.append(b"BT /F2 14 Tf 72 %d Td " % y + _pdf_string(header) + b" Tj ET")
    y -= 28
    lines = [*BODY_LINES, f"Marker for this page: fact-{page}. Page {page} of {N_PAGES}."]
    for line in lines:
        ops.append(b"BT /F1 11 Tf 72 %d Td " % y + _pdf_string(line) + b" Tj ET")
        y -= 16
    return b"\n".join(ops)


def build_pdf(n_pages: int = N_PAGES) -> bytes:
    """The whole file as bytes."""
    n_chapters = (n_pages + PAGES_PER_CHAPTER - 1) // PAGES_PER_CHAPTER
    if n_chapters > len(CHAPTER_TITLES):
        raise ValueError("not enough chapter titles")
    # Object numbers: 1 catalog, 2 pages, 3-4 fonts, 5 outline root, then one per
    # chapter bookmark, then a page and its content stream for every page.
    first_bookmark = 6
    first_page = first_bookmark + n_chapters
    page_obj = [first_page + 2 * i for i in range(n_pages)]

    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R /Outlines 5 0 R /PageMode /UseOutlines >>"
    kids = b" ".join(b"%d 0 R" % n for n in page_obj)
    objects[2] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % n_pages
    objects[3] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    objects[4] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    last_bookmark = first_bookmark + n_chapters - 1
    objects[5] = b"<< /Type /Outlines /First %d 0 R /Last %d 0 R /Count %d >>" % (
        first_bookmark,
        last_bookmark,
        n_chapters,
    )
    for i in range(n_chapters):
        num = first_bookmark + i
        target = page_obj[i * PAGES_PER_CHAPTER]
        links = b""
        if i > 0:
            links += b" /Prev %d 0 R" % (num - 1)
        if i < n_chapters - 1:
            links += b" /Next %d 0 R" % (num + 1)
        objects[num] = (
            b"<< /Title "
            + _pdf_string(chapter_title(i + 1))
            + b" /Parent 5 0 R"
            + links
            + b" /Dest [%d 0 R /XYZ 0 792 0] >>" % target
        )
    for i, num in enumerate(page_obj):
        stream = _page_stream(i + 1)
        objects[num] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>" % (num + 1)
        )
        objects[num + 1] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + objects[num] + b"\nendobj\n"
    xref_at = len(out)
    size = max(objects) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % size
    for num in range(1, size):
        out += b"%010d 00000 n \n" % offsets[num]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (size, xref_at)
    return bytes(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_bytes(build_pdf())
    tmp.replace(args.out)
    print(f"wrote {args.out} ({N_PAGES} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
