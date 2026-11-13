from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from techradar.library.parts import split_pdf_parts
from techradar.security.text import sanitize_text

if TYPE_CHECKING:
    from techradar.parser.pdf import OutlineEntry

MAX_TITLE = 300
_MARKER = re.compile(r"^<!-- page (\d+) -->$", re.MULTILINE)


def _clean_title(title: str) -> str:
    return " ".join(sanitize_text(title).split())[:MAX_TITLE]


class ChapterSpec(BaseModel):
    ordinal: int
    title: str
    page_start: int
    page_end: int


def _from_starts(starts: Iterable[tuple[int, str]], n_pages: int) -> list[ChapterSpec] | None:
    """Chapters from (page, title) starts; None when fewer than two distinct starts fit."""
    seen: dict[int, str] = {}
    for page, title in sorted(starts, key=lambda s: s[0]):
        page = max(page, 1)
        if page <= n_pages and page not in seen:
            seen[page] = _clean_title(title)
    if len(seen) < 2:
        return None
    pages = list(seen)
    pages[0] = 1  # front matter belongs to the first chapter
    ends = [p - 1 for p in pages[1:]] + [n_pages]
    return [
        ChapterSpec(ordinal=i + 1, title=title, page_start=s, page_end=e)
        for i, ((s, e), title) in enumerate(
            zip(zip(pages, ends, strict=True), seen.values(), strict=True)
        )
    ]


def detect_chapters(
    n_pages: int,
    outline: Sequence[OutlineEntry],
    headings: Sequence[tuple[int, int, str]],
    part_pages: int = 25,
) -> list[ChapterSpec]:
    """Chapters from level-1 outline entries, else level-1 headings, else fixed page ranges."""
    if n_pages <= 0:
        return []
    found = _from_starts(((e.page, e.title) for e in outline if e.level == 1), n_pages)
    if found is None:
        found = _from_starts(((p, t) for p, lvl, t in headings if lvl == 1), n_pages)
    if found is not None:
        return found
    return [
        ChapterSpec(
            ordinal=p.ordinal,
            title=f"Pages {p.page_start}–{p.page_end}",
            page_start=p.page_start,
            page_end=p.page_end,
        )
        for p in split_pdf_parts(n_pages, part_pages)
    ]


def _split_pages(text: str) -> dict[int, str]:
    """Page number -> its block of text, including the page marker line."""
    marks = list(_MARKER.finditer(text))
    return {
        int(m.group(1)): text[
            m.start() : marks[i + 1].start() if i + 1 < len(marks) else None
        ].strip()
        for i, m in enumerate(marks)
    }


def _note(first: int, last: int) -> str:
    if first == last:
        return f"> Page {first} couldn't be read."
    return f"> Pages {first}–{last} couldn't be read."


def _page_map(part_texts: Mapping[int, str]) -> dict[int, str]:
    pages: dict[int, str] = {}
    for text in part_texts.values():
        pages.update(_split_pages(text))
    return pages


def missing_pages(
    part_texts: Mapping[int, str], ch: ChapterSpec, failed_pages: Sequence[int]
) -> list[int]:
    """Pages of the chapter that failed or are absent from the part texts, in order."""
    pages = _page_map(part_texts)
    failed = set(failed_pages)
    return [n for n in range(ch.page_start, ch.page_end + 1) if n in failed or n not in pages]


def assemble_chapter_text(
    part_texts: Mapping[int, str], ch: ChapterSpec, failed_pages: Sequence[int]
) -> str:
    """Join the chapter's pages in order, noting unreadable or missing ranges in place."""
    pages = _page_map(part_texts)
    missing = set(missing_pages(part_texts, ch, failed_pages))
    out: list[str] = []
    run: list[int] = []

    def flush() -> None:
        if run:
            out.append(_note(run[0], run[-1]))
            run.clear()

    for n in range(ch.page_start, ch.page_end + 1):
        if n in missing:
            run.append(n)
            continue
        flush()
        out.append(pages[n])
    flush()
    return "\n\n".join(out)


def write_chapter_text(base: Path, doc_id: int, ordinal: int, text: str) -> Path:
    """Write <base>/text/<doc_id>/<NN>.md (mode 0o640) and return its path."""
    path = base / "text" / str(doc_id) / f"{ordinal:02d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    path.chmod(0o640)
    return path
