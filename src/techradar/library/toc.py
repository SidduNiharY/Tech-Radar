from __future__ import annotations

from typing import Any

from techradar.library.models import Chapter
from techradar.pipeline.writer import slugify


def chunk_by_page_ranges(page_count: int, part_size: int = 25) -> list[tuple[int, int]]:
    """Generates (start_page, end_page) 1-based inclusive slices for chunking long PDFs."""
    if page_count <= 0:
        return []
    if part_size <= 0:
        raise ValueError("part_size must be positive")

    ranges: list[tuple[int, int]] = []
    start = 1
    while start <= page_count:
        end = min(start + part_size - 1, page_count)
        ranges.append((start, end))
        start = end + 1
    return ranges


def _normalize_bookmark(b: Any) -> dict[str, Any]:
    if hasattr(b, "model_dump"):
        return b.model_dump()
    if hasattr(b, "dict"):
        return b.dict()
    if isinstance(b, dict):
        return dict(b)
    return {}


def extract_outline_chapters(bookmarks: list[dict[str, Any]], page_count: int) -> list[Chapter]:
    """Extract flat chapter list with start and end pages from PDF bookmark outlines."""
    if not bookmarks:
        return []

    normalized_list = [_normalize_bookmark(b) for b in bookmarks]

    levels = [int(b["level"]) for b in normalized_list if "level" in b and b["level"] is not None]
    min_level = min(levels) if levels else None

    candidates: list[dict[str, Any]] = []
    for b in normalized_list:
        if min_level is not None and "level" in b and b["level"] is not None:
            if int(b["level"]) != min_level:
                continue

        raw_title = b.get("title") or b.get("name") or b.get("label") or b.get("text") or ""
        title = str(raw_title).strip()

        if "start_page" in b and b["start_page"] is not None:
            start_page = int(b["start_page"])
        elif "page" in b and b["page"] is not None:
            start_page = int(b["page"])
        elif "page_number" in b and b["page_number"] is not None:
            start_page = int(b["page_number"])
        elif "page_index" in b and b["page_index"] is not None:
            start_page = int(b["page_index"]) + 1
        elif "page_idx" in b and b["page_idx"] is not None:
            start_page = int(b["page_idx"]) + 1
        else:
            start_page = 1

        start_page = max(1, start_page)

        end_page_val = None
        if "end_page" in b and b["end_page"] is not None:
            end_page_val = int(b["end_page"])

        slug_val = str(b["slug"]).strip() if "slug" in b and b["slug"] else None

        candidates.append(
            {
                "title": title,
                "start_page": start_page,
                "end_page": end_page_val,
                "slug": slug_val,
            }
        )

    if not candidates:
        return []

    candidates.sort(key=lambda c: c["start_page"])

    chapters: list[Chapter] = []
    seen_slugs: set[str] = set()

    for idx, cand in enumerate(candidates, start=1):
        start_page = cand["start_page"]
        title = cand["title"] or f"Chapter {idx}"

        if cand["end_page"] is not None:
            end_page = cand["end_page"]
        elif idx < len(candidates):
            next_start = candidates[idx]["start_page"]
            end_page = max(start_page, next_start - 1)
        else:
            end_page = max(start_page, page_count)

        if page_count >= start_page:
            end_page = min(end_page, page_count)

        slug = cand["slug"]
        if not slug:
            slug = slugify(title)
            if not slug or slug == "note":
                slug = f"chapter-{idx}"
            if slug in seen_slugs:
                slug = f"{slug}-{idx}"
        seen_slugs.add(slug)

        chapters.append(
            Chapter(
                title=title,
                ordinal=idx,
                start_page=start_page,
                end_page=end_page,
                slug=slug,
            )
        )

    return chapters
