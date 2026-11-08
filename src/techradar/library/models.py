from __future__ import annotations

from pydantic import BaseModel, Field


class Chapter(BaseModel):
    title: str
    ordinal: int
    start_page: int
    end_page: int
    slug: str


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
