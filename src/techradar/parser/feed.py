from __future__ import annotations

from datetime import UTC, datetime

import defusedxml.ElementTree as dET
import feedparser
import trafilatura
from defusedxml.common import (
    DTDForbidden,
    EntitiesForbidden,
    ExternalReferenceForbidden,
)

from techradar.schemas.pipeline import FeedEntry
from techradar.security.text import sanitize_text


def feed_to_entries(data: bytes, max_entries: int = 200) -> list[FeedEntry]:
    """Parse RSS/Atom feed data and return sanitized feed entries, rejecting XML entities/DTDs."""
    try:
        dET.fromstring(data, forbid_dtd=True)
    except (DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden) as exc:
        raise ValueError(f"xml_entities: {exc}") from exc
    except dET.ParseError, UnicodeDecodeError, ValueError:
        # Non-XML or malformed XML handled gracefully by feedparser
        pass

    try:
        parsed = feedparser.parse(data)
    except Exception:
        return []

    entries: list[FeedEntry] = []
    raw_entries = getattr(parsed, "entries", []) or []

    for entry in raw_entries[:max_entries]:
        title = sanitize_text(str(entry.get("title", "") or ""))[:300]
        link = str(entry.get("link", "") or "")[:2000]
        raw_summary = str(entry.get("summary", "") or "")
        summary_text = trafilatura.html2txt(raw_summary) if raw_summary else ""
        summary = sanitize_text(summary_text)[:2000]

        dt: datetime | None = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                dt = datetime(*entry.published_parsed[:6], tzinfo=UTC)
            except Exception:
                dt = None
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            try:
                dt = datetime(*entry.updated_parsed[:6], tzinfo=UTC)
            except Exception:
                dt = None

        entries.append(
            FeedEntry(
                title=title,
                link=link,
                published=dt,
                summary=summary,
            )
        )

    return entries
