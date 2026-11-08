from __future__ import annotations

import trafilatura

from techradar.schemas.pipeline import CleanDoc
from techradar.security.text import detect_lang, sanitize_text

MIN_TEXT_CHARS = 200


def html_to_doc(data: bytes, url: str, max_chars: int = 100_000) -> CleanDoc | None:
    """Extract clean readable text and metadata from HTML bytes."""
    try:
        extracted = trafilatura.extract(
            data,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
    except Exception:
        return None

    if not extracted:
        return None

    text = sanitize_text(extracted)
    if len(text) < MIN_TEXT_CHARS:
        return None

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    lang = detect_lang(text)

    title = "Untitled"
    try:
        meta = trafilatura.extract_metadata(data, default_url=url)
        if meta and meta.title:
            title = meta.title.strip() or "Untitled"
    except Exception:
        title = "Untitled"

    return CleanDoc(
        url=url,
        title=title[:300],
        text=text,
        lang=lang,
        truncated=truncated,
    )
