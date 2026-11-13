"""DOCX reader for the parser sandbox (Phase 2c Task 3).

Runs only after the gateway's archive, macro and XML checks passed. Docling's
DOCX pipeline uses no models, so it never needs the network.
"""

from __future__ import annotations

from pathlib import Path

from techradar.schemas.pipeline import CleanDoc
from techradar.security.text import detect_lang, sanitize_text


def docx_to_doc(path: Path, url: str, max_chars: int) -> CleanDoc | None:
    """Text of a DOCX through Docling, or None if it has no text."""
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter(allowed_formats=[InputFormat.DOCX])
    document = converter.convert(path).document
    text = sanitize_text(document.export_to_markdown() or "")
    if not text.strip():
        return None
    truncated = len(text) > max_chars
    text = text[:max_chars]
    title = path.stem
    for line in text.splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip() or title
            break
    return CleanDoc(
        url=url, title=title[:300], text=text, lang=detect_lang(text), truncated=truncated
    )
