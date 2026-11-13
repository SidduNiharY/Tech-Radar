"""Archive checks for DOCX and EPUB (Intake Gateway step 4, Phase 2c, SEC-54)."""

from __future__ import annotations

import stat
import zipfile
import zlib
from pathlib import Path, PurePosixPath

from techradar.schemas.pipeline import IntakeStep

# The ratio check applies to entries at least this large: small XML parts can
# compress very well without being a bomb.
RATIO_MIN_BYTES = 1024 * 1024
_READ_CHUNK = 1024 * 1024


def _reject(detail: str) -> IntakeStep:
    return IntakeStep(name="structure", outcome="reject", detail=detail)


def _unsafe_name(name: str) -> bool:
    norm = name.replace("\\", "/")
    if norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
        return True
    return ".." in PurePosixPath(norm).parts


def check_zip(
    path: Path,
    *,
    max_total: int = 200_000_000,
    max_ratio: float = 100.0,
    max_entries: int = 10_000,
) -> IntakeStep:
    """Reject zip bombs, unsafe names, symlinks and encrypted entries.

    Sizes are counted while actually inflating every entry, with a cap: the
    sizes an archive declares can be forged.
    """
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        return _reject(f"not a valid archive ({type(exc).__name__})")
    with z:
        infos = z.infolist()
        if len(infos) > max_entries:
            return _reject(f"too many entries ({len(infos)} > {max_entries})")
        for info in infos:
            if _unsafe_name(info.filename):
                return _reject(f"unsafe name in archive: {info.filename[:100]!r}")
            if stat.S_ISLNK(info.external_attr >> 16):
                return _reject(f"symlink in archive: {info.filename[:100]!r}")
            if info.flag_bits & 0x1:
                return _reject(f"encrypted entry: {info.filename[:100]!r}")
        total = 0
        for info in infos:
            if info.is_dir():
                continue
            entry = 0
            try:
                with z.open(info) as fh:
                    while chunk := fh.read(_READ_CHUNK):
                        entry += len(chunk)
                        total += len(chunk)
                        if total > max_total:
                            return _reject(f"archive inflates past {max_total} bytes")
            except (zipfile.BadZipFile, zlib.error, OSError, EOFError, NotImplementedError) as exc:
                return _reject(f"corrupt entry {info.filename[:100]!r} ({type(exc).__name__})")
            if (
                entry >= RATIO_MIN_BYTES
                and info.compress_size > 0
                and entry / info.compress_size > max_ratio
            ):
                return _reject(f"compression ratio over {max_ratio:g}: {info.filename[:100]!r}")
    return IntakeStep(name="structure", outcome="ok", detail=f"{len(infos)} entries")
