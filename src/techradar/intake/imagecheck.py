"""Structure check for PNG and JPEG screenshots (Phase 8 Task 5).

The pixel size is read from the file's own header with a few lines of code (no image
library), so an image bomb (a small file that claims a huge canvas) is refused before
anything decodes it. Decoding and re-encoding happen later, only inside the parser's
limited child process (parser/image.py), which checks the size again.
"""

from __future__ import annotations

from techradar.schemas.pipeline import IntakeStep

# The same ceiling as the PDF pixel rebuild (intake/rebuild.py); a phone screenshot is
# about 3 million pixels.
MAX_IMAGE_PIXELS = 50_000_000
MAX_IMAGE_SIDE = 16_384
_PNG = b"\x89PNG\r\n\x1a\n"
# Start-of-frame markers carry the size; C4 (DHT), C8 (JPG) and CC (DAC) do not.
_SOF = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:  # markers without a length
            i += 2
            continue
        if marker in (0xD9, 0xDA):  # end of image, or scan data before any frame
            return None
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        if length < 2:
            return None
        if marker in _SOF:
            if i + 9 > len(data):
                return None
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return width, height
        i += 2 + length
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a PNG or JPEG header, or None when it cannot be read."""
    if data.startswith(_PNG):
        return _png_size(data)
    if data.startswith(b"\xff\xd8\xff"):
        return _jpeg_size(data)
    return None


def image_problem(data: bytes) -> str | None:
    """None for an image of a sane size, else why it is refused."""
    size = image_size(data)
    if size is None:
        return "image header unreadable"
    width, height = size
    if width < 1 or height < 1:
        return "image has no pixels"
    if max(width, height) > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
        return f"image too large ({width}x{height} pixels)"
    return None


def check_image(data: bytes) -> IntakeStep:
    """Gateway step 4 for kind `image`."""
    problem = image_problem(data)
    if problem is not None:
        return IntakeStep(name="structure", outcome="reject", detail=problem)
    return IntakeStep(name="structure", outcome="ok", detail="image header ok")
