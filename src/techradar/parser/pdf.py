from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import pypdfium2 as pdfium
from pydantic import BaseModel, field_validator

from techradar.schemas.pipeline import CleanDoc
from techradar.security.text import detect_lang, sanitize_text

MIN_TEXT_CHARS = 200
MAX_OUTLINE_ENTRIES = 500
MAX_OUTLINE_TITLE = 300


class OutlineEntry(BaseModel):
    """One bookmark of a PDF. `level` starts at 1 for top-level entries."""

    title: str
    page: int
    level: int

    @field_validator("title")
    @classmethod
    def _cap_title(cls, v: str) -> str:
        return v[:MAX_OUTLINE_TITLE]


class PdfProbe(BaseModel):
    n_pages: int
    outline: list[OutlineEntry]

    @field_validator("outline")
    @classmethod
    def _cap_outline(cls, v: list[OutlineEntry]) -> list[OutlineEntry]:
        return v[:MAX_OUTLINE_ENTRIES]


def pdf_probe(path: Path) -> PdfProbe:
    """Page count and bookmark outline, without extracting any text."""
    try:
        pdf = pdfium.PdfDocument(path)
        n_pages = len(pdf)
        outline: list[OutlineEntry] = []
        for item in pdf.get_toc():
            if len(outline) >= MAX_OUTLINE_ENTRIES:
                break
            dest = item.get_dest()
            index = dest.get_index() if dest is not None else None
            if index is None:
                continue
            outline.append(
                OutlineEntry(
                    title=sanitize_text(item.get_title() or ""),
                    page=index + 1,
                    level=item.level + 1,
                )
            )
    except Exception as exc:
        raise ValueError("unreadable pdf") from exc
    return PdfProbe(n_pages=n_pages, outline=outline)


class _Converter(Protocol):
    def convert(self, source: Path, *, page_range: tuple[int, int]) -> Any: ...


def _docling_converter(artifacts_path: Path | None) -> _Converter:
    # Imported here: Docling is heavy and only part mode needs it.
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=True,  # RapidOCR reads pages that have no text layer
        ocr_options=RapidOcrOptions(),
        artifacts_path=artifacts_path,
        enable_remote_services=False,
    )
    return DocumentConverter(  # type: ignore[no-any-return]
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def pdf_part_to_doc(
    path: Path,
    url: str,
    page_start: int,
    page_end: int,
    max_chars: int = 100_000,
    artifacts_path: Path | None = None,
    converter: _Converter | None = None,
) -> CleanDoc | None:
    """Convert pages page_start..page_end (1-based, inclusive) with Docling.

    Each page's text is preceded by a `<!-- page N -->` line. Returns None when no
    page produced any text.
    """
    conv = converter or _docling_converter(artifacts_path)
    result = conv.convert(path, page_range=(page_start, page_end))
    blocks: list[str] = []
    any_text = False
    for n in range(page_start, page_end + 1):
        page_text = sanitize_text(result.document.export_to_markdown(page_no=n) or "")
        any_text = any_text or bool(page_text)
        blocks.append(f"<!-- page {n} -->\n{page_text}".rstrip())
    if not any_text:
        return None
    text = "\n\n".join(blocks)
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return CleanDoc(
        url=url,
        title=f"pages {page_start}-{page_end}",
        text=text,
        lang=detect_lang(text),
        truncated=truncated,
    )


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
