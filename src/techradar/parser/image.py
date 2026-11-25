"""Screenshots to text inside the parser sandbox (Phase 8 Task 5).

Runs only in the parser's limited child process (no network, 120 s, RLIMIT_AS). The image
is first re-encoded into a fresh, metadata-free PNG (intake/rebuild.reencode_image), with
Pillow's decompression-bomb limit turned into an error, and only that copy is read by the
offline RapidOCR models baked into the parser image (they never download).
"""

from __future__ import annotations

import tempfile
import warnings
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from techradar.intake.rebuild import reencode_image
from techradar.schemas.pipeline import CleanDoc
from techradar.security.text import detect_lang, sanitize_text

MAX_OCR_PX = 2048  # longest side of the copy that OCR reads


def image_to_doc(
    path: Path,
    url: str,
    max_chars: int,
    artifacts_path: Path | None,
    *,
    ocr: Callable[[Path], str] | None = None,
) -> CleanDoc | None:
    """OCR text of a PNG or JPEG, or None when it has none.

    Raises ValueError for an unreadable image, an image bomb, or missing OCR models.
    """
    if ocr is None:
        if artifacts_path is None or not Path(artifacts_path).is_dir():
            raise ValueError("offline OCR models missing")
        from techradar.parser.limits import offline_ocr  # limits imports this module

        ocr = offline_ocr(Path(artifacts_path))
    with tempfile.TemporaryDirectory(prefix="image-") as tmp:
        with warnings.catch_warnings():
            # Pillow only warns between its limit and twice its limit: refuse those too.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            clean = reencode_image(path, Path(tmp) / "clean", max_px=MAX_OCR_PX)
        text = sanitize_text(ocr(clean))
    if not text.strip():
        return None
    truncated = len(text) > max_chars
    text = text[:max_chars]
    return CleanDoc(url=url, title="image", text=text, lang=detect_lang(text), truncated=truncated)
