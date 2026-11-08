from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium

from techradar.schemas.pipeline import CleanDoc
from techradar.security.text import detect_lang, sanitize_text

MIN_TEXT_CHARS = 200


def pdf_to_doc(
    path: Path,
    url: str,
    max_chars: int = 100_000,
    artifacts_path: Path | None = None,
) -> CleanDoc | None:
    """Extract clean text and metadata from a PDF file using pypdfium2."""
    del artifacts_path  # Accepted for interface compatibility with offline docling models
    try:
        pdf = pdfium.PdfDocument(path)
        parts: list[str] = []
        for page in pdf:
            textpage = page.get_textpage()
            t = textpage.get_text_range()
            if t:
                parts.append(t)
        raw_text = "\n\n".join(parts)
    except Exception:
        return None

    text = sanitize_text(raw_text)
    if len(text) < MIN_TEXT_CHARS:
        return None

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    lang = detect_lang(text)

    title = "Untitled"
    try:
        meta = pdf.get_metadata_dict()
        if meta and meta.get("Title"):
            title = str(meta["Title"]).strip() or "Untitled"
    except Exception:
        title = "Untitled"

    if title == "Untitled":
        title = path.stem.replace("_", " ").title()

    return CleanDoc(
        url=url,
        title=title[:300],
        text=text,
        lang=lang,
        truncated=truncated,
    )
