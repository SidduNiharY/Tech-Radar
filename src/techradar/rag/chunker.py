"""Markdown chunker for vault and library documents (Phase 2b Task 1 / SEC-41)."""

from __future__ import annotations

import math
import re
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Chunk(BaseModel):
    """Structured chunk of a indexed document."""

    model_config = ConfigDict(extra="forbid")

    doc_path: str
    heading_path: list[str]
    ordinal: int
    text: str = Field(min_length=1, max_length=10000)
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


def _parse_sections(body: str) -> list[_Section]:
    """Parse markdown body into sections delineated by headings # to ###."""
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
            current_block_lines.append(line)

    flush_block()
    return [s for s in sections if s.blocks]


def split_markdown(
    md: str,
    doc_path: str,
    *,
    target_tokens: int = 500,
    overlap_tokens: int = 60,
) -> list[Chunk]:
    """Split markdown text into structured chunks keeping headings, code fences and overlaps."""
    _, body = parse_front_matter(md)
    if not body.strip():
        return []

    sections = _parse_sections(body)
    if not sections:
        return []

    chunks: list[Chunk] = []
    ordinal = 0

    for section in sections:
        current_blocks: list[str] = []
        last_chunk_text: str | None = None

        for block in section.blocks:
            candidate_blocks = list(current_blocks) + [block]
            candidate_text = "\n\n".join(candidate_blocks).strip()
            candidate_tokens = estimate_tokens(candidate_text)

            if candidate_tokens > target_tokens and current_blocks:
                # Emit current chunk
                chunk_text = "\n\n".join(current_blocks).strip()
                if chunk_text:
                    chunks.append(
                        Chunk(
                            doc_path=doc_path,
                            heading_path=list(section.heading_path),
                            ordinal=ordinal,
                            text=chunk_text,
                            token_estimate=estimate_tokens(chunk_text),
                        )
                    )
                    ordinal += 1
                    last_chunk_text = chunk_text

                # Start new chunk with overlap from last chunk
                words = chunk_text.split()
                if len(words) > overlap_tokens:
                    overlap_str = " ".join(words[-overlap_tokens:])
                else:
                    overlap_str = chunk_text

                current_blocks = [overlap_str, block]
            else:
                current_blocks = candidate_blocks

        if current_blocks:
            chunk_text = "\n\n".join(current_blocks).strip()
            if chunk_text and chunk_text != last_chunk_text:
                chunks.append(
                    Chunk(
                        doc_path=doc_path,
                        heading_path=list(section.heading_path),
                        ordinal=ordinal,
                        text=chunk_text,
                        token_estimate=estimate_tokens(chunk_text),
                    )
                )
                ordinal += 1

    return chunks
