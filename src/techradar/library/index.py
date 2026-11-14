"""Index one library chapter into `chunks` (Phase 2c Task 6).

Each chunk is embedded with a context label in front (`Book › Chapter › Section`), so a
sentence like "the rate was cut" is found under the right book. The label is stored in its
own column; the stored text never contains it. The embedder input is label + blank line + text.

How answers learn the doc's trust (official / open / my own): `chunks` has no trust column and
this task does not add one, so the answer layer must join `chunks.doc_id` to
`library_docs.trust` and show `trust_label(trust)`.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Literal

from sqlalchemy import delete

from techradar.db.models import BookEval, Chunk, LibraryChapter, LibraryDoc
from techradar.rag.chunker import context_label, page_of, split_markdown
from techradar.rag.indexer import IndexDeps
from techradar.security.text import detect_lang, sanitize_text

logger = logging.getLogger(__name__)

__all__ = ["context_label", "index_library_chapter", "page_of", "trust_label"]

EMBED_BATCH = 16
_TRUST_LABELS: dict[str, Literal["official", "open", "my own"]] = {
    "official": "official",
    "open": "open",
    "my_own": "my own",
}


def trust_label(trust: str) -> Literal["official", "open", "my own"]:
    """Reader-facing name of a `library_docs.trust` value."""
    try:
        return _TRUST_LABELS[trust]
    except KeyError:
        raise ValueError(f"unknown library trust: {trust!r}") from None


def _read_chapter_text(library_dir: Path, text_path: str) -> str | None:
    """The chapter text file, or None when it is missing, unreadable, empty or outside the dir."""
    base = library_dir.resolve()
    path = (base / text_path).resolve()
    if not path.is_relative_to(base):
        logger.warning("library chapter text path escapes the library dir; not indexing")
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("library chapter text unreadable (%s); not indexing", type(exc).__name__)
        return None
    return sanitize_text(text) if text.strip() else None


def _section_path(chapter_title: str, heading_path: list[str]) -> list[str]:
    """The headings below the chapter: the chapter's own `# <title>` heading (always the
    first one in its text) is dropped, so the label reads `Book › Chapter › Section`
    and not `Book › Chapter › Chapter › Section`."""
    if heading_path and heading_path[0].strip().casefold() == chapter_title.strip().casefold():
        return heading_path[1:]
    return heading_path


async def index_library_chapter(deps: IndexDeps, chapter_id: int) -> int:
    """Chunk, embed and store one chapter; returns the chunk count.

    Idempotent: the chapter's old chunks are deleted and the new ones inserted in one
    transaction. A missing chapter or doc row, or a missing/empty text file, indexes nothing,
    returns 0 and leaves existing chunks alone. The chapter text is untrusted: it is only
    split and embedded, never interpreted, and its file path never enters a chunk.
    """
    async with deps.session_factory() as session:
        chapter = await session.get(LibraryChapter, chapter_id)
        doc = await session.get(LibraryDoc, chapter.doc_id) if chapter else None
        if chapter is None or doc is None:
            logger.warning("library chapter %s has no chapter or doc row; not indexing", chapter_id)
            return 0
        doc_id, ordinal = chapter.doc_id, chapter.ordinal
        chapter_title, first_page = chapter.title, chapter.page_start
        text_path = chapter.text_path
        book, exam_tags = doc.title, list(doc.exam_tags or [])
        flagged = bool(doc.flagged)  # the gateway's (or an owner release's) verdict

    text = _read_chapter_text(deps.library_dir, text_path)
    if text is None:
        logger.warning("library chapter %s has no text; nothing indexed", chapter_id)
        return 0

    rows: list[tuple[str, str, list[str], int | None]] = []  # label, text, headings, page
    last_page = first_page
    for c in split_markdown(text, "chapter"):
        page, clean = page_of(c.text, last_page)
        last_page = page
        if not clean:
            continue
        label = context_label(book, chapter_title, _section_path(chapter_title, c.heading_path))
        rows.append((label, clean, list(c.heading_path), page))
    if not rows:
        logger.warning("library chapter %s has no indexable text; nothing indexed", chapter_id)
        return 0

    embeddings: list[list[float]] = []
    for i in range(0, len(rows), EMBED_BATCH):
        batch = [f"{label}\n\n{body}" for label, body, _, _ in rows[i : i + EMBED_BATCH]]
        embeddings.extend(await deps.embedder.embed(batch))

    doc_path = f"library/{doc_id}/{ordinal:02d}.md"
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    lang = detect_lang(text)
    async with deps.session_factory() as session:
        await session.execute(delete(Chunk).where(Chunk.chapter_id == chapter_id))
        # `book_evals.expected_chunk_ids` has no foreign key: the old chunk ids are gone now, so
        # the doc's evals would point at nothing. They are made again by the next ready run.
        await session.execute(delete(BookEval).where(BookEval.doc_id == doc_id))
        for n, (label, body, headings, page) in enumerate(rows):
            session.add(
                Chunk(
                    doc_path=doc_path,
                    doc_kind="library",
                    title=book,
                    heading_path=headings,
                    ordinal=n,
                    text=body,
                    lang=lang,
                    section=None,
                    exam_tags=exam_tags,
                    verified=None,
                    generated=False,
                    # Vault notes set this from the gateway verdict (rag/indexer.py reads
                    # result.intake.verdict). Library parts keep no verdict: jobs.py does not
                    # store result.intake, and a rejected or quarantined part never becomes
                    # a chapter. So the only source here is the default, False.
                    flagged=flagged,
                    source_domains=[],
                    content_hash=content_hash,
                    embedding=embeddings[n] if n < len(embeddings) else None,
                    doc_id=doc_id,
                    chapter_id=chapter_id,
                    page=page,
                    context_label=label,
                )
            )
        await session.commit()
    return len(rows)
