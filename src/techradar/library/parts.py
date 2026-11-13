from __future__ import annotations

from pydantic import BaseModel


class PartSpec(BaseModel):
    ordinal: int
    page_start: int
    page_end: int


def split_pdf_parts(n_pages: int, part_pages: int = 25) -> list[PartSpec]:
    """Split pages 1..n_pages into 1-based inclusive parts of at most part_pages."""
    if part_pages <= 0:
        raise ValueError("part_pages must be positive")
    return [
        PartSpec(ordinal=i + 1, page_start=s, page_end=min(s + part_pages - 1, n_pages))
        for i, s in enumerate(range(1, n_pages + 1, part_pages))
    ]
