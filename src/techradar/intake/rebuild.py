"""Pixel rebuild for flagged PDFs and safe image re-encoding (Phase 2c, D36).

A flagged PDF's text layer is attacker-controlled, so its text is taken from
pixels instead: each page is rendered to an image and read by OCR. Both run
inside the parser's limited child process (see parser/limits.py).
"""

from __future__ import annotations

import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

# Longest side of a rendered page; a hostile page size (pages can be
# 200 inches wide) must not become a gigantic bitmap.
MAX_RENDER_PX = 4000
# Decompression-bomb guard for images (Pillow refuses larger ones).
MAX_IMAGE_PIXELS = 50_000_000


def _iter_rendered(
    pdf: Path, out_dir: Path, page_start: int, page_end: int, dpi: int
) -> Iterator[tuple[int, Path]]:
    """Render pages page_start..page_end (1-based, clamped) one at a time."""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(pdf)
    try:
        n = len(doc)
        for number in range(max(1, page_start), min(page_end, n) + 1):
            page = doc[number - 1]
            width, height = page.get_size()  # in points (1/72 inch)
            scale = min(dpi / 72, MAX_RENDER_PX / max(width, height, 1.0))
            image = page.render(scale=scale).to_pil()
            path = out_dir / f"page-{number:04d}.png"
            image.save(path, format="PNG")
            yield number, path
    finally:
        doc.close()


def render_pages(
    pdf: Path, out_dir: Path, page_start: int, page_end: int, *, dpi: int = 150
) -> list[Path]:
    """Render pages page_start..page_end (1-based, clamped) to PNG files."""
    return [path for _n, path in _iter_rendered(pdf, out_dir, page_start, page_end, dpi)]


def rebuild_pages(
    pdf: Path,
    page_start: int,
    page_end: int,
    ocr: Callable[[Path], str],
    *,
    deadline: float | None = None,
    dpi: int = 150,
) -> tuple[str, bool]:
    """(text from pixels, complete). Each page is rendered, read and deleted in turn.

    At the deadline (time.monotonic) it stops and ends the text with a visible note
    for the pages it did not read, so a part never silently loses pages or times out.
    """
    blocks: list[str] = []
    complete = True
    doc = pdfium.PdfDocument(pdf)
    try:
        last = min(page_end, len(doc))
    finally:
        doc.close()
    with tempfile.TemporaryDirectory(prefix="rebuild-") as tmp:
        for number, path in _iter_rendered(pdf, Path(tmp), page_start, page_end, dpi):
            if deadline is not None and time.monotonic() >= deadline:
                complete = False
                blocks.append(f"<!-- pages {number}-{last} not read (time limit) -->")
                break
            blocks.append(f"<!-- page {number} -->\n{ocr(path).strip()}".rstrip())
            path.unlink(missing_ok=True)
    return "\n\n".join(blocks), complete


def pixel_rebuild(pdf: Path, page_start: int, page_end: int, ocr: Callable[[Path], str]) -> str:
    """Text from pixels only, with a `<!-- page N -->` line before each page."""
    return rebuild_pages(pdf, page_start, page_end, ocr)[0]


def reencode_image(src: Path, dst: Path, max_px: int = 2048) -> Path:
    """Re-encode an image as a metadata-free PNG that fits within max_px.

    Raises ValueError for unreadable images and decompression bombs.
    """
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(src) as im:
            im.load()
            rgb = im.convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError) as exc:
        raise ValueError(f"image refused: {type(exc).__name__}") from exc
    rgb.thumbnail((max_px, max_px))
    clean = Image.new("RGB", rgb.size)  # a fresh image carries no metadata
    clean.paste(rgb)
    out = dst.with_suffix(".png")
    clean.save(out, format="PNG")
    return out
