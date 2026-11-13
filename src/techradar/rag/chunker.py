"""Markdown chunker for vault and library documents (Phase 2b Task 1 / SEC-41)."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

_MAX_CHUNK_CHARS = 10000


class Chunk(BaseModel):
    """Structured chunk of a indexed document."""

    model_config = ConfigDict(extra="forbid")

    doc_path: str
    heading_path: list[str]
    ordinal: int
    text: str = Field(min_length=1, max_length=_MAX_CHUNK_CHARS)
    token_estimate: int


def estimate_tokens(text: str) -> int:
    """Estimate token count from word count: ceil(words * 1.3)."""
    words = len(text.split())
    return math.ceil(words * 1.3)


def parse_front_matter(md: str) -> tuple[dict[str, Any], str]:
    """Parse leading YAML front-matter block, returning (metadata_dict, body_text)."""
    if not md.startswith("---"):
        return {}, md

    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", md)
    if not match:
        return {}, md

    raw_yaml = match.group(1)
    body = md[match.end() :]

    try:
        data = yaml.safe_load(raw_yaml)
        if isinstance(data, dict):
            return data, body
    except yaml.YAMLError:
        return {}, md

    return {}, md


class _Section:
    def __init__(self, heading_path: list[str]) -> None:
        self.heading_path = heading_path
        self.blocks: list[str] = []


def _is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _is_table_block(block: str) -> bool:
    return all(_is_table_line(line) for line in block.splitlines())


def _parse_sections(body: str, *, keep_tables: bool = True) -> list[_Section]:
    """Parse markdown body into sections delineated by headings # to ###.

    With keep_tables, a run of consecutive lines starting with `|` is always its own block,
    even when no blank line separates it from the text around it.
    """
    lines = body.splitlines()
    sections: list[_Section] = []
    current_heading_path: list[str] = []
    current_section = _Section([])
    sections.append(current_section)

    in_code = False
    current_block_lines: list[str] = []

    def flush_block() -> None:
        if current_block_lines:
            block = "\n".join(current_block_lines).strip()
            if block:
                current_section.blocks.append(block)
            current_block_lines.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            current_block_lines.append(line)
            if not in_code:
                # Finished a code block
                flush_block()
            continue

        if in_code:
            current_block_lines.append(line)
            continue

        # Check for heading
        heading_match = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading_match:
            flush_block()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()

            if level == 1:
                current_heading_path = [title]
            elif level == 2:
                if len(current_heading_path) >= 1:
                    current_heading_path = [current_heading_path[0], title]
                else:
                    current_heading_path = [title]
            elif level == 3:
                if len(current_heading_path) >= 2:
                    current_heading_path = [
                        current_heading_path[0],
                        current_heading_path[1],
                        title,
                    ]
                elif len(current_heading_path) == 1:
                    current_heading_path = [current_heading_path[0], title]
                else:
                    current_heading_path = [title]

            current_section = _Section(list(current_heading_path))
            sections.append(current_section)
            continue

        if not stripped:
            flush_block()
        else:
            if (
                keep_tables
                and current_block_lines
                and _is_table_line(line) != _is_table_line(current_block_lines[-1])
            ):
                flush_block()
            current_block_lines.append(line)

    flush_block()
    return [s for s in sections if s.blocks]


MAX_TABLE_CHARS = 4000
_SEPARATOR_ROW = re.compile(r"^\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?$")


def _split_big_table(table: str, limit: int = MAX_TABLE_CHARS) -> list[str]:
    """Split a table at row boundaries; every piece repeats the header and `|---|` line.

    A single row longer than the limit stays whole (cut only to fit Chunk.text).
    """
    lines = table.splitlines()
    header: list[str] = []
    if len(lines) >= 2 and _SEPARATOR_ROW.match(lines[1].strip()):
        header, lines = lines[:2], lines[2:]
    head_text = "\n".join(header)
    pieces: list[str] = []
    rows: list[str] = []
    size = len(head_text)
    for row in lines:
        if rows and size + 1 + len(row) > limit:
            pieces.append("\n".join([*header, *rows]))
            rows, size = [], len(head_text)
        rows.append(row)
        size += 1 + len(row)
    if rows:
        pieces.append("\n".join([*header, *rows]))
    return [p[:_MAX_CHUNK_CHARS] for p in pieces]


BLOCK_CAP_CHARS = 8_000  # one block never exceeds this; a chunk is at most 10,000
SOFT_CHUNK_CHARS = 9_000  # flush a chunk before it gets near the 10,000 limit
OVERLAP_MAX_CHARS = 600  # words can be huge (OCR blobs); the overlap never is


def _hard_split(text: str, limit: int) -> list[str]:
    """Pieces of at most `limit` chars, cut at whitespace where possible."""
    pieces: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = max(rest.rfind("\n", 0, limit), rest.rfind(" ", 0, limit))
        if cut < limit // 2:  # no usable break (an unbroken OCR blob): cut hard
            cut = limit
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest.strip():
        pieces.append(rest)
    return [p for p in pieces if p.strip()]


def _cap_block(block: str, limit: int = BLOCK_CAP_CHARS) -> list[str]:
    """Split a paragraph or code fence longer than `limit` so no chunk is rejected.

    A code fence stays a fence: each piece is wrapped in the same fence markers.
    Tables are handled separately (_split_big_table) and are returned unchanged.
    """
    if len(block) <= limit or _is_table_block(block):
        return [block]
    lines = block.splitlines()
    if lines and lines[0].lstrip().startswith(("```", "~~~")):
        fence = lines[0].strip()
        marker = fence[:3]
        body = "\n".join(lines[1:])
        if body.rstrip().endswith(marker):
            body = body.rstrip()[: -len(marker)].rstrip()
        return [f"{fence}\n{piece}\n{marker}" for piece in _hard_split(body, limit - 20)]
    return _hard_split(block, limit)


def split_markdown(
    md: str,
    doc_path: str,
    *,
    target_tokens: int = 500,
    overlap_tokens: int = 60,
    keep_tables: bool = True,
) -> list[Chunk]:
    """Split markdown text into structured chunks keeping headings, code fences and overlaps.

    With keep_tables, a Markdown table is never split, except one over 4,000 characters:
    that becomes its own chunks, cut at row boundaries, each with the header row repeated.
    """
    _, body = parse_front_matter(md)
    if not body.strip():
        return []

    sections = _parse_sections(body, keep_tables=keep_tables)
    if not sections:
        return []

    chunks: list[Chunk] = []

    def emit(section: _Section, text: str) -> None:
        text = text[:_MAX_CHUNK_CHARS]  # safety net: a chunk is never rejected for length
        chunks.append(
            Chunk(
                doc_path=doc_path,
                heading_path=list(section.heading_path),
                ordinal=len(chunks),
                text=text,
                token_estimate=estimate_tokens(text),
            )
        )

    for section in sections:
        current_blocks: list[str] = []
        last_chunk_text: str | None = None

        blocks = [piece for b in section.blocks for piece in _cap_block(b)]
        for block in blocks:
            if keep_tables and len(block) > MAX_TABLE_CHARS and _is_table_block(block):
                chunk_text = "\n\n".join(current_blocks).strip()
                if chunk_text and chunk_text != last_chunk_text:
                    emit(section, chunk_text)
                for piece in _split_big_table(block):
                    emit(section, piece)
                current_blocks = []
                last_chunk_text = None
                continue

            candidate_blocks = list(current_blocks) + [block]
            candidate_text = "\n\n".join(candidate_blocks).strip()
            candidate_tokens = estimate_tokens(candidate_text)

            if (
                candidate_tokens > target_tokens or len(candidate_text) > SOFT_CHUNK_CHARS
            ) and current_blocks:
                # Emit current chunk
                chunk_text = "\n\n".join(current_blocks).strip()
                if chunk_text:
                    emit(section, chunk_text)
                    last_chunk_text = chunk_text

                # Start new chunk with overlap from last chunk; never carry row fragments
                # of a table into the next chunk.
                if keep_tables and _is_table_block(current_blocks[-1]):
                    current_blocks = [block]
                    continue
                words = chunk_text.split()
                if len(words) > overlap_tokens:
                    overlap_str = " ".join(words[-overlap_tokens:])
                else:
                    overlap_str = chunk_text
                overlap_str = overlap_str[-OVERLAP_MAX_CHARS:]

                current_blocks = [overlap_str, block]
            else:
                current_blocks = candidate_blocks

        if current_blocks:
            chunk_text = "\n\n".join(current_blocks).strip()
            if chunk_text and chunk_text != last_chunk_text:
                emit(section, chunk_text)

    return chunks


_PAGE_MARKER = re.compile(r"<!--[ \t]*page[ \t]+(\d{1,6})[ \t]*-->[ \t]*\n?")
MAX_LABEL_CHARS = 200


def page_of(chunk_text: str, last_page: int | None) -> tuple[int | None, str]:
    """The page a chunk ends on, and the chunk text without its `<!-- page N -->` markers.

    The page is the last marker inside the chunk; a chunk with no marker gets `last_page`
    (the page the caller saw most recently). Only that exact marker form is removed.
    """
    found = _PAGE_MARKER.findall(chunk_text)
    page = int(found[-1]) if found else last_page
    return page, _PAGE_MARKER.sub("", chunk_text).strip()


def context_label(book: str, chapter: str, heading_path: Sequence[str]) -> str:
    """`<book> › <chapter> › <section>` (empty parts left out), cut to 200 characters."""
    section = " › ".join(h.strip() for h in heading_path if h.strip())
    parts = [p.strip() for p in (book, chapter, section) if p and p.strip()]
    return " › ".join(parts)[:MAX_LABEL_CHARS]
