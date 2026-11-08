from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Chapter(BaseModel):
    title: str
    ordinal: int
    start_page: int
    end_page: int
    slug: str
    missing_pages: list[int] = Field(default_factory=list)


class BookMeta(BaseModel):
    title: str
    author: str | None = None
    doc_kind: str = "library"
    exam_tags: list[str] = Field(default_factory=list)
    page_count: int = 0
    chapters: list[Chapter] = Field(default_factory=list)


class LibraryPart(BaseModel):
    book_slug: str
    part_index: int
    start_page: int
    end_page: int
    status: str = "pending"
    part_id: str | None = None
    error: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.part_id is None:
            self.part_id = f"{self.book_slug}-part-{self.part_index}"


class LibraryDoc(BaseModel):
    doc_id: str
    sha256: str
    title: str
    original_path: Path
    trust: str = "official"
    status: str = "pending"
    page_count: int = 0
    parts: list[LibraryPart] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)


class MediaInfo(BaseModel):
    format_name: str = ""
    duration_s: float = 0.0
    has_audio: bool = False
    has_video: bool = False
    size_bytes: int = 0
